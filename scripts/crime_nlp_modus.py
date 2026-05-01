#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ENCODINGS = ["utf-8-sig", "utf-8", "cp932", "shift_jis", "euc_jp"]
KEYWORDS = [
    "侵入",
    "ガラス破り",
    "ガラス",
    "ドア",
    "無施錠",
    "ピッキング",
    "窓",
    "施錠",
    "車上",
    "自転車",
    "オートバイ",
    "置引き",
    "ひったくり",
    "忍込み",
    "空き巣",
]


def normalize_value(value: str | None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def infer_prefecture(csv_path: Path) -> str | None:
    for part in csv_path.parts:
        if part == "北海道" or re.search(r"[都道府県]$", part):
            return part
    return None


def try_read_rows(csv_path: Path) -> tuple[list[dict[str, str]], str]:
    last_error = None
    for enc in ENCODINGS:
        try:
            with csv_path.open("r", encoding=enc, newline="") as f:
                rows = list(csv.DictReader(f))
            return rows, enc
        except UnicodeDecodeError as e:
            last_error = e
        except csv.Error as e:
            last_error = e
    raise RuntimeError(f"Failed to read {csv_path}: {last_error}")


def top_items(counter: Counter[str], limit: int) -> list[dict[str, int | str]]:
    return [{"value": k, "count": v} for k, v in counter.most_common(limit)]


def main() -> None:
    root = Path("data/crime")
    out_path = Path("docs/data/crime_modus_analysis.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    csv_files = sorted(root.rglob("*.csv"))

    national_modus = Counter()
    national_crime_type = Counter()
    cross_tab = Counter()
    prefecture_modus = defaultdict(Counter)
    keyword_counter = Counter()

    processed_files = 0
    processed_records = 0
    used_encodings = Counter()

    for csv_file in csv_files:
        try:
            rows, used_enc = try_read_rows(csv_file)
        except RuntimeError:
            continue

        processed_files += 1
        used_encodings[used_enc] += 1

        pref = infer_prefecture(csv_file)

        for row in rows:
            processed_records += 1

            modus = normalize_value(row.get("手口"))
            crime_type = normalize_value(row.get("罪名"))

            if modus:
                national_modus[modus] += 1
                if pref:
                    prefecture_modus[pref][modus] += 1

                for kw in KEYWORDS:
                    if kw in modus:
                        keyword_counter[kw] += 1

            if crime_type:
                national_crime_type[crime_type] += 1

            if modus and crime_type:
                cross_tab[(modus, crime_type)] += 1

    output = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_root": str(root),
            "output_path": str(out_path),
            "csv_files_found": len(csv_files),
            "csv_files_processed": processed_files,
            "records_processed": processed_records,
            "encoding_attempt_order": ENCODINGS,
            "encodings_used": dict(used_encodings),
            "keyword_list": KEYWORDS,
        },
        "national_modus_top100": top_items(national_modus, 100),
        "national_crime_type_top100": top_items(national_crime_type, 100),
        "prefecture_modus_top10": {
            pref: top_items(counter, 10)
            for pref, counter in sorted(prefecture_modus.items(), key=lambda x: x[0])
        },
        "cross_tab_top50": [
            {"modus": m, "crime_type": c, "count": n}
            for (m, c), n in cross_tab.most_common(50)
        ],
        "modus_keyword_analysis": top_items(keyword_counter, len(KEYWORDS)),
    }

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Processed files: {processed_files}/{len(csv_files)}")
    print(f"Processed records: {processed_records}")


if __name__ == "__main__":
    main()
