#!/usr/bin/env python3
"""
Generate synthetic crime events for prefectures without individual-level open data.

For the 25 prefectures that lack CSV-level crime data, we:
1. Take the prefecture-level crime counts from estat_crime_full.json
2. Distribute them across major cities within each prefecture using population weights
3. Assign approximate lat/lon coordinates for each city
4. Output synthetic events for 2023 (latest full year)

Output: data/crime/national/synthetic_events.json
"""

import json
import random
import math
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parent.parent
CRIME_DIR = BASE / "data" / "crime"
OUT_DIR = CRIME_DIR / "national"

random.seed(42)  # Reproducibility

# ─── Prefectures WITHOUT individual-level open data ─────────────────
# These 25 prefectures need synthetic events
PREFECTURES_WITHOUT_DATA = {
    "24", "26", "41", "01", "30", "44", "45", "19",
    "33", "32", "34", "15", "09", "47", "25", "43",
    "17", "18", "05", "10", "08", "37", "39", "31", "46"
}

# ─── Major cities per prefecture with population (2023 estimates, thousands) ──
# and approximate centroid coordinates
# For each prefecture, we list the top cities that together account for ~80%+ of population
CITY_DATA = {
    "01": {  # 北海道
        "name": "北海道",
        "cities": [
            {"city": "札幌市", "pop": 1975, "lat": 43.0618, "lon": 141.3545},
            {"city": "旭川市", "pop": 329, "lat": 43.7709, "lon": 142.3650},
            {"city": "函館市", "pop": 243, "lat": 41.7687, "lon": 140.7288},
            {"city": "釧路市", "pop": 161, "lat": 42.9850, "lon": 144.3814},
            {"city": "帯広市", "pop": 165, "lat": 42.9236, "lon": 143.1966},
            {"city": "苫小牧市", "pop": 169, "lat": 42.6340, "lon": 141.6053},
            {"city": "小樽市", "pop": 107, "lat": 43.1907, "lon": 140.9945},
            {"city": "北見市", "pop": 114, "lat": 43.8030, "lon": 143.8908},
            {"city": "江別市", "pop": 120, "lat": 43.1037, "lon": 141.5361},
            {"city": "その他", "pop": 2817, "lat": 43.3, "lon": 142.5},
        ],
    },
    "05": {  # 秋田県
        "name": "秋田県",
        "cities": [
            {"city": "秋田市", "pop": 300, "lat": 39.7200, "lon": 140.1025},
            {"city": "横手市", "pop": 83, "lat": 39.3114, "lon": 140.5533},
            {"city": "大仙市", "pop": 73, "lat": 39.4497, "lon": 140.4753},
            {"city": "由利本荘市", "pop": 71, "lat": 39.3861, "lon": 140.0489},
            {"city": "大館市", "pop": 66, "lat": 40.2714, "lon": 140.5642},
            {"city": "その他", "pop": 337, "lat": 39.6, "lon": 140.3},
        ],
    },
    "08": {  # 茨城県
        "name": "茨城県",
        "cities": [
            {"city": "水戸市", "pop": 269, "lat": 36.3418, "lon": 140.4468},
            {"city": "つくば市", "pop": 252, "lat": 36.0835, "lon": 140.0766},
            {"city": "日立市", "pop": 166, "lat": 36.5991, "lon": 140.6514},
            {"city": "ひたちなか市", "pop": 155, "lat": 36.3966, "lon": 140.5344},
            {"city": "土浦市", "pop": 138, "lat": 36.0799, "lon": 140.2048},
            {"city": "古河市", "pop": 138, "lat": 36.1809, "lon": 139.6994},
            {"city": "取手市", "pop": 104, "lat": 35.9116, "lon": 140.0501},
            {"city": "その他", "pop": 1658, "lat": 36.3, "lon": 140.3},
        ],
    },
    "09": {  # 栃木県
        "name": "栃木県",
        "cities": [
            {"city": "宇都宮市", "pop": 518, "lat": 36.5551, "lon": 139.8836},
            {"city": "小山市", "pop": 167, "lat": 36.3145, "lon": 139.8003},
            {"city": "栃木市", "pop": 151, "lat": 36.3816, "lon": 139.7309},
            {"city": "足利市", "pop": 143, "lat": 36.3409, "lon": 139.4497},
            {"city": "佐野市", "pop": 113, "lat": 36.3142, "lon": 139.5781},
            {"city": "その他", "pop": 808, "lat": 36.6, "lon": 139.9},
        ],
    },
    "10": {  # 群馬県
        "name": "群馬県",
        "cities": [
            {"city": "前橋市", "pop": 331, "lat": 36.3911, "lon": 139.0608},
            {"city": "高崎市", "pop": 370, "lat": 36.3223, "lon": 139.0032},
            {"city": "太田市", "pop": 222, "lat": 36.2913, "lon": 139.3754},
            {"city": "伊勢崎市", "pop": 212, "lat": 36.3113, "lon": 139.1968},
            {"city": "桐生市", "pop": 104, "lat": 36.4054, "lon": 139.3303},
            {"city": "その他", "pop": 681, "lat": 36.5, "lon": 139.1},
        ],
    },
    "15": {  # 新潟県
        "name": "新潟県",
        "cities": [
            {"city": "新潟市", "pop": 781, "lat": 37.9026, "lon": 139.0236},
            {"city": "長岡市", "pop": 263, "lat": 37.4468, "lon": 138.8510},
            {"city": "上越市", "pop": 186, "lat": 37.1481, "lon": 138.2364},
            {"city": "三条市", "pop": 93, "lat": 37.6369, "lon": 138.9612},
            {"city": "柏崎市", "pop": 80, "lat": 37.3723, "lon": 138.5589},
            {"city": "その他", "pop": 757, "lat": 37.7, "lon": 139.0},
        ],
    },
    "17": {  # 石川県
        "name": "石川県",
        "cities": [
            {"city": "金沢市", "pop": 463, "lat": 36.5946, "lon": 136.6256},
            {"city": "白山市", "pop": 110, "lat": 36.5145, "lon": 136.5656},
            {"city": "小松市", "pop": 106, "lat": 36.4014, "lon": 136.4451},
            {"city": "加賀市", "pop": 62, "lat": 36.3031, "lon": 136.3147},
            {"city": "その他", "pop": 379, "lat": 36.7, "lon": 136.8},
        ],
    },
    "18": {  # 福井県
        "name": "福井県",
        "cities": [
            {"city": "福井市", "pop": 260, "lat": 36.0652, "lon": 136.2219},
            {"city": "坂井市", "pop": 88, "lat": 36.1697, "lon": 136.2317},
            {"city": "越前市", "pop": 80, "lat": 35.9025, "lon": 136.1693},
            {"city": "敦賀市", "pop": 63, "lat": 35.6451, "lon": 136.0556},
            {"city": "その他", "pop": 259, "lat": 35.9, "lon": 136.1},
        ],
    },
    "19": {  # 山梨県
        "name": "山梨県",
        "cities": [
            {"city": "甲府市", "pop": 188, "lat": 35.6642, "lon": 138.5684},
            {"city": "南アルプス市", "pop": 69, "lat": 35.6076, "lon": 138.4651},
            {"city": "甲斐市", "pop": 76, "lat": 35.6745, "lon": 138.5152},
            {"city": "笛吹市", "pop": 66, "lat": 35.6476, "lon": 138.6418},
            {"city": "富士吉田市", "pop": 46, "lat": 35.4878, "lon": 138.8034},
            {"city": "その他", "pop": 345, "lat": 35.6, "lon": 138.6},
        ],
    },
    "25": {  # 滋賀県
        "name": "滋賀県",
        "cities": [
            {"city": "大津市", "pop": 344, "lat": 35.0045, "lon": 135.8686},
            {"city": "草津市", "pop": 145, "lat": 35.0170, "lon": 135.9608},
            {"city": "長浜市", "pop": 114, "lat": 35.3811, "lon": 136.2696},
            {"city": "東近江市", "pop": 113, "lat": 35.1126, "lon": 136.2022},
            {"city": "彦根市", "pop": 112, "lat": 35.2764, "lon": 136.2519},
            {"city": "その他", "pop": 592, "lat": 35.1, "lon": 136.1},
        ],
    },
    "26": {  # 京都府
        "name": "京都府",
        "cities": [
            {"city": "京都市", "pop": 1453, "lat": 35.0116, "lon": 135.7681},
            {"city": "宇治市", "pop": 179, "lat": 34.8845, "lon": 135.8040},
            {"city": "亀岡市", "pop": 86, "lat": 35.0127, "lon": 135.5773},
            {"city": "舞鶴市", "pop": 77, "lat": 35.4434, "lon": 135.3840},
            {"city": "長岡京市", "pop": 81, "lat": 34.9260, "lon": 135.6947},
            {"city": "その他", "pop": 694, "lat": 35.2, "lon": 135.5},
        ],
    },
    "30": {  # 和歌山県
        "name": "和歌山県",
        "cities": [
            {"city": "和歌山市", "pop": 352, "lat": 34.2260, "lon": 135.1675},
            {"city": "田辺市", "pop": 69, "lat": 33.7310, "lon": 135.3787},
            {"city": "橋本市", "pop": 60, "lat": 34.3154, "lon": 135.6051},
            {"city": "海南市", "pop": 47, "lat": 34.1558, "lon": 135.2033},
            {"city": "その他", "pop": 382, "lat": 33.9, "lon": 135.5},
        ],
    },
    "31": {  # 鳥取県
        "name": "鳥取県",
        "cities": [
            {"city": "鳥取市", "pop": 186, "lat": 35.5036, "lon": 134.2383},
            {"city": "米子市", "pop": 147, "lat": 35.4282, "lon": 133.3311},
            {"city": "倉吉市", "pop": 45, "lat": 35.4301, "lon": 133.8255},
            {"city": "境港市", "pop": 32, "lat": 35.5380, "lon": 133.2320},
            {"city": "その他", "pop": 130, "lat": 35.4, "lon": 133.8},
        ],
    },
    "32": {  # 島根県
        "name": "島根県",
        "cities": [
            {"city": "松江市", "pop": 200, "lat": 35.4723, "lon": 133.0505},
            {"city": "出雲市", "pop": 175, "lat": 35.3669, "lon": 132.7551},
            {"city": "浜田市", "pop": 50, "lat": 34.8992, "lon": 132.0811},
            {"city": "益田市", "pop": 44, "lat": 34.6768, "lon": 131.8419},
            {"city": "その他", "pop": 181, "lat": 35.2, "lon": 132.5},
        ],
    },
    "33": {  # 岡山県
        "name": "岡山県",
        "cities": [
            {"city": "岡山市", "pop": 720, "lat": 34.6618, "lon": 133.9344},
            {"city": "倉敷市", "pop": 472, "lat": 34.5850, "lon": 133.7714},
            {"city": "津山市", "pop": 97, "lat": 35.0690, "lon": 134.0068},
            {"city": "総社市", "pop": 69, "lat": 34.6726, "lon": 133.7459},
            {"city": "その他", "pop": 522, "lat": 34.8, "lon": 133.8},
        ],
    },
    "34": {  # 広島県
        "name": "広島県",
        "cities": [
            {"city": "広島市", "pop": 1194, "lat": 34.3963, "lon": 132.4596},
            {"city": "福山市", "pop": 459, "lat": 34.4860, "lon": 133.3622},
            {"city": "呉市", "pop": 207, "lat": 34.2488, "lon": 132.5655},
            {"city": "東広島市", "pop": 193, "lat": 34.4267, "lon": 132.7432},
            {"city": "尾道市", "pop": 127, "lat": 34.4089, "lon": 133.2050},
            {"city": "その他", "pop": 600, "lat": 34.5, "lon": 132.8},
        ],
    },
    "37": {  # 香川県
        "name": "香川県",
        "cities": [
            {"city": "高松市", "pop": 418, "lat": 34.3401, "lon": 134.0434},
            {"city": "丸亀市", "pop": 108, "lat": 34.2897, "lon": 133.7980},
            {"city": "三豊市", "pop": 59, "lat": 34.1822, "lon": 133.7164},
            {"city": "観音寺市", "pop": 55, "lat": 34.1283, "lon": 133.6607},
            {"city": "その他", "pop": 300, "lat": 34.2, "lon": 134.0},
        ],
    },
    "39": {  # 高知県
        "name": "高知県",
        "cities": [
            {"city": "高知市", "pop": 322, "lat": 33.5597, "lon": 133.5311},
            {"city": "南国市", "pop": 46, "lat": 33.5768, "lon": 133.6313},
            {"city": "四万十市", "pop": 32, "lat": 32.9916, "lon": 132.9378},
            {"city": "香南市", "pop": 32, "lat": 33.5625, "lon": 133.6896},
            {"city": "その他", "pop": 248, "lat": 33.5, "lon": 133.3},
        ],
    },
    "41": {  # 佐賀県
        "name": "佐賀県",
        "cities": [
            {"city": "佐賀市", "pop": 232, "lat": 33.2494, "lon": 130.2988},
            {"city": "唐津市", "pop": 114, "lat": 33.4509, "lon": 129.9694},
            {"city": "鳥栖市", "pop": 75, "lat": 33.3786, "lon": 130.5062},
            {"city": "伊万里市", "pop": 51, "lat": 33.2647, "lon": 129.8804},
            {"city": "その他", "pop": 328, "lat": 33.2, "lon": 130.2},
        ],
    },
    "43": {  # 熊本県
        "name": "熊本県",
        "cities": [
            {"city": "熊本市", "pop": 738, "lat": 32.7898, "lon": 130.7417},
            {"city": "八代市", "pop": 120, "lat": 32.5070, "lon": 130.6016},
            {"city": "天草市", "pop": 72, "lat": 32.4578, "lon": 130.1932},
            {"city": "玉名市", "pop": 62, "lat": 32.9275, "lon": 130.5574},
            {"city": "合志市", "pop": 63, "lat": 32.8856, "lon": 130.7876},
            {"city": "その他", "pop": 695, "lat": 32.7, "lon": 130.7},
        ],
    },
    "44": {  # 大分県
        "name": "大分県",
        "cities": [
            {"city": "大分市", "pop": 476, "lat": 33.2382, "lon": 131.6126},
            {"city": "別府市", "pop": 115, "lat": 33.2846, "lon": 131.5004},
            {"city": "中津市", "pop": 82, "lat": 33.5979, "lon": 131.1879},
            {"city": "佐伯市", "pop": 64, "lat": 32.9585, "lon": 131.8990},
            {"city": "その他", "pop": 373, "lat": 33.2, "lon": 131.5},
        ],
    },
    "45": {  # 宮崎県
        "name": "宮崎県",
        "cities": [
            {"city": "宮崎市", "pop": 398, "lat": 31.9111, "lon": 131.4239},
            {"city": "都城市", "pop": 160, "lat": 31.7253, "lon": 131.0620},
            {"city": "延岡市", "pop": 117, "lat": 32.5822, "lon": 131.6680},
            {"city": "日向市", "pop": 59, "lat": 32.4278, "lon": 131.6244},
            {"city": "その他", "pop": 326, "lat": 32.0, "lon": 131.3},
        ],
    },
    "46": {  # 鹿児島県
        "name": "鹿児島県",
        "cities": [
            {"city": "鹿児島市", "pop": 593, "lat": 31.5602, "lon": 130.5581},
            {"city": "霧島市", "pop": 123, "lat": 31.7403, "lon": 130.7630},
            {"city": "鹿屋市", "pop": 99, "lat": 31.3784, "lon": 130.8528},
            {"city": "薩摩川内市", "pop": 91, "lat": 31.8133, "lon": 130.3044},
            {"city": "姶良市", "pop": 78, "lat": 31.7284, "lon": 130.6319},
            {"city": "その他", "pop": 616, "lat": 31.4, "lon": 130.6},
        ],
    },
    "47": {  # 沖縄県
        "name": "沖縄県",
        "cities": [
            {"city": "那覇市", "pop": 315, "lat": 26.3344, "lon": 127.8056},
            {"city": "沖縄市", "pop": 143, "lat": 26.3342, "lon": 127.8057},
            {"city": "うるま市", "pop": 124, "lat": 26.3793, "lon": 127.8579},
            {"city": "浦添市", "pop": 115, "lat": 26.3464, "lon": 127.7217},
            {"city": "宜野湾市", "pop": 100, "lat": 26.3383, "lon": 127.7783},
            {"city": "名護市", "pop": 63, "lat": 26.5918, "lon": 127.9773},
            {"city": "その他", "pop": 600, "lat": 26.5, "lon": 127.9},
        ],
    },
    "24": {  # 三重県
        "name": "三重県",
        "cities": [
            {"city": "四日市市", "pop": 306, "lat": 34.9648, "lon": 136.6249},
            {"city": "津市", "pop": 273, "lat": 34.7303, "lon": 136.5086},
            {"city": "鈴鹿市", "pop": 196, "lat": 34.8824, "lon": 136.5842},
            {"city": "松阪市", "pop": 159, "lat": 34.5781, "lon": 136.5272},
            {"city": "桑名市", "pop": 139, "lat": 35.0624, "lon": 136.6838},
            {"city": "その他", "pop": 727, "lat": 34.5, "lon": 136.4},
        ],
    },
}


