#!/usr/bin/env python3
"""
Build comprehensive crime statistics from existing e-Stat data files.

Combines:
  - estat_2024_crime_traffic.json: K4201 + 5 subtypes + traffic, 47 prefs, 2023-2024
  - estat_2023_crime.json: K4201 + 3 subtypes, 47 prefs, 2022-2023
  - estat_crime_pref.json: NPA Table 3, partial (刑法犯総数 by pref, 2006-2016)
  - estat_theft_pref.json: NPA Table 4, partial (窃盗犯 by pref, 2006-2016)

Output:
  - data/crime/national/estat_crime_full.json
  - data/crime/national/pref_centroids.json
  - data/crime/national/estat_crime_summary.json (pivot summary)
"""

import json
import os
from pathlib import Path
from collections import defaultdict
from typing import Optional, List, Dict

BASE = Path(__file__).resolve().parent.parent
CRIME_DIR = BASE / "data" / "crime"
OUT_DIR = CRIME_DIR / "national"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── Prefecture master data ────────────────────────────────────────
PREFECTURES = {
    "01": {"name": "北海道", "lat": 43.0642, "lon": 141.3469},
    "02": {"name": "青森県", "lat": 40.8244, "lon": 140.7400},
    "03": {"name": "岩手県", "lat": 39.7036, "lon": 141.1527},
    "04": {"name": "宮城県", "lat": 38.2688, "lon": 140.8721},
    "05": {"name": "秋田県", "lat": 39.7186, "lon": 140.1024},
    "06": {"name": "山形県", "lat": 38.2405, "lon": 140.3633},
    "07": {"name": "福島県", "lat": 37.7503, "lon": 140.4676},
    "08": {"name": "茨城県", "lat": 36.3418, "lon": 140.4468},
    "09": {"name": "栃木県", "lat": 36.5657, "lon": 139.8836},
    "10": {"name": "群馬県", "lat": 36.3911, "lon": 139.0608},
    "11": {"name": "埼玉県", "lat": 35.8570, "lon": 139.6489},
    "12": {"name": "千葉県", "lat": 35.6047, "lon": 140.1233},
    "13": {"name": "東京都", "lat": 35.6895, "lon": 139.6917},
    "14": {"name": "神奈川県", "lat": 35.4478, "lon": 139.6425},
    "15": {"name": "新潟県", "lat": 37.9026, "lon": 139.0236},
    "16": {"name": "富山県", "lat": 36.6953, "lon": 137.2114},
    "17": {"name": "石川県", "lat": 36.5946, "lon": 136.6256},
    "18": {"name": "福井県", "lat": 36.0652, "lon": 136.2219},
    "19": {"name": "山梨県", "lat": 35.6642, "lon": 138.5684},
    "20": {"name": "長野県", "lat": 36.2325, "lon": 138.1813},
    "21": {"name": "岐阜県", "lat": 35.3912, "lon": 136.7223},
    "22": {"name": "静岡県", "lat": 34.9769, "lon": 138.3831},
    "23": {"name": "愛知県", "lat": 35.1802, "lon": 136.9066},
    "24": {"name": "三重県", "lat": 34.7303, "lon": 136.5086},
    "25": {"name": "滋賀県", "lat": 35.0045, "lon": 135.8686},
    "26": {"name": "京都府", "lat": 35.0214, "lon": 135.7556},
    "27": {"name": "大阪府", "lat": 34.6864, "lon": 135.5200},
    "28": {"name": "兵庫県", "lat": 34.6913, "lon": 135.1830},
    "29": {"name": "奈良県", "lat": 34.6851, "lon": 135.8329},
    "30": {"name": "和歌山県", "lat": 34.2260, "lon": 135.1675},
    "31": {"name": "鳥取県", "lat": 35.5036, "lon": 134.2383},
    "32": {"name": "島根県", "lat": 35.4723, "lon": 133.0505},
    "33": {"name": "岡山県", "lat": 34.6618, "lon": 133.9344},
    "34": {"name": "広島県", "lat": 34.3963, "lon": 132.4596},
    "35": {"name": "山口県", "lat": 34.1861, "lon": 131.4705},
    "36": {"name": "徳島県", "lat": 34.0658, "lon": 134.5593},
    "37": {"name": "香川県", "lat": 34.3401, "lon": 134.0434},
    "38": {"name": "愛媛県", "lat": 33.8416, "lon": 132.7657},
    "39": {"name": "高知県", "lat": 33.5597, "lon": 133.5311},
    "40": {"name": "福岡県", "lat": 33.6064, "lon": 130.4183},
    "41": {"name": "佐賀県", "lat": 33.2494, "lon": 130.2988},
    "42": {"name": "長崎県", "lat": 32.7448, "lon": 129.8737},
    "43": {"name": "熊本県", "lat": 32.7898, "lon": 130.7417},
    "44": {"name": "大分県", "lat": 33.2382, "lon": 131.6126},
    "45": {"name": "宮崎県", "lat": 31.9111, "lon": 131.4239},
    "46": {"name": "鹿児島県", "lat": 31.5602, "lon": 130.5581},
    "47": {"name": "沖縄県", "lat": 26.3344, "lon": 127.8056},
}

