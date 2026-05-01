#!/usr/bin/env python3
"""
Normalize crime CSV/XLSX data from prefectures into unified event schema.
Outputs data/normalized/crime_national.json
"""

from __future__ import annotations

import csv
import glob
import json
import os
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import chardet
import openpyxl

BASE = Path(__file__).resolve().parent.parent
PREF_DIR = BASE / "data" / "crime" / "prefectures"
OUT_DIR = BASE / "data" / "normalized"
OUT_FILE = OUT_DIR / "crime_national.json"

JST = timezone(timedelta(hours=9))

# ── subtype mapping ──
TEGUCHI_MAP = {
    "ひったくり": "theft_purse_snatching",
    "車上ねらい": "theft_car_breakin",
    "部品ねらい": "theft_parts",
    "自販機ねらい": "theft_vending",
    "自動販売機ねらい": "theft_vending",
    "自動車盗": "theft_vehicle",
    "オートバイ盗": "theft_motorcycle",
    "自転車盗": "theft_bicycle",
}

# severity: all are theft → 2 (property crime, non-violent except snatching → 3)
SEVERITY_MAP = {
    "theft_purse_snatching": 3,
    "theft_car_breakin": 2,
    "theft_parts": 2,
    "theft_vending": 2,
    "theft_vehicle": 2,
    "theft_motorcycle": 2,
    "theft_bicycle": 1,
}

# XLSX filename → teguchi
XLSX_NAME_MAP = {
    "自転車盗": "自転車盗",
    "ひったくり": "ひったくり",
    "部品ねらい": "部品ねらい",
    "自動販売機ねらい": "自動販売機ねらい",
    "車上ねらい": "車上ねらい",
    "自動車盗": "自動車盗",
    "オートバイ盗": "オートバイ盗",
}

# Column name normalization: strip common suffixes
def normalize_col(col: str) -> str:
    col = col.strip().strip('"').strip('\ufeff')
    # Remove （発生地） suffix
    col = re.sub(r'（発生地）', '', col)
    # Remove （始期） suffix
    col = re.sub(r'（始期）', '', col)
    return col

# Map normalized column names to standard field names
COL_MAP = {
    "罪名": "crime_name",
    "手口": "teguchi",
    "管轄警察署": "police_station",
    "管轄交番・駐在所": "koban",
    "市区町村コード": "city_code",
    "都道府県": "prefecture",
    "市区町村": "city",
    "町丁目": "town",
    "発生年月日": "date",
    "発生時": "hour",
    "発生場所": "location",
    "発生場所の詳細": "location_detail",
    "被害者の性別": "victim_sex",
    "被害者の年齢": "victim_age",
    "被害者の職業": "victim_occupation",
    "施錠関係": "lock_status",
    "盗難防止装置の有無": "anti_theft",
    "現金被害の有無": "cash_damage",
    "現金以外の主な被害品": "stolen_items",
    "発生場所の属性": "location_attr",
}


def detect_encoding(raw_bytes: bytes) -> str:
    # Use a sample for chardet (performance), but validate on full data
    sample = raw_bytes[:20000]
    result = chardet.detect(sample)
    enc = result.get("encoding") or "cp932"
    # Normalize common aliases
    upper = enc.upper()
    if upper in ("SHIFT_JIS", "SHIFT-JIS", "SJIS", "WINDOWS-31J"):
        enc = "cp932"
    # If chardet picks a non-Japanese encoding, try cp932 first since all
    # files in this dataset are Japanese. Common misdetection: windows-1253.
    JAPANESE_ENCODINGS = {"CP932", "UTF-8", "UTF-8-SIG", "EUC-JP", "ISO-2022-JP",
                          "SHIFT_JIS", "SHIFT-JIS", "SJIS", "WINDOWS-31J"}
    if upper not in JAPANESE_ENCODINGS:
        # Verify cp932 can decode the FULL data without errors
        try:
            raw_bytes.decode("cp932")
            enc = "cp932"
        except (UnicodeDecodeError, LookupError):
            pass  # keep detected encoding
    return enc