def generate_events(crime_data, target_year=2023):
    """Generate synthetic events for prefectures without open data."""
    # Filter to target prefectures and year, only crime types (not traffic)
    pref_crimes = defaultdict(list)
    for rec in crime_data:
        if (rec["prefecture_code"] in PREFECTURES_WITHOUT_DATA
                and rec["year"] == target_year
                and rec["crime_type"] not in ("刑法犯", "交通事故")
                and rec["subtype"] != "総数"):
            pref_crimes[rec["prefecture_code"]].append(rec)

    events = []
    event_id = 0

    for pref_code, crimes in sorted(pref_crimes.items()):
        city_info = CITY_DATA.get(pref_code)
        if not city_info:
            continue

        cities = city_info["cities"]
        total_pop = sum(c["pop"] for c in cities)
        weights = [c["pop"] / total_pop for c in cities]

        for crime_rec in crimes:
            count = crime_rec["count"]
            if count <= 0:
                continue

            # Distribute count across cities proportional to population
            city_counts = []
            remaining = count
            for i, (city, weight) in enumerate(zip(cities, weights)):
                if i == len(cities) - 1:
                    city_counts.append(remaining)
                else:
                    c = round(count * weight)
                    c = min(c, remaining)
                    city_counts.append(c)
                    remaining -= c

            # Generate events for each city
            for city, city_count in zip(cities, city_counts):
                if city_count <= 0:
                    continue

                # Distribute events across months (roughly uniform with seasonal variation)
                # Crime tends to be slightly higher in summer/fall
                month_weights = [0.075, 0.070, 0.080, 0.082, 0.085, 0.088,
                                 0.092, 0.095, 0.090, 0.088, 0.080, 0.075]

                for month_idx in range(12):
                    month_count = max(0, round(city_count * month_weights[month_idx]))
                    if month_count == 0 and city_count > 12:
                        month_count = 1

                    for _ in range(month_count):
                        # Random day within month
                        month = month_idx + 1
                        if month in (1, 3, 5, 7, 8, 10, 12):
                            max_day = 31
                        elif month in (4, 6, 9, 11):
                            max_day = 30
                        else:
                            max_day = 28
                        day = random.randint(1, max_day)

                        # Add small random offset to coordinates (within ~2km)
                        lat_offset = random.gauss(0, 0.01)
                        lon_offset = random.gauss(0, 0.01)

                        events.append({
                            "event_id": f"SYN-{pref_code}-{event_id:06d}",
                            "prefecture": crime_rec["prefecture"],
                            "prefecture_code": pref_code,
                            "city": city["city"],
                            "crime_type": crime_rec["crime_type"],
                            "subtype": crime_rec["subtype"],
                            "date": f"{target_year}-{month:02d}-{day:02d}",
                            "lat": round(city["lat"] + lat_offset, 6),
                            "lon": round(city["lon"] + lon_offset, 6),
                            "source": "synthetic (population-weighted from e-Stat)",
                        })
                        event_id += 1

    return events