# ─── e-Stat category code → crime type/subtype mapping ─────────────
CATEGORY_MAP = {
    "K4201":   {"crime_type": "刑法犯", "subtype": "総数"},
    "K420101": {"crime_type": "凶悪犯", "subtype": "総数"},
    "K420102": {"crime_type": "粗暴犯", "subtype": "総数"},
    "K420103": {"crime_type": "窃盗犯", "subtype": "総数"},
    "K420104": {"crime_type": "知能犯", "subtype": "総数"},
    "K420105": {"crime_type": "風俗犯", "subtype": "総数"},
    # Traffic (included for completeness)
    "K3101":   {"crime_type": "交通事故", "subtype": "発生件数"},
    "K3103":   {"crime_type": "交通事故", "subtype": "死者数"},
    "K3104":   {"crime_type": "交通事故", "subtype": "負傷者数"},
}

# ─── Subtype breakdowns (national proportions from police white paper 2023) ──
# These are used to estimate prefecture-level subtypes from the major category totals
# Source: 令和5年版 犯罪白書 / 警察庁犯罪統計 2023
SUBTYPE_RATIOS = {
    "凶悪犯": {
        "殺人": 0.145,       # ~830 / 5750
        "強盗": 0.277,       # ~1590 / 5750
        "放火": 0.149,       # ~860 / 5750
        "強制性交等": 0.429, # ~2470 / 5750
    },
    "粗暴犯": {
        "暴行": 0.500,       # ~29200 / 58474
        "傷害": 0.374,       # ~21870 / 58474
        "脅迫": 0.076,       # ~4450 / 58474
        "恐喝": 0.025,       # ~1470 / 58474
        "凶器準備集合": 0.025, # remainder
    },
    "窃盗犯": {
        "侵入窃盗": 0.103,   # ~49800 / 483695
        "乗り物盗": 0.177,    # ~85600 / 483695
        "非侵入窃盗": 0.720,  # ~348300 / 483695
    },
    "知能犯": {
        "詐欺": 0.816,       # ~40800 / 50035
        "横領": 0.065,       # ~3250 / 50035
        "偽造": 0.044,       # ~2200 / 50035
        "汚職": 0.005,       # ~250 / 50035
        "あっせん利得処罰法": 0.000,
        "背任": 0.070,       # remainder
    },
    "風俗犯": {
        "賭博": 0.034,       # ~400 / 11774
        "わいせつ": 0.966,    # ~11374 / 11774
    },
}

# ─── "その他の刑法犯" calculation ──────────────────────────────────
# 刑法犯総数 = 凶悪犯 + 粗暴犯 + 窃盗犯 + 知能犯 + 風俗犯 + その他
# So その他 = 総数 - (凶悪 + 粗暴 + 窃盗 + 知能 + 風俗)

# Subtypes for その他 (national ratios, 2023 police stats)
# その他の刑法犯 ~93,623 in 2023
OTHER_SUBTYPE_RATIOS = {
    "器物損壊": 0.710,      # ~66,500
    "住居侵入": 0.105,      # ~9,800
    "公務執行妨害": 0.035,  # ~3,300
    "占有離脱物横領": 0.080, # ~7,500
    "その他": 0.070,         # ~6,500
}


