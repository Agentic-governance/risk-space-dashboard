#!/usr/bin/env python3
"""
build_historical_baseline.py

Aggregates all historical crime CSV data from data/crime/prefectures/
into a unified JSON baseline for the risk model.

Output: docs/data/historical_crime_baseline.json
"""

import os
import sys
import csv
import json
import re
import io
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
PREFECTURES_DIR = PROJECT_ROOT / "data" / "crime" / "prefectures"
PREF_CENTROIDS_PATH = PROJECT_ROOT / "data" / "crime" / "national" / "pref_centroids.json"
CITY_CENTROIDS_PATH = PROJECT_ROOT / "data" / "crime" / "national" / "city_centroids.json"
OUTPUT_PATH = PROJECT_ROOT / "docs" / "data" / "historical_crime_baseline.json"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column name candidates (normalised to internal keys)
# ---------------------------------------------------------------------------
# prefecture
PREF_COLS = ["都道府県（発生地）", "都道府県", "prefecture"]
# city
CITY_COLS = ["市区町村（発生地）", "市区町村", "city"]
# crime type (罪種)
CRIME_TYPE_COLS = ["罪名", "罪種", "手口", "crime_type"]
# sub-type (手口) — used when 罪名 alone is too generic ("窃盗")
MODUS_COLS = ["手口", "modus"]
# occurrence date
DATE_COLS = ["発生年月日（始期）", "発生年月日", "date"]
# count  — most rows are individual incidents (count=1)
COUNT_COLS = ["件数", "count"]

ENCODINGS_TO_TRY = ["utf-8-sig", "shift_jis", "utf-8", "cp932"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def detect_encoding(raw: bytes) -> str:  # noqa: E501
    """Try chardet first, then fall back to manual list."""
    try:
        import chardet
        result = chardet.detect(raw)
        enc = result.get("encoding") or "utf-8"
        # normalise chardet names
        enc = enc.upper().replace("-", "_")
        if enc in ("UTF_8_SIG", "UTF_8"):
            return "utf-8-sig"
        if enc in ("SHIFT_JIS", "SJIS"):
            return "shift_jis"
        return enc.lower()
    except ImportError:
        return "utf-8-sig"


def read_csv_rows(path: Path):
    """
    Read a CSV file, returning (list_of_dicts, encoding_used) or (None, None).
    Tries multiple encodings and strips BOM.
    """
    raw = path.read_bytes()
    if not raw:
        return None, None

    detected = detect_encoding(raw[:4096])
    encodings = [detected] + [e for e in ENCODINGS_TO_TRY if e != detected]

    for enc in encodings:
        try:
            text = raw.decode(enc, errors="strict")
            # strip BOM if present
            text = text.lstrip("\ufeff")
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
            if rows:
                return rows, enc
        except (UnicodeDecodeError, Exception):
            continue

    # Last resort: replace errors
    for enc in encodings:
        try:
            text = raw.decode(enc, errors="replace").lstrip("\ufeff")
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
            if rows:
                log.warning("  [warn] %s decoded with errors using %s", path.name, enc)
                return rows, enc
        except Exception:
            continue

    return None, None


def pick_col(row: dict, candidates: list):
    """Return first candidate key that exists (non-empty) in row."""
    for c in candidates:
        v = row.get(c, "").strip()
        if v:
            return v
    return None


def parse_date(raw: str):
    """
    Parse various date formats → (year, month).
    Formats seen:
      20240725   → 2024-07-25
      2023-11-25
      2023/1/24
    """
    raw = raw.strip()
    # YYYYMMDD (no separators)
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", raw)
    if m:
        return int(m.group(1)), int(m.group(2))
    # YYYY-MM-DD or YYYY/MM/DD or YYYY/M/D
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", raw)
    if m:
        return int(m.group(1)), int(m.group(2))
    # YYYYMM (6 digits)
    m = re.match(r"^(\d{4})(\d{2})$", raw)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def derive_crime_label(row: dict) -> str:
    """
    Build a readable crime-type label from 罪名 + 手口.
    For generic 罪名 like '窃盗', append the 手口 to be specific.
    """
    generic_types = {"窃盗", "刑法犯", "特別法犯", ""}
    crime = pick_col(row, CRIME_TYPE_COLS) or "不明"
    modus = pick_col(row, MODUS_COLS) or ""

    # If the crime type column is actually the modus column (some CSVs only have 手口)
    # we already got that value; skip duplicating.
    if crime == modus:
        return crime

    if crime in generic_types and modus:
        return modus
    if modus and crime not in generic_types:
        return f"{crime}_{modus}"
    return crime


# ---------------------------------------------------------------------------
# Main aggregation
# ---------------------------------------------------------------------------

def load_centroids():
    pref_centroids = {}
    city_centroids = {}

    if PREF_CENTROIDS_PATH.exists():
        with open(PREF_CENTROIDS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            for item in data:
                name = item.get("prefecture", "")
                if name:
                    pref_centroids[name] = {
                        "lat": item.get("lat"),
                        "lon": item.get("lon"),
                    }
        elif isinstance(data, dict):
            pref_centroids = data
        log.info("Loaded %d prefecture centroids", len(pref_centroids))
    else:
        log.warning("pref_centroids.json not found at %s", PREF_CENTROIDS_PATH)

    if CITY_CENTROIDS_PATH.exists():
        with open(CITY_CENTROIDS_PATH, encoding="utf-8") as f:
            city_centroids = json.load(f)
        log.info("Loaded %d city centroids", len(city_centroids))
    else:
        log.warning("city_centroids.json not found at %s", CITY_CENTROIDS_PATH)

    return pref_centroids, city_centroids


def aggregate_csvs():
    """
    Walk all CSV files; return a nested dict:
      raw[prefecture][crime_type][year][month] = incident_count
    and stats counters.
    """
    # raw[pref][crime_type][year][month] = count
    raw: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(int))))
    stats = {"files_found": 0, "files_parsed": 0, "files_skipped": 0,
             "rows_total": 0, "rows_extracted": 0}

    if not PREFECTURES_DIR.exists():
        log.error("Prefectures directory not found: %s", PREFECTURES_DIR)
        sys.exit(1)

    all_csv = sorted(PREFECTURES_DIR.rglob("*.csv"))
    stats["files_found"] = len(all_csv)
    log.info("Found %d CSV files under %s", len(all_csv), PREFECTURES_DIR)

    for idx, path in enumerate(all_csv, 1):
        if idx % 50 == 0 or idx == len(all_csv):
            log.info("  Processing %d/%d files…", idx, len(all_csv))

        rows, enc = read_csv_rows(path)
        if rows is None:
            log.warning("  SKIP (unreadable): %s", path.name)
            stats["files_skipped"] += 1
            continue

        stats["files_parsed"] += 1
        stats["rows_total"] += len(rows)

        for row in rows:
            # Strip whitespace from all values
            row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}

            pref = pick_col(row, PREF_COLS)
            if not pref:
                # fall back: infer from directory name
                pref = path.parent.name  # e.g. "山梨県"

            date_raw = pick_col(row, DATE_COLS)
            if not date_raw:
                continue

            year, month = parse_date(date_raw)
            if year is None or month is None:
                continue
            if not (2010 <= year <= 2030) or not (1 <= month <= 12):
                continue

            crime_label = derive_crime_label(row)

            # Count: some CSVs have a 件数 column; most are 1 row = 1 incident
            count_raw = pick_col(row, COUNT_COLS)
            try:
                count = int(count_raw) if count_raw else 1
            except ValueError:
                count = 1

            raw[pref][crime_label][str(year)][month] += count
            stats["rows_extracted"] += 1

    return raw, stats