def main():
    print("=" * 60)
    print("Generating synthetic crime events")
    print("=" * 60)

    # Load crime data
    crime_path = OUT_DIR / "estat_crime_full.json"
    with open(crime_path, "r", encoding="utf-8") as f:
        crime_data = json.load(f)

    print(f"Loaded {len(crime_data)} crime records")

    # Generate events for 2023
    events = generate_events(crime_data, target_year=2023)
    print(f"Generated {len(events):,} synthetic events for 2023")

    # Summary by prefecture
    from collections import Counter
    pref_counts = Counter(e["prefecture"] for e in events)
    print(f"\nEvents by prefecture:")
    for pref, count in sorted(pref_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {pref}: {count:,}")
    print(f"  ... and {len(pref_counts) - 10} more prefectures")

    # Summary by crime type
    type_counts = Counter(e["crime_type"] for e in events)
    print(f"\nEvents by crime type:")
    for ct, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {ct}: {count:,}")

    # Save
    out_path = OUT_DIR / "synthetic_events.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=None)  # compact format
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"\nSaved: {out_path}")
    print(f"Size: {size_mb:.1f} MB")

    # Also save a compact summary
    summary = {
        "metadata": {
            "generated": "2026-04-03",
            "method": "Population-weighted allocation of prefecture-level e-Stat crime counts to major cities",
            "target_year": 2023,
            "prefectures_covered": len(pref_counts),
            "total_events": len(events),
        },
        "by_prefecture": dict(sorted(pref_counts.items())),
        "by_crime_type": dict(sorted(type_counts.items())),
    }
    summary_path = OUT_DIR / "synthetic_events_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"Saved: {summary_path}")


if __name__ == "__main__":
    main()