def estat_area_to_pref_code(area_code: str) -> Optional[str]:
    """Convert e-Stat area code (e.g. '13000') to JIS prefecture code ('13')."""
    if not area_code or len(area_code) != 5:
        return None
    prefix = area_code[:2]
    if prefix in PREFECTURES:
        return prefix
    return None


def parse_estat_values(filepath: str) -> List[Dict]:
    """Parse an e-Stat JSON file into structured records."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    sd = data.get("GET_STATS_DATA", {})
    if sd.get("RESULT", {}).get("STATUS", -1) != 0:
        return []

    stats = sd.get("STATISTICAL_DATA", {})
    values = stats.get("DATA_INF", {}).get("VALUE", [])

    # Build lookup for class labels
    class_objs = stats.get("CLASS_INF", {}).get("CLASS_OBJ", [])
    lookups = {}
    for co in class_objs:
        dim_id = co.get("@id", "")
        classes = co.get("CLASS", [])
        if isinstance(classes, dict):
            classes = [classes]
        lookups[dim_id] = {c["@code"]: c["@name"] for c in classes}

    records = []
    for v in values:
        cat01 = v.get("@cat01", "")
        area = v.get("@area", "")
        time_code = v.get("@time", "")
        val_str = v.get("$", "")

        # Skip national totals
        pref_code = estat_area_to_pref_code(area)
        if not pref_code:
            continue

        # Parse year from time code (e.g. "2023100000" → 2023, "2016000000" → 2016)
        year = None
        if len(time_code) >= 4:
            try:
                year = int(time_code[:4])
            except ValueError:
                continue
        if not year:
            continue

        # Parse value
        try:
            count = int(val_str)
        except (ValueError, TypeError):
            try:
                count = int(float(val_str))
            except:
                continue

        # Map category
        cat_info = CATEGORY_MAP.get(cat01)
        if not cat_info:
            continue

        pref_name = PREFECTURES.get(pref_code, {}).get("name", "")
        records.append({
            "prefecture": pref_name,
            "prefecture_code": pref_code,
            "crime_type": cat_info["crime_type"],
            "subtype": cat_info["subtype"],
            "year": year,
            "count": count,
            "source": "e-Stat",
            "_cat01": cat01,
        })

    return records


def parse_npa_table(filepath: str, cat01_filter: str = "100") -> List[Dict]:
    """Parse NPA crime stats table (Table 3/4) - only 認知件数 (cat01=100)."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    sd = data.get("GET_STATS_DATA", {})
    if sd.get("RESULT", {}).get("STATUS", -1) != 0:
        return []

    stats = sd.get("STATISTICAL_DATA", {})
    values = stats.get("DATA_INF", {}).get("VALUE", [])
    title = stats.get("TABLE_INF", {}).get("TITLE", "")

    # Determine crime type from title
    is_theft = "窃盗" in (title if isinstance(title, str) else str(title))
    crime_type = "窃盗犯" if is_theft else "刑法犯"

    records = []
    for v in values:
        cat01 = v.get("@cat01", "")
        if cat01 != cat01_filter:  # Only 認知件数
            continue

        area = v.get("@area", "")
        time_code = v.get("@time", "")
        val_str = v.get("$", "")

        pref_code = estat_area_to_pref_code(area)
        if not pref_code:
            continue

        year = None
        if len(time_code) >= 4:
            try:
                year = int(time_code[:4])
            except:
                continue
        if not year:
            continue

        try:
            count = int(val_str)
        except:
            continue

        pref_name = PREFECTURES.get(pref_code, {}).get("name", "")
        records.append({
            "prefecture": pref_name,
            "prefecture_code": pref_code,
            "crime_type": crime_type,
            "subtype": "総数",
            "year": year,
            "count": count,
            "source": "e-Stat (NPA)",
            "_cat01": cat01,
        })

    return records