def build_output(raw: dict, pref_centroids: dict, city_centroids: dict) -> dict:
    """
    Convert raw nested dict into the final output format.
    Also compute monthly_avg and risk_score per prefecture.
    """
    prefectures_out = {}

    # We need max total_incidents across prefectures for normalising risk_score
    pref_totals = {}
    for pref, types in raw.items():
        total = sum(
            count
            for crime_data in types.values()
            for year_data in crime_data.values()
            for count in year_data.values()
        )
        pref_totals[pref] = total

    max_total = max(pref_totals.values()) if pref_totals else 1

    for pref, types in sorted(raw.items()):
        centroid = pref_centroids.get(pref, {})
        lat = centroid.get("lat")
        lon = centroid.get("lon")

        total_incidents = pref_totals[pref]

        by_type: dict = {}
        monthly_avg: dict = {}

        for crime_type, year_data in sorted(types.items()):
            # Build year→[m1..m12] array (0-indexed placeholders)
            by_year: dict = {}
            all_monthly_counts = []

            for year_str, month_data in sorted(year_data.items()):
                monthly = [month_data.get(m, 0) for m in range(1, 13)]
                by_year[year_str] = monthly
                all_monthly_counts.extend(monthly)

            by_type[crime_type] = by_year

            # Average monthly count across all data (skip zero months)
            non_zero = [c for c in all_monthly_counts if c > 0]
            monthly_avg[crime_type] = round(
                sum(non_zero) / len(non_zero), 2
            ) if non_zero else 0.0

        # risk_score: 0.0–1.0 relative to the busiest prefecture
        risk_score = round(total_incidents / max_total, 4) if max_total > 0 else 0.0

        prefectures_out[pref] = {
            "lat": lat,
            "lon": lon,
            "total_incidents": total_incidents,
            "by_type": by_type,
            "monthly_avg": monthly_avg,
            "risk_score": risk_score,
        }

    return prefectures_out


def main():
    log.info("=== build_historical_baseline.py start ===")

    pref_centroids, city_centroids = load_centroids()
    raw, stats = aggregate_csvs()

    log.info(
        "Parse complete — files: %d parsed / %d skipped / %d total",
        stats["files_parsed"], stats["files_skipped"], stats["files_found"],
    )
    log.info(
        "Rows: %d extracted / %d total", stats["rows_extracted"], stats["rows_total"]
    )

    if not raw:
        log.error("No data extracted. Aborting.")
        sys.exit(1)

    prefectures_out = build_output(raw, pref_centroids, city_centroids)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_records": stats["rows_extracted"],
        "source_files_parsed": stats["files_parsed"],
        "source_files_skipped": stats["files_skipped"],
        "prefectures": prefectures_out,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log.info(
        "Wrote %d prefectures → %s  (%.1f KB)",
        len(prefectures_out),
        OUTPUT_PATH,
        OUTPUT_PATH.stat().st_size / 1024,
    )
    log.info("=== done ===")


if __name__ == "__main__":
    main()
