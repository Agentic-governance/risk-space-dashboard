#!/usr/bin/env python3
"""Fix Step 1 parsing based on actual JASPIC title format."""

import json
import re
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "data", "realtime", "jaspic_analysis")

# Real JASPIC title format: （都道府県略称）市区町村名で種別　日付
# e.g. （兵庫）尼崎市武庫之荘東１丁目で声かけ　３月２７日
# e.g. （北海道）恵庭市で痴漢　３月２３日
# e.g. （神奈川）横浜市保土ケ谷区宮田町１丁目で声かけ　４月１日

PREF_ABBREV_MAP = {
    "北海道": "北海道", "青森": "青森県", "岩手": "岩手県", "宮城": "宮城県",
    "秋田": "秋田県", "山形": "山形県", "福島": "福島県",
    "茨城": "茨城県", "栃木": "栃木県", "群馬": "群馬県", "埼玉": "埼玉県",
    "千葉": "千葉県", "東京": "東京都", "神奈川": "神奈川県",
    "新潟": "新潟県", "富山": "富山県", "石川": "石川県", "福井": "福井県",
    "山梨": "山梨県", "長野": "長野県",
    "岐阜": "岐阜県", "静岡": "静岡県", "愛知": "愛知県", "三重": "三重県",
    "滋賀": "滋賀県", "京都": "京都府", "大阪": "大阪府", "兵庫": "兵庫県",
    "奈良": "奈良県", "和歌山": "和歌山県",
    "鳥取": "鳥取県", "島根": "島根県", "岡山": "岡山県", "広島": "広島県", "山口": "山口県",
    "徳島": "徳島県", "香川": "香川県", "愛媛": "愛媛県", "高知": "高知県",
    "福岡": "福岡県", "佐賀": "佐賀県", "長崎": "長崎県", "熊本": "熊本県",
    "大分": "大分県", "宮崎": "宮崎県", "鹿児島": "鹿児島県", "沖縄": "沖縄県",
}

KIND_PATTERNS = [
    "声かけ", "つきまとい", "付きまとい", "痴漢", "わいせつ", "盗撮", "強盗", "暴行",
    "刃物所持", "不審者", "露出", "のぞき", "ひったくり", "すり",
    "クマ出没", "イノシシ出没", "サル出没", "シカ出没",
    "空き巣", "車上ねらい", "車上荒らし", "自転車盗", "オレオレ詐欺", "還付金詐欺",
    "特殊詐欺", "架空請求", "窃盗", "侵入盗", "万引き",
    "公然わいせつ", "器物損壊", "不審車両", "不審電話",
    "写真撮影", "容姿撮影", "暴言", "チカン",
]


def parse_jaspic_title(title):
    """Parse real JASPIC title format: （都道府県略称）場所で種別　日付"""
    result = {"raw_title": title, "prefecture": None, "prefecture_abbrev": None,
              "city": None, "kind": None, "location_detail": None}

    # Extract prefecture abbreviation from （）
    pref_match = re.search(r'[（(]([^）)]+)[）)]', title)
    if pref_match:
        abbrev = pref_match.group(1)
        result["prefecture_abbrev"] = abbrev
        result["prefecture"] = PREF_ABBREV_MAP.get(abbrev, abbrev)

    # Extract kind from title text
    for kp in KIND_PATTERNS:
        if kp in title:
            result["kind"] = kp
            break

    # Extract city
    after_paren = re.sub(r'^[（(][^）)]+[）)]', '', title).strip()
    city_match = re.match(r'(\S+?(?:市|区|町|村))', after_paren)
    if city_match:
        result["city"] = city_match.group(1)

    # Extract location detail (everything between pref and kind)
    if result["kind"]:
        loc_match = re.search(r'[）)](.+?)(?:で|にて)?' + re.escape(result["kind"]), title)
        if loc_match:
            result["location_detail"] = loc_match.group(1).strip()

    return result


def parse_jaspic_body(body_text):
    """Extract structured data from JASPIC article body."""
    result = {}

    # Full-width numeral conversion
    fw_to_hw = str.maketrans('０１２３４５６７８９', '0123456789')
    normalized = body_text.translate(fw_to_hw)

    # Date: ３月２７日 or 2026年3月27日
    date_match = re.search(r'(\d{1,2})月(\d{1,2})日', normalized)
    if date_match:
        month = int(date_match.group(1))
        day = int(date_match.group(2))
        year = 2026 if month <= 12 else 2025
        result["date"] = f"{year}-{month:02d}-{day:02d}"

    # Time: 午後５時３０分 or 午前１１時
    time_match = re.search(r'(午前|午後)(\d{1,2})時(\d{1,2})?分?', normalized)
    if time_match:
        hour = int(time_match.group(2))
        minute = int(time_match.group(3)) if time_match.group(3) else 0
        if time_match.group(1) == "午後" and hour < 12:
            hour += 12
        elif time_match.group(1) == "午前" and hour == 12:
            hour = 0
        result["time"] = f"{hour:02d}:{minute:02d}"

    # Also try HH:MM format
    if "time" not in result:
        t2 = re.search(r'(\d{1,2}):(\d{2})', normalized)
        if t2:
            result["time"] = f"{int(t2.group(1)):02d}:{t2.group(2)}"

    # Perpetrator characteristics
    perp_match = re.search(r'実行者の特徴[：:](.+?)(?:[）)]|\n)', body_text)
    if perp_match:
        result["perpetrator_description"] = perp_match.group(1).strip()

    # Situation
    situation_parts = []
    for line in body_text.split('\n'):
        line = line.strip()
        if line.startswith('・') and not line.startswith('・http'):
            situation_parts.append(line[1:].strip())
    if situation_parts:
        result["situation_details"] = situation_parts

    # Nearby facilities
    facility_match = re.search(r'現場付近の施設\n((?:・.+\n?)+)', body_text)
    if facility_match:
        facilities = [l.strip()[1:].strip() for l in facility_match.group(1).split('\n') if l.strip().startswith('・')]
        result["nearby_facilities"] = facilities

    return result