def generate_subtypes(records: List[Dict]) -> List[Dict]:
    """Generate subtype breakdowns from major category totals using national ratios."""
    subtype_records = []

    for rec in records:
        ct = rec["crime_type"]
        if ct not in SUBTYPE_RATIOS and ct != "その他の刑法犯":
            continue
        if rec["subtype"] != "総数":
            continue

        ratios = SUBTYPE_RATIOS.get(ct, OTHER_SUBTYPE_RATIOS if ct == "その他の刑法犯" else {})
        for subtype_name, ratio in ratios.items():
            sub_count = max(0, round(rec["count"] * ratio))
            subtype_records.append({
                "prefecture": rec["prefecture"],
                "prefecture_code": rec["prefecture_code"],
                "crime_type": ct,
                "subtype": subtype_name,
                "year": rec["year"],
                "count": sub_count,
                "source": "e-Stat (estimated)",
            })

    return subtype_records


def compute_other_crimes(records: List[Dict]) -> List[Dict]:
    """Compute その他の刑法犯 = 刑法犯総数 - sum(5 categories)."""
    # Group by (pref, year)
    totals = {}  # (pref_code, year) -> total
    cats = defaultdict(int)  # (pref_code, year) -> sum of 5 categories

    for rec in records:
        key = (rec["prefecture_code"], rec["year"])
        if rec["crime_type"] == "刑法犯" and rec["subtype"] == "総数":
            totals[key] = rec["count"]
        elif rec["crime_type"] in ("凶悪犯", "粗暴犯", "窃盗犯", "知能犯", "風俗犯") and rec["subtype"] == "総数":
            cats[key] += rec["count"]

    other_records = []
    for key, total in totals.items():
        pref_code, year = key
        cat_sum = cats.get(key, 0)
        other_count = max(0, total - cat_sum)
        if other_count > 0:
            pref_name = PREFECTURES.get(pref_code, {}).get("name", "")
            other_records.append({
                "prefecture": pref_name,
                "prefecture_code": pref_code,
                "crime_type": "その他の刑法犯",
                "subtype": "総数",
                "year": year,
                "count": other_count,
                "source": "e-Stat (computed)",
            })
            # Also generate subtypes for その他
            for subtype_name, ratio in OTHER_SUBTYPE_RATIOS.items():
                sub_count = max(0, round(other_count * ratio))
                other_records.append({
                    "prefecture": pref_name,
                    "prefecture_code": pref_code,
                    "crime_type": "その他の刑法犯",
                    "subtype": subtype_name,
                    "year": year,
                    "count": sub_count,
                    "source": "e-Stat (estimated)",
                })

    return other_records


def deduplicate(records: List[Dict]) -> List[Dict]:
    """Deduplicate keeping the most recent/complete source."""
    # Priority: e-Stat > e-Stat (NPA) > e-Stat (computed) > e-Stat (estimated)
    priority = {
        "e-Stat": 0,
        "e-Stat (NPA)": 1,
        "e-Stat (computed)": 2,
        "e-Stat (estimated)": 3,
    }
    best = {}
    for rec in records:
        key = (rec["prefecture_code"], rec["crime_type"], rec["subtype"], rec["year"])
        p = priority.get(rec["source"], 99)
        if key not in best or p < priority.get(best[key]["source"], 99):
            best[key] = rec

    return sorted(best.values(), key=lambda r: (r["prefecture_code"], r["year"], r["crime_type"], r["subtype"]))


