#!/usr/bin/env python3
"""Extract qualitative features from fushinsha incidents using regex rules."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = BASE_DIR / "data" / "realtime" / "fushinsha_7days" / "gaccom_full.json"
OUTPUT_PATH = BASE_DIR / "docs" / "data" / "qualitative_features.json"

CATEGORIES: Dict[str, Dict[str, str]] = {
    "victim_type": {
        "child_female": r"小学生女児|女子小学生|女子児童",
        "child_male": r"小学生男児|男子小学生|男子児童",
        "child": r"児童|子ども|子供|園児|幼児",
        "jhs_female": r"女子中学生|中学生女子",
        "jhs_male": r"男子中学生|中学生男子",
        "hs_female": r"女子高校生|高校生女子|女子高生",
        "hs_male": r"男子高校生|高校生男子|男子高生",
        "woman": r"女性|成人女性",
        "man": r"男性(?!が)|成人男性",
        "elderly": r"高齢者|お年寄り|老人|高齢女性|高齢男性",
    },
    "location_type": {
        "street": r"路上|道路上|歩道上|道路",
        "park": r"公園|緑地|広場",
        "station_train": r"駅|電車内|列車内|ホーム|改札",
        "convenience": r"コンビニ|コンビニエンスストア",
        "home": r"自宅|玄関|マンション|アパート|住宅",
        "school_route": r"通学路|スクールゾーン",
        "school": r"学校|校門|校庭",
        "parking": r"駐車場|駐輪場",
        "commercial": r"商業施設|ショッピング|スーパー|デパート|商店",
        "hospital": r"病院|クリニック|医院",
    },
    "modus_operandi": {
        "stalking": r"つきまとい|つきまとわ|後をつけ|尾行",
        "calling": r"声かけ|声をかけ|話しかけ|呼び止め",
        "groping": r"体を触|身体を触|触られ|痴漢",
        "weapon": r"包丁|刃物|ナイフ|凶器|刃物様|金属バット|鉄パイプ",
        "vehicle": r"車から|車両|車で|バイクで",
        "photography": r"撮影|スマートフォンを向け|カメラ|盗撮|写真",
        "intrusion": r"侵入|押し入|忍び込|不法侵入",
        "assault": r"暴行|殴|蹴|叩|押し倒|突き飛ば",
        "exposure": r"露出|下半身|陰部|裸",
        "threat": r"脅迫|脅し|殺す|金を出せ",
    },
    "temporal_context": {
        "after_school": r"下校中|下校途中|下校時|帰り道",
        "to_school": r"登校中|登校途中|通学中",
        "commute_home": r"帰宅途中|帰宅中",
        "commute_work": r"通勤中|通勤途中|出勤",
        "sleeping": r"就寝中|睡眠中",
        "shopping": r"買い物中|買い物帰り",
    },
    "environmental_risk": {
        "alone": r"一人歩き|一人で歩|独り歩き|ひとり歩き|1人で",
        "dark": r"暗い|暗がり|街灯のない|照明が少ない",
        "nighttime": r"夜間|深夜|未明|午前[0-3]時",
        "deserted": r"人通りの少ない|人けのない|人気のない",
    },
}


def compile_patterns() -> Dict[str, List[Tuple[str, re.Pattern[str]]]]:
    compiled: Dict[str, List[Tuple[str, re.Pattern[str]]]] = {}
    for category, mapping in CATEGORIES.items():
        compiled[category] = [(key, re.compile(pattern)) for key, pattern in mapping.items()]
    return compiled


def extract_matches(text: str, compiled: Dict[str, List[Tuple[str, re.Pattern[str]]]]) -> Dict[str, List[str]]:
    result: Dict[str, List[str]] = {}
    for category, pairs in compiled.items():
        matched = [name for name, pat in pairs if pat.search(text)]
        result[category] = matched
    return result


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def calc_severity_adj(matches: Dict[str, List[str]]) -> float:
    victim = set(matches["victim_type"])
    modus = set(matches["modus_operandi"])
    env = set(matches["environmental_risk"])

    total = 0.0
    has_child = any(v.startswith("child") or v.startswith("jhs") or v.startswith("hs") for v in victim)
    has_female = any(v in {"woman", "child_female", "jhs_female", "hs_female"} for v in victim)

    if has_child:
        total += 0.3
    if has_female and "alone" in env:
        total += 0.2
    if "weapon" in modus:
        total += 0.5
    if "exposure" in modus:
        total += 0.1
    if "assault" in modus:
        total += 0.4
    if "intrusion" in modus:
        total += 0.3
    if "nighttime" in env and "dark" in env:
        total += 0.2
    if "deserted" in env:
        total += 0.15

    return round(clip(total, 0.0, 1.0), 4)


def calc_multiplier(matches: Dict[str, List[str]]) -> float:
    victim = set(matches["victim_type"])
    location = set(matches["location_type"])
    env = set(matches["environmental_risk"])

    has_child = any(v.startswith("child") or v.startswith("jhs") or v.startswith("hs") for v in victim)

    mult = 1.0
    if "alone" in env:
        mult *= 1.15
    if "nighttime" in env:
        mult *= 1.10
    if "dark" in env:
        mult *= 1.10
    if "deserted" in env:
        mult *= 1.20
    if "school_route" in location and has_child:
        mult *= 1.25
    if "station_train" in location:
        mult *= 0.90
    if "convenience" in location:
        mult *= 0.85

    return round(clip(mult, 0.7, 2.0), 4)


def dominant_or_unknown(values: Iterable[str]) -> str:
    counter = Counter(values)
    return counter.most_common(1)[0][0] if counter else "unknown"


def main() -> int:
    try:
        print(f"[1/4] Loading incidents: {INPUT_PATH}")
        with INPUT_PATH.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        incidents = payload.get("incidents", [])
        if not isinstance(incidents, list):
            raise ValueError("Invalid input schema: incidents must be a list")

        print(f"[2/4] Extracting qualitative features for {len(incidents):,} incidents")
        compiled = compile_patterns()

        extracted: List[Dict[str, object]] = []
        summary_counters: Dict[str, Counter[str]] = {k: Counter() for k in CATEGORIES}

        total = len(incidents)
        for idx, incident in enumerate(incidents, start=1):
            title = str(incident.get("title") or "")
            description = str(incident.get("description") or "")
            full_description = str(incident.get("full_description") or "")
            text = "\n".join([title, description, full_description])

            matches = extract_matches(text, compiled)
            severity_adj = calc_severity_adj(matches)
            multiplier = calc_multiplier(matches)

            for category, labels in matches.items():
                summary_counters[category].update(labels)

            extracted.append(
                {
                    "id": incident.get("id"),
                    "prefecture": incident.get("prefecture"),
                    "city": incident.get("city"),
                    "date": incident.get("date"),
                    "lat": incident.get("lat"),
                    "lng": incident.get("lng"),
                    "matched": matches,
                    "dominant_victim_type": dominant_or_unknown(matches["victim_type"]),
                    "dominant_location_type": dominant_or_unknown(matches["location_type"]),
                    "dominant_modus_operandi": dominant_or_unknown(matches["modus_operandi"]),
                    "qualitative_severity_adj": severity_adj,
                    "qualitative_risk_multiplier": multiplier,
                }
            )

            if idx % 1000 == 0 or idx == total:
                print(f"  processed {idx:,}/{total:,}")

        print(f"[3/4] Writing output: {OUTPUT_PATH}")
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        output = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": str(INPUT_PATH),
                "output": str(OUTPUT_PATH),
                "total_incidents": len(extracted),
                "schema_version": "1.0.0",
            },
            "summary_counts": {k: dict(v) for k, v in summary_counters.items()},
            "incidents": extracted,
        }
        with OUTPUT_PATH.open("w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print("[4/4] Done")
        return 0
    except FileNotFoundError as exc:
        print(f"ERROR: input file not found: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pylint: disable=broad-except
        print(f"ERROR: unexpected failure: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