def main():
    # Load existing samples
    schema_path = os.path.join(OUT_DIR, "schema_samples.json")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_data = json.load(f)

    # Re-parse all samples
    kind_counts = {}
    prefecture_counts = {}
    fixed_samples = []

    for sample in schema_data["samples"]:
        title = sample.get("raw_title", "")
        body = sample.get("body_snippet", "")

        # Re-parse title
        parsed_title = parse_jaspic_title(title)
        # Re-parse body
        parsed_body = parse_jaspic_body(body)

        fixed = {**sample, **parsed_title, **parsed_body}
        fixed_samples.append(fixed)

        if fixed.get("kind"):
            kind_counts[fixed["kind"]] = kind_counts.get(fixed["kind"], 0) + 1
        if fixed.get("prefecture"):
            prefecture_counts[fixed["prefecture"]] = prefecture_counts.get(fixed["prefecture"], 0) + 1

    schema_data["samples"] = fixed_samples
    schema_data["kind_distribution"] = kind_counts
    schema_data["prefecture_coverage"] = prefecture_counts
    schema_data["title_format_actual"] = "（都道府県略称）市区町村名＋場所で種別　月日[解決]"
    schema_data["body_structure"] = {
        "line_1": "XX県警によると、日時、場所で、被害者への種別が発生しました。（実行者の特徴：...）",
        "section_situation": "■発生時の状況（bulleted list）",
        "section_facilities": "■現場付近の施設（bulleted list）",
        "section_other": "■その他（解決情報など）",
    }
    schema_data["fixed_at"] = datetime.now().isoformat()

    with open(schema_path, "w", encoding="utf-8") as f:
        json.dump(schema_data, f, ensure_ascii=False, indent=2)

    # Build kind taxonomy
    kind_taxonomy = {}
    all_kinds = sorted(set(list(kind_counts.keys()) + KIND_PATTERNS))
    for kind_name in all_kinds:
        cat = _categorize_kind(kind_name)
        kind_taxonomy[kind_name] = {
            "category": cat,
            "count_in_sample": kind_counts.get(kind_name, 0),
            "layer": "crime" if cat != "wildlife" else "disaster",
        }

    taxonomy_path = os.path.join(OUT_DIR, "kind_taxonomy.json")
    with open(taxonomy_path, "w", encoding="utf-8") as f:
        json.dump(kind_taxonomy, f, ensure_ascii=False, indent=2)

    print("Fixed JASPIC analysis:")
    print(f"  Kind distribution: {json.dumps(kind_counts, ensure_ascii=False)}")
    print(f"  Prefecture coverage: {json.dumps(prefecture_counts, ensure_ascii=False)}")
    print(f"  Samples with kind: {sum(1 for s in fixed_samples if s.get('kind'))}/{len(fixed_samples)}")
    print(f"  Samples with prefecture: {sum(1 for s in fixed_samples if s.get('prefecture'))}/{len(fixed_samples)}")
    print(f"  Samples with date: {sum(1 for s in fixed_samples if s.get('date'))}/{len(fixed_samples)}")
    print(f"  Samples with time: {sum(1 for s in fixed_samples if s.get('time'))}/{len(fixed_samples)}")


def _categorize_kind(kind):
    person_kinds = ["声かけ", "つきまとい", "付きまとい", "痴漢", "わいせつ", "盗撮", "不審者", "露出", "のぞき", "公然わいせつ", "写真撮影", "容姿撮影", "チカン"]
    violent_kinds = ["強盗", "暴行", "刃物所持", "ひったくり", "暴言"]
    property_kinds = ["空き巣", "車上ねらい", "車上荒らし", "自転車盗", "すり", "窃盗", "侵入盗", "万引き", "器物損壊"]
    fraud_kinds = ["オレオレ詐欺", "還付金詐欺", "特殊詐欺", "架空請求"]
    wildlife_kinds = ["クマ出没", "イノシシ出没", "サル出没", "シカ出没"]
    if kind in person_kinds: return "suspicious_person"
    if kind in violent_kinds: return "violent_crime"
    if kind in property_kinds: return "property_crime"
    if kind in fraud_kinds: return "fraud"
    if kind in wildlife_kinds: return "wildlife"
    if "不審車両" in kind: return "suspicious_vehicle"
    if "不審電話" in kind: return "suspicious_phone"
    return "other"


if __name__ == "__main__":
    main()
