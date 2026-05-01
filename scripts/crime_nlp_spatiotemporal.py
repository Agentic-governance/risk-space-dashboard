#!/usr/bin/env python3
"""Crime spatiotemporal analysis from CSV files under data/crime/."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, Optional

TARGET_COLUMNS = {
    "time": "発生時（始期）",
    "date": "発生年月日（始期）",
    "location": "発生場所",
    "location_detail": "発生場所の詳細",
    "chome": "町丁目（発生地）",
    "crime_name": "罪名",
    "prefecture": "都道府県（発生地）",
    "lock": "施錠関係",
}

ENCODINGS_TO_TRY = [
    "utf-8-sig",
    "utf-8",
    "cp932",
    "shift_jis",
    "euc_jp",
    "iso2022_jp",
    "latin-1",
]

STOPWORDS = {
    "その他",
    "不明",
    "なし",
    "有り",
    "あり",
    "無",
    "有",
    "等",
    "及び",
    "その",
    "ところ",
    "場所",
}


def detect_encoding(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ENCODINGS_TO_TRY:
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "utf-8"


def clean_value(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).strip().strip('"').strip()


def parse_hour(value: str) -> Optional[int]:
    text = clean_value(value)
    if not text:
        return None
    match = re.search(r"\d{1,2}", text)
    if not match:
        return None
    hour = int(match.group(0))
    return hour if 0 <= hour <= 23 else None


def parse_event_date(value: str) -> Optional[date]:
    text = clean_value(value)
    if not text:
        return None

    compact = re.sub(r"\D", "", text)
    if len(compact) == 8:
        try:
            return datetime.strptime(compact, "%Y%m%d").date()
        except ValueError:
            pass

    parts = [p for p in re.split(r"[^0-9]", text) if p]
    if len(parts) >= 3:
        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            return date(y, m, d)
        except ValueError:
            return None

    return None


def normalize_location(value: str) -> str:
    text = clean_value(value)
    return text if text else "不明"


def normalize_prefecture(row: Dict[str, str], csv_path: Path, root: Path) -> str:
    pref = clean_value(row.get(TARGET_COLUMNS["prefecture"], ""))
    if pref:
        return pref

    try:
        rel = csv_path.relative_to(root)
    except ValueError:
        return "不明"

    parts = rel.parts
    if len(parts) >= 3 and parts[0] == "prefectures":
        return parts[1]
    return "不明"


def normalize_lock_status(value: str) -> str:
    text = clean_value(value)
    if not text:
        return "unknown"
    if "無施錠" in text or "施錠せず" in text:
        return "unlocked"
    if "施錠" in text:
        return "locked"
    return "other"


def tokenize_location_detail(value: str) -> Iterable[str]:
    text = clean_value(value)
    if not text:
        return []

    normalized = (
        text.replace("駐車（輪）場", "駐車場")
        .replace("（", " ")
        .replace("）", " ")
        .replace("(", " ")
        .replace(")", " ")
    )

    chunks = re.split(r"[\s,，、/／・]+", normalized)
    tokens = []
    for chunk in chunks:
        token = chunk.strip("._-")
        if not token:
            continue
        if token in STOPWORDS:
            continue
        if len(token) <= 1:
            continue
        if re.fullmatch(r"\d+", token):
            continue
        tokens.append(token)
    return tokens


def sorted_counter(counter: Counter, by_key_numeric: bool = False) -> Dict[str, int]:
    if by_key_numeric:
        items = sorted(counter.items(), key=lambda kv: int(kv[0]))
    else:
        items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return {str(k): int(v) for k, v in items}


def nested_counter_to_dict(data: Dict[str, Counter], hour_sorted: bool = False) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    for key in sorted(data.keys()):
        if hour_sorted:
            items = sorted(data[key].items(), key=lambda kv: int(kv[0]))
        else:
            items = sorted(data[key].items(), key=lambda kv: (-kv[1], kv[0]))
        out[key] = {str(k): int(v) for k, v in items}
    return out


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    crime_root = project_root / "data" / "crime"
    output_path = project_root / "docs" / "data" / "crime_spatiotemporal_analysis.json"

    csv_paths = sorted(p for p in crime_root.rglob("*.csv") if p.is_file())

    hourly = Counter({str(h): 0 for h in range(24)})
    weekday = Counter({str(i): 0 for i in range(7)})  # Monday=0
    monthly = Counter({str(m): 0 for m in range(1, 13)})
    location_type = Counter()
    detail_keywords = Counter()
    hour_x_crime = defaultdict(Counter)
    location_x_hour = defaultdict(Counter)
    pref_hour = defaultdict(Counter)
    pref_location = defaultdict(Counter)
    lock_status = Counter()

    total_rows = 0
    processed_rows = 0
    rows_with_time = 0
    rows_with_date = 0
    rows_with_location = 0
    rows_with_prefecture = 0
    rows_with_lock = 0
    file_errors = []
    used_encodings = Counter()

    for csv_path in csv_paths:
        try:
            encoding = detect_encoding(csv_path)
            used_encodings[encoding] += 1
            with csv_path.open("r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    continue

                rel_parent = csv_path.parent.relative_to(crime_root)
                for row in reader:
                    total_rows += 1
                    hour = parse_hour(row.get(TARGET_COLUMNS["time"], ""))
                    event_date = parse_event_date(row.get(TARGET_COLUMNS["date"], ""))
                    loc = normalize_location(row.get(TARGET_COLUMNS["location"], ""))
                    loc_detail = clean_value(row.get(TARGET_COLUMNS["location_detail"], ""))
                    crime_name = clean_value(row.get(TARGET_COLUMNS["crime_name"], "")) or "不明"
                    pref = normalize_prefecture(row, csv_path, crime_root)
                    lock_raw = clean_value(row.get(TARGET_COLUMNS["lock"], ""))

                    row_has_any = False

                    if hour is not None:
                        hourly[str(hour)] += 1
                        rows_with_time += 1
                        row_has_any = True

                    if event_date is not None:
                        weekday[str(event_date.weekday())] += 1
                        monthly[str(event_date.month)] += 1
                        rows_with_date += 1
                        row_has_any = True

                    if loc != "不明":
                        location_type[loc] += 1
                        rows_with_location += 1
                        row_has_any = True

                    if hour is not None and crime_name:
                        hour_x_crime[str(hour)][crime_name] += 1

                    if loc != "不明" and hour is not None:
                        location_x_hour[loc][str(hour)] += 1

                    if pref != "不明":
                        rows_with_prefecture += 1
                        if hour is not None:
                            pref_hour[pref][str(hour)] += 1
                        if loc != "不明":
                            pref_location[pref][loc] += 1

                    if loc_detail:
                        for token in tokenize_location_detail(loc_detail):
                            detail_keywords[token] += 1

                    if lock_raw:
                        lock_status[normalize_lock_status(lock_raw)] += 1
                        rows_with_lock += 1

                    # Keep the folder read side-effect explicit for metadata diagnostics.
                    _ = rel_parent

                    if row_has_any:
                        processed_rows += 1
        except Exception as exc:
            file_errors.append({"file": str(csv_path.relative_to(project_root)), "error": str(exc)})

    prefecture_peak_hours = {}
    for pref, pref_hours in pref_hour.items():
        peak_hour = None
        peak_hour_count = 0
        if pref_hours:
            peak_hour, peak_hour_count = max(pref_hours.items(), key=lambda kv: (kv[1], -int(kv[0])))

        top_location = None
        top_location_count = 0
        if pref_location[pref]:
            top_location, top_location_count = max(pref_location[pref].items(), key=lambda kv: (kv[1], kv[0]))

        prefecture_peak_hours[pref] = {
            "peak_hour": peak_hour,
            "peak_hour_count": int(peak_hour_count),
            "top_location": top_location,
            "top_location_count": int(top_location_count),
        }

    lock_total = sum(lock_status.values())
    lock_ratio = {
        key: (lock_status[key] / lock_total if lock_total else 0.0)
        for key in ["locked", "unlocked", "other", "unknown"]
    }

    result = {
        "metadata": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "input_root": str(crime_root.relative_to(project_root)),
            "output_path": str(output_path.relative_to(project_root)),
            "csv_files_scanned": len(csv_paths),
            "total_rows": total_rows,
            "rows_used_for_any_analysis": processed_rows,
            "rows_with_time": rows_with_time,
            "rows_with_date": rows_with_date,
            "rows_with_location": rows_with_location,
            "rows_with_prefecture": rows_with_prefecture,
            "rows_with_lock_status": rows_with_lock,
            "weekday_index": {
                "0": "Monday",
                "1": "Tuesday",
                "2": "Wednesday",
                "3": "Thursday",
                "4": "Friday",
                "5": "Saturday",
                "6": "Sunday",
            },
            "encodings_detected": sorted_counter(used_encodings),
            "file_errors": file_errors,
            "target_columns": TARGET_COLUMNS,
        },
        "hourly_distribution": sorted_counter(hourly, by_key_numeric=True),
        "weekday_distribution": sorted_counter(weekday, by_key_numeric=True),
        "monthly_distribution": sorted_counter(monthly, by_key_numeric=True),
        "hour_x_crime_cross": nested_counter_to_dict(hour_x_crime),
        "location_type_distribution": sorted_counter(location_type),
        "location_detail_keywords": sorted_counter(detail_keywords),
        "location_x_hour_cross": nested_counter_to_dict(location_x_hour, hour_sorted=True),
        "prefecture_peak_hours": {
            k: prefecture_peak_hours[k] for k in sorted(prefecture_peak_hours.keys())
        },
        "lock_status": {
            "counts": {k: int(lock_status[k]) for k in ["locked", "unlocked", "other", "unknown"]},
            "ratios": lock_ratio,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[done] CSV files scanned: {len(csv_paths)}")
    print(f"[done] Total rows: {total_rows}")
    print(f"[done] Output written: {output_path}")


if __name__ == "__main__":
    main()