def parse_date(val) -> str | None:
    """Parse date value into ISO 8601 string."""
    if val is None:
        return None
    val = str(val).strip()
    if not val:
        return None

    # YYYYMMDD integer or string
    m = re.match(r'^(\d{4})(\d{2})(\d{2})$', val)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=JST)
            return dt.isoformat()
        except ValueError:
            return None

    # YYYY-MM-DD or YYYY/M/D or YYYY/MM/DD
    m = re.match(r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$', val)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=JST)
            return dt.isoformat()
        except ValueError:
            return None

    # 令和/平成 dates
    m = re.match(r'(令和|平成)(\d+)年(\d+)月(\d+)日', val)
    if m:
        era, y, mo, d = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
        base_year = 2018 if era == "令和" else 1988
        try:
            dt = datetime(base_year + y, mo, d, tzinfo=JST)
            return dt.isoformat()
        except ValueError:
            return None

    return None


def parse_hour(val) -> int | None:
    if val is None:
        return None
    val = str(val).strip()
    m = re.match(r'^(\d{1,2})', val)
    if m:
        h = int(m.group(1))
        if 0 <= h <= 23:
            return h
    return None


def read_csv_file(filepath: str) -> list[dict]:
    """Read a CSV file, auto-detecting encoding and delimiter."""
    with open(filepath, "rb") as f:
        raw = f.read()

    if len(raw) == 0:
        return []

    enc = detect_encoding(raw)
    try:
        text = raw.decode(enc, errors="replace")
    except (UnicodeDecodeError, LookupError):
        text = raw.decode("cp932", errors="replace")

    # Strip BOM
    text = text.lstrip('\ufeff')

    # Detect delimiter
    first_line = text.split('\n')[0]
    delimiter = '\t' if first_line.count('\t') > first_line.count(',') else ','

    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    rows = []
    for row in reader:
        # Normalize column names
        normalized = {}
        for k, v in row.items():
            if k is None:
                continue
            nk = normalize_col(k)
            std = COL_MAP.get(nk, nk)
            normalized[std] = v.strip().strip('"') if v else None
        rows.append(normalized)
    return rows


def read_xlsx_file(filepath: str) -> list[dict]:
    """Read an XLSX file."""
    wb = openpyxl.load_workbook(filepath, read_only=True)
    ws = wb.active
    rows_out = []

    header = None
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            header = [normalize_col(str(c)) if c else f"col_{j}" for j, c in enumerate(row)]
            header = [COL_MAP.get(h, h) for h in header]
            continue
        rec = {}
        for j, val in enumerate(row):
            if j < len(header):
                rec[header[j]] = str(val).strip() if val is not None else None
        rows_out.append(rec)

    wb.close()
    return rows_out


def infer_subtype_from_filename(filename: str) -> str | None:
    """Infer crime subtype from filename when teguchi column is missing."""
    fname = os.path.basename(filename).lower()
    decoded = __import__('urllib.parse', fromlist=['unquote']).unquote(fname)

    mapping = {
        "hittakuri": "ひったくり",
        "syazyounerai": "車上ねらい",
        "buhinnerai": "部品ねらい",
        "zidouhanbaikinerai": "自動販売機ねらい",
        "zidousyatou": "自動車盗",
        "ootobaitou": "オートバイ盗",
        "zitensyatou": "自転車盗",
        "ひったくり": "ひったくり",
        "車上ねらい": "車上ねらい",
        "部品ねらい": "部品ねらい",
        "自動販売機ねらい": "自動販売機ねらい",
        "自動車盗": "自動車盗",
        "オートバイ盗": "オートバイ盗",
        "自転車盗": "自転車盗",
    }

    for key, teguchi in mapping.items():
        if key in decoded:
            return TEGUCHI_MAP.get(teguchi)
    return None


def normalize_record(row: dict, pref_name: str, filepath: str) -> dict | None:
    """Convert a raw row into the unified schema."""
    # Get subtype from teguchi column or filename
    teguchi = row.get("teguchi", "")
    subtype = TEGUCHI_MAP.get(teguchi) if teguchi else None
    if not subtype:
        subtype = infer_subtype_from_filename(filepath)
    if not subtype:
        return None  # Can't classify

    # Parse date
    date_str = parse_date(row.get("date"))
    hour = parse_hour(row.get("hour"))
    if date_str and hour is not None:
        # Insert hour into the datetime
        date_str = re.sub(r'T00:00:00', f'T{hour:02d}:00:00', date_str)

    prefecture = row.get("prefecture", pref_name)
    city = row.get("city")
    town = row.get("town")
    city_code = row.get("city_code")

    # Build raw dict (non-null original fields)
    raw = {k: v for k, v in row.items() if v is not None and v != ""}

    severity = SEVERITY_MAP.get(subtype, 2)

    record = {
        "id": str(uuid.uuid4()),
        "source_id": None,
        "layer": "crime",
        "subtype": subtype,
        "geometry": None,
        "admin": {
            "prefecture": prefecture,
            "prefecture_code": city_code[:2] if city_code and len(str(city_code)) >= 2 else None,
            "city": city,
            "city_code": city_code,
            "town": town,
        },
        "spatial_resolution": "town" if town else ("city" if city else "prefecture"),
        "occurred_at": date_str,
        "published_at": None,
        "time_resolution": "hour" if hour is not None else ("day" if date_str else None),
        "realtime": False,
        "severity": severity,
        "risk_score": None,
        "source": {
            "org": f"{prefecture}警" if prefecture else f"{pref_name}警",
            "url": None,
            "license": "open",
            "fee": False,
            "update_freq": "irregular",
            "missing_rate": None,
            "geocoded": False,
        },
        "raw": raw,
    }
    return record


def main():
    all_records = []
    pref_counts = Counter()
    subtype_counts = Counter()
    column_coverage = Counter()
    total_columns_seen = set()
    skipped_files = []
    error_files = []
    files_processed = 0

    pref_dirs = sorted(PREF_DIR.iterdir())
    for pref_dir in pref_dirs:
        if not pref_dir.is_dir():
            continue
        pref_name = pref_dir.name

        # Collect CSV and XLSX files
        csv_files = list(pref_dir.glob("*.csv")) + list(pref_dir.glob("*.csv.csv"))
        xlsx_files = list(pref_dir.glob("*.xlsx"))

        if not csv_files and not xlsx_files:
            continue

        for filepath in csv_files + xlsx_files:
            try:
                if filepath.suffix == ".xlsx":
                    rows = read_xlsx_file(str(filepath))
                else:
                    rows = read_csv_file(str(filepath))
            except Exception as e:
                error_files.append((str(filepath), str(e)))
                continue

            if not rows:
                continue

            # Check if this is crime data (must have teguchi or recognizable filename)
            first = rows[0]
            has_teguchi = "teguchi" in first and first["teguchi"] in TEGUCHI_MAP
            has_filename_hint = infer_subtype_from_filename(str(filepath)) is not None

            if not has_teguchi and not has_filename_hint:
                skipped_files.append(str(filepath))
                continue

            files_processed += 1

            # Track columns
            for row in rows:
                for k, v in row.items():
                    total_columns_seen.add(k)
                    if v is not None and v != "":
                        column_coverage[k] += 1

            for row in rows:
                record = normalize_record(row, pref_name, str(filepath))
                if record:
                    all_records.append(record)
                    pref_counts[record["admin"]["prefecture"] or pref_name] += 1
                    subtype_counts[record["subtype"]] += 1

    # Write output
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=None, separators=(",", ":"))

    # Also write pretty-printed summary
    total = len(all_records)

    print("=" * 60)
    print(f"  Crime Data Normalization Complete")
    print("=" * 60)
    print(f"\nFiles processed: {files_processed}")
    print(f"Total records:   {total:,}")
    print(f"Output:          {OUT_FILE}")
    print(f"Output size:     {OUT_FILE.stat().st_size / 1024 / 1024:.1f} MB")

    print(f"\n{'Prefecture':<12} {'Count':>8}")
    print("-" * 22)
    for pref, count in sorted(pref_counts.items(), key=lambda x: -x[1]):
        print(f"  {pref:<10} {count:>8,}")

    print(f"\n{'Subtype':<28} {'Count':>8}")
    print("-" * 38)
    for st, count in sorted(subtype_counts.items(), key=lambda x: -x[1]):
        print(f"  {st:<26} {count:>8,}")

    print(f"\nColumn coverage (non-null rate across {total:,} records):")
    print("-" * 50)
    for col, count in sorted(column_coverage.items(), key=lambda x: -x[1]):
        pct = count / total * 100 if total > 0 else 0
        print(f"  {col:<30} {count:>8,}  ({pct:5.1f}%)")

    if skipped_files:
        print(f"\nSkipped (not crime data): {len(skipped_files)}")
        for f in skipped_files:
            print(f"  {os.path.basename(f)}")

    if error_files:
        print(f"\nErrors: {len(error_files)}")
        for f, e in error_files:
            print(f"  {os.path.basename(f)}: {e}")


if __name__ == "__main__":
    main()
