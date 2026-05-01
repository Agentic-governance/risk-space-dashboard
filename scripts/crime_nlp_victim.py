#!/usr/bin/env python3
"""Aggregate victim-related attributes from crime CSV files.

Scans data/crime recursively, auto-detects victim columns, computes:
- National age histogram (10-year bins), gender ratio, occupation top20
- Prefecture victim profile (median age, gender ratio, most common occupation)
- Crime x victim attribute cross tabs
- Vulnerability multipliers for age x gender x crime combinations
- Locking-related aggregates when lock columns exist

Output: docs/data/crime_victim_analysis.json
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

ENCODINGS = ["utf-8-sig", "utf-8", "cp932", "shift_jis", "euc_jp"]
ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data" / "crime"
OUTPUT_PATH = ROOT_DIR / "docs" / "data" / "crime_victim_analysis.json"

UNKNOWN = "不明"
PREFECTURES = {
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
}


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def pick_best_column(headers: list[str], rules: list[tuple[tuple[str, ...], int]]) -> str | None:
    best_col = None
    best_score = -1
    for col in headers:
        name = normalize_text(col)
        if not name:
            continue
        score = 0
        for keywords, points in rules:
            if all(k in name for k in keywords):
                score += points
        if score > best_score:
            best_score = score
            best_col = col
    return best_col if best_score > 0 else None


def detect_columns(headers: list[str]) -> dict[str, str | list[str] | None]:
    age_col = pick_best_column(
        headers,
        [
            (("被害者", "年齢"), 100),
            (("年齢",), 30),
        ],
    )
    gender_col = pick_best_column(
        headers,
        [
            (("被害者", "性別"), 100),
            (("性別",), 30),
        ],
    )
    occupation_col = pick_best_column(
        headers,
        [
            (("被害者", "職業"), 100),
            (("職業",), 30),
        ],
    )
    prefecture_col = pick_best_column(
        headers,
        [
            (("都道府県",), 100),
            (("都",), 1),
            (("道",), 1),
            (("府",), 1),
            (("県",), 1),
        ],
    )
    crime_col = pick_best_column(
        headers,
        [
            (("罪名",), 100),
            (("罪種",), 80),
            (("手口",), 40),
        ],
    )

    lock_cols = []
    for c in headers:
        name = normalize_text(c)
        if not name:
            continue
        if any(k in name for k in ("施錠", "鍵", "ロック", "盗難防止")):
            lock_cols.append(c)

    return {
        "age": age_col,
        "gender": gender_col,
        "occupation": occupation_col,
        "prefecture": prefecture_col,
        "crime": crime_col,
        "lock_cols": lock_cols,
    }


def infer_prefecture_from_path(path: Path) -> str:
    for part in reversed(path.parts):
        if part in PREFECTURES:
            return part
    return UNKNOWN


def parse_prefecture(value: str | None, path: Path) -> str:
    text = normalize_text(value).strip("\"' ")
    if text in PREFECTURES:
        return text
    for pref in PREFECTURES:
        if pref in text:
            return pref
    return infer_prefecture_from_path(path)


def parse_gender(value: str | None) -> str:
    text = normalize_text(value)
    if not text:
        return UNKNOWN
    if "法人" in text or "団体" in text:
        return "法人・団体"
    if "男" in text:
        return "男性"
    if "女" in text:
        return "女性"
    if "不明" in text or "なし" in text or "その他" in text:
        return UNKNOWN
    return text


def parse_occupation(value: str | None) -> str:
    text = normalize_text(value)
    if not text:
        return UNKNOWN
    if "法人" in text or "団体" in text:
        return "法人・団体"
    if text in {"不明", "その他", "なし", "被害者なし"}:
        return UNKNOWN
    return text


def parse_age_number(value: str | None) -> int | None:
    text = normalize_text(value)
    if not text:
        return None
    if "法人" in text or "団体" in text or "被害者なし" in text:
        return None

    m = re.search(r"(\d+)\s*歳代", text)
    if m:
        return int(m.group(1))

    m = re.search(r"(\d+)\s*歳以上", text)
    if m:
        return int(m.group(1))

    m = re.search(r"(\d+)\s*[\-~〜]\s*(\d+)\s*歳", text)
    if m:
        lo = int(m.group(1))
        hi = int(m.group(2))
        return (lo + hi) // 2

    m = re.search(r"(\d+)\s*歳", text)
    if m:
        return int(m.group(1))

    m = re.search(r"\b(\d{1,3})\b", text)
    if m:
        return int(m.group(1))

    return None


def age_bin(age: int | None) -> str:
    if age is None or age < 0:
        return UNKNOWN
    if age >= 100:
        return "100+"
    lo = (age // 10) * 10
    hi = lo + 9
    return f"{lo}-{hi}"


def parse_crime(value: str | None) -> str:
    text = normalize_text(value)
    return text if text else UNKNOWN


def parse_lock_value(values: list[str]) -> str:
    vals = [normalize_text(v) for v in values if normalize_text(v)]
    if not vals:
        return "情報なし"
    return " | ".join(vals)


def ratio_dict(counter: Counter, digits: int = 4) -> dict[str, float]:
    total = sum(counter.values())
    if total <= 0:
        return {}
    return {k: round(v / total, digits) for k, v in counter.most_common()}


def choose_delimiter(sample: str) -> str:
    comma_count = sample.count(",")
    tab_count = sample.count("\t")
    if tab_count > comma_count:
        return "\t"
    return ","


def try_open_dict_reader(path: Path) -> tuple[csv.DictReader, object, str] | tuple[None, None, None]:
    for enc in ENCODINGS:
        try:
            f = path.open("r", encoding=enc, newline="")
            sample = f.read(4096)
            f.seek(0)
            delimiter = choose_delimiter(sample)
            reader = csv.DictReader(f, delimiter=delimiter)
            if reader.fieldnames:
                if len(reader.fieldnames) == 1 and "\t" in (reader.fieldnames[0] or ""):
                    f.close()
                    f = path.open("r", encoding=enc, newline="")
                    reader = csv.DictReader(f, delimiter="\t")
                return reader, f, enc
            f.close()
        except Exception:
            continue
    return None, None, None


def main() -> None:
    csv_paths = sorted(DATA_DIR.rglob("*.csv"))

    age_counter = Counter()
    gender_counter = Counter()
    occupation_counter = Counter()
    lock_counter = Counter()

    pref_age_values = defaultdict(list)
    pref_gender_counter = defaultdict(Counter)
    pref_occ_counter = defaultdict(Counter)
    pref_lock_counter = defaultdict(Counter)

    crime_age_counter = defaultdict(Counter)
    crime_gender_counter = defaultdict(Counter)
    crime_age_gender_counter = defaultdict(Counter)
    crime_lock_counter = defaultdict(Counter)

    combo_counter = Counter()  # (age_bin, gender, crime)
    combo_base_counter = Counter()  # (age_bin, gender)
    crime_counter = Counter()

    files_processed = 0
    rows_processed = 0
    rows_with_victim_attr = 0
    rows_with_lock_attr = 0
    failed_files = []

    detected_column_patterns = {
        "age": Counter(),
        "gender": Counter(),
        "occupation": Counter(),
        "prefecture": Counter(),
        "crime": Counter(),
        "lock": Counter(),
    }

    for path in csv_paths:
        reader, fh, used_encoding = try_open_dict_reader(path)
        if reader is None or fh is None:
            failed_files.append(str(path))
            continue

        headers = [h for h in (reader.fieldnames or []) if h is not None]
        cols = detect_columns(headers)
        age_col = cols["age"]
        gender_col = cols["gender"]
        occupation_col = cols["occupation"]
        prefecture_col = cols["prefecture"]
        crime_col = cols["crime"]
        lock_cols = cols["lock_cols"] or []

        if age_col:
            detected_column_patterns["age"][age_col] += 1
        if gender_col:
            detected_column_patterns["gender"][gender_col] += 1
        if occupation_col:
            detected_column_patterns["occupation"][occupation_col] += 1
        if prefecture_col:
            detected_column_patterns["prefecture"][prefecture_col] += 1
        if crime_col:
            detected_column_patterns["crime"][crime_col] += 1
        for lc in lock_cols:
            detected_column_patterns["lock"][lc] += 1

        files_processed += 1
        for row in reader:
            rows_processed += 1

            prefecture = parse_prefecture(row.get(prefecture_col), path) if prefecture_col else infer_prefecture_from_path(path)

            crime = parse_crime(row.get(crime_col)) if crime_col else UNKNOWN
            age_num = parse_age_number(row.get(age_col)) if age_col else None
            age_bucket = age_bin(age_num)
            gender = parse_gender(row.get(gender_col)) if gender_col else UNKNOWN
            occupation = parse_occupation(row.get(occupation_col)) if occupation_col else UNKNOWN

            lock_values = [row.get(c, "") for c in lock_cols]
            lock_status = parse_lock_value(lock_values)
            has_lock_info = bool(lock_cols) and lock_status != "情報なし"

            has_victim = any(
                [
                    age_col and normalize_text(row.get(age_col)),
                    gender_col and normalize_text(row.get(gender_col)),
                    occupation_col and normalize_text(row.get(occupation_col)),
                ]
            )
            if has_victim:
                rows_with_victim_attr += 1
            if has_lock_info:
                rows_with_lock_attr += 1

            age_counter[age_bucket] += 1
            gender_counter[gender] += 1
            occupation_counter[occupation] += 1

            if has_lock_info:
                lock_counter[lock_status] += 1

            pref_age_values[prefecture].append(age_num) if age_num is not None else None
            pref_gender_counter[prefecture][gender] += 1
            pref_occ_counter[prefecture][occupation] += 1
            if has_lock_info:
                pref_lock_counter[prefecture][lock_status] += 1

            crime_age_counter[crime][age_bucket] += 1
            crime_gender_counter[crime][gender] += 1
            crime_age_gender_counter[crime][f"{age_bucket}|{gender}"] += 1
            if has_lock_info:
                crime_lock_counter[crime][lock_status] += 1

            combo_counter[(age_bucket, gender, crime)] += 1
            combo_base_counter[(age_bucket, gender)] += 1
            crime_counter[crime] += 1

        fh.close()

    age_distribution = dict(
        sorted(age_counter.items(), key=lambda kv: (999 if kv[0] == UNKNOWN else int(kv[0].split("-")[0]) if "-" in kv[0] else 1000))
    )

    occupation_top20 = [
        {"occupation": k, "count": v}
        for k, v in occupation_counter.most_common(20)
    ]

    pref_profile = {}
    for pref in sorted(pref_gender_counter.keys()):
        ages = pref_age_values.get(pref, [])
        age_med = round(float(median(ages)), 2) if ages else None
        occ_top = pref_occ_counter[pref].most_common(1)
        lock_top = pref_lock_counter[pref].most_common(1)
        pref_profile[pref] = {
            "age_median": age_med,
            "gender_ratio": ratio_dict(pref_gender_counter[pref]),
            "most_common_occupation": occ_top[0][0] if occ_top else UNKNOWN,
            "most_common_lock_status": lock_top[0][0] if lock_top else "情報なし",
        }

    crime_cross = {}
    for crime in sorted(crime_counter.keys()):
        crime_cross[crime] = {
            "total": crime_counter[crime],
            "age_distribution": dict(crime_age_counter[crime].most_common()),
            "gender_distribution": dict(crime_gender_counter[crime].most_common()),
            "age_gender_distribution": dict(crime_age_gender_counter[crime].most_common()),
            "lock_distribution": dict(crime_lock_counter[crime].most_common()),
        }

    total_rows = sum(crime_counter.values())
    vulnerability = []
    min_combo_count = 10
    for (ab, g, c), cnt in combo_counter.items():
        combo_total = combo_base_counter[(ab, g)]
        if cnt < min_combo_count or combo_total <= 0 or total_rows <= 0:
            continue

        combo_crime_rate = cnt / combo_total
        overall_crime_rate = crime_counter[c] / total_rows if total_rows else 0.0
        if overall_crime_rate <= 0:
            continue
        multiplier = combo_crime_rate / overall_crime_rate

        vulnerability.append(
            {
                "age_group": ab,
                "gender": g,
                "crime": c,
                "count": cnt,
                "combo_total": combo_total,
                "overall_crime_count": crime_counter[c],
                "combo_crime_rate": round(combo_crime_rate, 6),
                "overall_crime_rate": round(overall_crime_rate, 6),
                "multiplier": round(multiplier, 4),
            }
        )

    vulnerability.sort(key=lambda x: (x["multiplier"], x["count"]), reverse=True)

    output = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "input_root": str(DATA_DIR),
            "output_path": str(OUTPUT_PATH),
            "files_processed": files_processed,
            "rows_processed": rows_processed,
            "rows_with_victim_attributes": rows_with_victim_attr,
            "rows_with_lock_attributes": rows_with_lock_attr,
            "failed_files": failed_files,
            "detected_columns": {
                k: dict(v.most_common()) for k, v in detected_column_patterns.items()
            },
            "encodings_tried": ENCODINGS,
            "vulnerability_formula": "multiplier = P(crime | age_group,gender) / P(crime)",
            "minimum_combo_count": min_combo_count,
        },
        "age_distribution": age_distribution,
        "gender_ratio": ratio_dict(gender_counter),
        "occupation_top20": occupation_top20,
        "prefecture_victim_profile": pref_profile,
        "crime_x_victim_cross": crime_cross,
        "vulnerability_scores": vulnerability,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Wrote: {OUTPUT_PATH}")
    print(f"Files: {files_processed}, Rows: {rows_processed}, Failed: {len(failed_files)}")


if __name__ == "__main__":
    main()