def main():
    print("=" * 60)
    print("Building comprehensive crime statistics from e-Stat data")
    print("=" * 60)

    all_records = []

    # ─── Source 1: estat_2024_crime_traffic.json (best source) ──
    f1 = CRIME_DIR / "estat_2024_crime_traffic.json"
    if f1.exists():
        recs = parse_estat_values(str(f1))
        print(f"[1] estat_2024_crime_traffic.json: {len(recs)} records")
        all_records.extend(recs)

    # ─── Source 2: estat_2023_crime.json ──
    f2 = CRIME_DIR / "estat_2023_crime.json"
    if f2.exists():
        recs = parse_estat_values(str(f2))
        print(f"[2] estat_2023_crime.json: {len(recs)} records")
        all_records.extend(recs)

    # ─── Source 3: NPA Table 3 (刑法犯総数 by pref) ──
    f3 = CRIME_DIR / "estat_crime_pref.json"
    if f3.exists():
        recs = parse_npa_table(str(f3))
        print(f"[3] estat_crime_pref.json (NPA Table 3): {len(recs)} records")
        all_records.extend(recs)

    # ─── Source 4: NPA Table 4 (窃盗犯 by pref) ──
    f4 = CRIME_DIR / "estat_theft_pref.json"
    if f4.exists():
        recs = parse_npa_table(str(f4))
        print(f"[4] estat_theft_pref.json (NPA Table 4): {len(recs)} records")
        all_records.extend(recs)

    # Deduplicate base records
    base_records = deduplicate(all_records)
    print(f"\nBase records after dedup: {len(base_records)}")

    # ─── Compute "その他の刑法犯" ──
    other_recs = compute_other_crimes(base_records)
    print(f"Generated その他の刑法犯 records: {len(other_recs)}")

    # ─── Generate subtype breakdowns ──
    # Only for records that have subtypes defined
    eligible = [r for r in base_records if r["crime_type"] in SUBTYPE_RATIOS and r["subtype"] == "総数"]
    sub_recs = generate_subtypes(eligible)
    print(f"Generated subtype records: {len(sub_recs)}")

    # ─── Combine all ──
    final = deduplicate(base_records + other_recs + sub_recs)

    # Remove internal fields
    for rec in final:
        rec.pop("_cat01", None)

    print(f"\n--- Final dataset ---")
    print(f"Total records: {len(final)}")

    # Summary stats
    years = sorted(set(r["year"] for r in final))
    prefs = sorted(set(r["prefecture_code"] for r in final))
    types = sorted(set(r["crime_type"] for r in final))
    print(f"Years: {min(years)}-{max(years)} ({len(years)} years)")
    print(f"Prefectures: {len(prefs)}")
    print(f"Crime types: {types}")

    # Check coverage for 2023
    recs_2023 = [r for r in final if r["year"] == 2023]
    total_2023 = sum(r["count"] for r in recs_2023 if r["crime_type"] == "刑法犯" and r["subtype"] == "総数")
    print(f"\n2023 total 刑法犯認知件数 (47 prefs): {total_2023:,}")
    print(f"2023 records: {len(recs_2023)}")

    # Per-type totals for 2023
    type_totals = defaultdict(int)
    for r in recs_2023:
        if r["subtype"] == "総数":
            type_totals[r["crime_type"]] += r["count"]
    print("\n2023 by crime type (総数):")
    for ct in sorted(type_totals.keys()):
        print(f"  {ct}: {type_totals[ct]:,}")

    # ─── Save main output ──
    out_path = OUT_DIR / "estat_crime_full.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {out_path} ({len(final)} records)")

    # ─── Save prefecture centroids ──
    centroids = []
    for code, info in sorted(PREFECTURES.items()):
        centroids.append({
            "prefecture": info["name"],
            "prefecture_code": code,
            "lat": info["lat"],
            "lon": info["lon"],
        })
    centroid_path = OUT_DIR / "pref_centroids.json"
    with open(centroid_path, "w", encoding="utf-8") as f:
        json.dump(centroids, f, ensure_ascii=False, indent=2)
    print(f"Saved: {centroid_path} ({len(centroids)} prefectures)")

    # ─── Save summary pivot ──
    summary = {
        "metadata": {
            "generated": "2026-04-03",
            "sources": [
                "e-Stat 社会・人口統計体系 (0000010111) K安全",
                "e-Stat 犯罪統計 NPA Table 3 (0003195002)",
                "e-Stat 犯罪統計 NPA Table 4 (0003194949)",
            ],
            "total_records": len(final),
            "years": years,
            "prefectures": len(prefs),
            "crime_types": types,
            "subtype_estimation_method": "National ratio proportional allocation from 犯罪白書 2023",
        },
        "yearly_totals": {},
    }
    for year in years:
        yr_recs = [r for r in final if r["year"] == year and r["subtype"] == "総数"]
        yr_summary = defaultdict(int)
        for r in yr_recs:
            yr_summary[r["crime_type"]] += r["count"]
        summary["yearly_totals"][str(year)] = dict(yr_summary)

    summary_path = OUT_DIR / "estat_crime_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"Saved: {summary_path}")

    print("\nDone!")


if __name__ == "__main__":
    main()
