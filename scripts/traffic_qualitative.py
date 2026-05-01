#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ACCIDENT_CONTENT_MAP = {
    "1": "死亡事故",
    "2": "負傷事故",
}

ACCIDENT_TYPE_MAP = {
    "01": "正面衝突",
    "02": "追突(進行中)",
    "03": "追突(その他)",
    "04": "出会い頭",
    "05": "左折時",
    "06": "右折時",
    "07": "横断中",
    "08": "すれ違い",
    "09": "左折直進",
    "10": "右折直進",
    "11": "その他",
    "21": "追突",
    "41": "出会い頭衝突",
    "61": "右左折時衝突",
    "71": "その他(車両相互)",
    "81": "人対車両",
}

PARTY_TYPE_MAP = {
    "01": "普通乗用",
    "02": "普通貨物",
    "03": "大型乗用",
    "04": "大型貨物",
    "05": "軽乗用",
    "06": "軽貨物",
    "07": "特殊",
    "11": "自動二輪",
    "12": "原付",
    "13": "自転車",
    "14": "歩行者",
    "15": "電動キックボード",
    "17": "その他",
    "75": "歩行者",
    "76": "歩行者(65歳以上)",
}

WEATHER_MAP = {
    "1": "晴",
    "2": "曇",
    "3": "雨",
    "4": "霧",
    "5": "雪",
}

ROAD_SURFACE_MAP = {
    "1": "乾燥",
    "2": "湿潤",
    "3": "凍結",
    "4": "積雪",
    "5": "その他",
}

ROAD_SHAPE_MAP = {
    "01": "交差点",
    "02": "交差点付近",
    "03": "カーブ",
    "04": "屈折",
    "05": "トンネル",
    "06": "橋",
    "07": "踏切",
    "14": "一般単路",
    "99": "その他",
}

DAY_NIGHT_MAP = {
    "11": "昼(明)",
    "12": "昼",
    "13": "昼(暮)",
    "21": "夜(暗)",
    "22": "夜(街灯あり)",
    "23": "夜(道路照明あり)",
}

INJURY_MAP = {
    "1": "死亡",
    "2": "重傷(30日以上)",
    "3": "軽傷(30日未満)",
    "4": "損傷なし",
}

PREFECTURE_MAP = {
    "01": "北海道", "02": "青森県", "03": "岩手県", "04": "宮城県", "05": "秋田県", "06": "山形県",
    "07": "福島県", "08": "茨城県", "09": "栃木県", "10": "群馬県", "11": "埼玉県", "12": "千葉県",
    "13": "東京都", "14": "神奈川県", "15": "新潟県", "16": "富山県", "17": "石川県", "18": "福井県",
    "19": "山梨県", "20": "長野県", "21": "岐阜県", "22": "静岡県", "23": "愛知県", "24": "三重県",
    "25": "滋賀県", "26": "京都府", "27": "大阪府", "28": "兵庫県", "29": "奈良県", "30": "和歌山県",
    "31": "鳥取県", "32": "島根県", "33": "岡山県", "34": "広島県", "35": "山口県", "36": "徳島県",
    "37": "香川県", "38": "愛媛県", "39": "高知県", "40": "福岡県", "41": "佐賀県", "42": "長崎県",
    "43": "熊本県", "44": "大分県", "45": "宮崎県", "46": "鹿児島県", "47": "沖縄県",
}

WEATHER_RISK = {"雨": 1.3, "雪": 1.5, "霧": 1.4, "晴": 1.0, "曇": 1.05}
SURFACE_RISK = {"凍結": 1.6, "積雪": 1.4, "湿潤": 1.2, "乾燥": 1.0}
DAY_NIGHT_RISK = {"夜(暗)": 1.4, "夜(街灯あり)": 1.15, "夜(道路照明あり)": 1.15, "昼(明)": 1.0, "昼": 1.0, "昼(暮)": 1.0}
ROAD_SHAPE_RISK = {"交差点": 1.3, "カーブ": 1.25, "踏切": 1.4, "一般単路": 1.0}

YEARS = ["2019", "2020", "2021", "2022", "2023", "2024"]


def normalize_code(value: str) -> str:
    return (value or "").strip()


def decode_code(value: str, mapping: dict[str, str]) -> str:
    raw = normalize_code(value)
    if raw in mapping:
        return mapping[raw]
    if raw.isdigit():
        if len(raw) == 1:
            padded = raw.zfill(2)
            if padded in mapping:
                return mapping[padded]
        if len(raw) == 2:
            no_pad = str(int(raw))
            if no_pad in mapping:
                return mapping[no_pad]
    return raw


def get_value(row: list[str], idx: int | None) -> str:
    if idx is None:
        return ""
    if idx < 0 or idx >= len(row):
        return ""
    return row[idx].strip()


def counter_to_sorted_dict(counter: Counter) -> dict[str, int]:
    return {k: v for k, v in sorted(counter.items(), key=lambda x: (-x[1], x[0]))}


def nested_counter_to_dict(nested: dict[str, Counter]) -> dict[str, dict[str, int]]:
    return {k: counter_to_sorted_dict(v) for k, v in sorted(nested.items(), key=lambda x: x[0])}


def age_to_band(age_code: str) -> str:
    s = normalize_code(age_code)
    if not s.isdigit():
        return "不明"
    age = int(s)
    if age <= 0 or age >= 999:
        return "不明"
    if age <= 15:
        return "0-15"
    if age <= 24:
        return "16-24"
    if age <= 39:
        return "25-39"
    if age <= 64:
        return "40-64"
    return "65+"


def pick_files(base_dir: Path) -> dict[str, Path]:
    priorities = {
        "": 0,
        "full": 1,
        "geocoded": 2,
        "synthetic": 3,
        "head": 4,
    }
    selected: dict[str, tuple[int, Path]] = {}
    for path in base_dir.glob("honhyo_*.csv"):
        stem = path.stem
        parts = stem.split("_")
        if len(parts) < 2 or parts[0] != "honhyo":
            continue
        year = parts[1]
        if year not in YEARS:
            continue
        suffix = parts[2] if len(parts) >= 3 else ""
        priority = priorities.get(suffix, 9)
        current = selected.get(year)
        if current is None or priority < current[0] or (priority == current[0] and path.name < current[1].name):
            selected[year] = (priority, path)
    return {year: selected[year][1] for year in YEARS if year in selected}


def build_index_map(header: list[str]) -> dict[str, int | None]:
    hmap = {name.strip(): i for i, name in enumerate(header)}
    return {
        "pref_code": hmap.get("都道府県コード"),
        "accident_content": hmap.get("事故内容"),
        "accident_type": hmap.get("事故類型"),
        "weather": hmap.get("天候"),
        "road_surface": hmap.get("路面状態"),
        "road_shape": hmap.get("道路形状"),
        "day_night": hmap.get("昼夜"),
        "party_type_a": hmap.get("当事者種別（当事者A）"),
        "party_type_b": hmap.get("当事者種別（当事者B）"),
        "age_a": hmap.get("年齢（当事者A）"),
        "age_b": hmap.get("年齢（当事者B）"),
        "injury_a": hmap.get("人身損傷程度（当事者A）"),
        "injury_b": hmap.get("人身損傷程度（当事者B）"),
    }


def update_pref_profile(profile: dict, accident_type: str, weather: str, road_surface: str, road_shape: str, day_night: str) -> None:
    profile["count"] += 1
    profile["accident_type"][accident_type] += 1
    profile["weather"][weather] += 1
    profile["road_surface"][road_surface] += 1
    profile["road_shape"][road_shape] += 1
    profile["day_night"][day_night] += 1


def main() -> None:
    base_dir = Path("data/traffic")
    output_path = Path("docs/data/traffic_qualitative_analysis.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    files_by_year = pick_files(base_dir)

    accident_type_dist = Counter()
    weather_dist = Counter()
    road_surface_dist = Counter()
    road_shape_dist = Counter()
    day_night_dist = Counter()
    party_type_dist = Counter()

    cross_weather_accident = defaultdict(Counter)
    cross_daynight_accident = defaultdict(Counter)
    cross_roadshape_accident = defaultdict(Counter)
    cross_age_injury = defaultdict(Counter)

    prefecture_profiles = defaultdict(lambda: {
        "count": 0,
        "accident_type": Counter(),
        "weather": Counter(),
        "road_surface": Counter(),
        "road_shape": Counter(),
        "day_night": Counter(),
    })

    yearly_trend = {}
    total_rows = 0

    risk_total = 0.0
    risk_count = 0
    risk_min = None
    risk_max = None
    risk_bucket = Counter()

    for year in YEARS:
        path = files_by_year.get(year)
        if path is None:
            continue

        year_count = 0
        with path.open("r", encoding="cp932", newline="", errors="replace") as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                yearly_trend[year] = 0
                continue

            idx = build_index_map(header)
            for row in reader:
                if not row:
                    continue
                year_count += 1
                total_rows += 1

                accident_content = decode_code(get_value(row, idx["accident_content"]), ACCIDENT_CONTENT_MAP)
                accident_type = decode_code(get_value(row, idx["accident_type"]), ACCIDENT_TYPE_MAP)
                weather = decode_code(get_value(row, idx["weather"]), WEATHER_MAP)
                road_surface = decode_code(get_value(row, idx["road_surface"]), ROAD_SURFACE_MAP)
                road_shape = decode_code(get_value(row, idx["road_shape"]), ROAD_SHAPE_MAP)
                day_night = decode_code(get_value(row, idx["day_night"]), DAY_NIGHT_MAP)
                party_a = decode_code(get_value(row, idx["party_type_a"]), PARTY_TYPE_MAP)
                party_b = decode_code(get_value(row, idx["party_type_b"]), PARTY_TYPE_MAP)

                accident_type_dist[accident_type] += 1
                weather_dist[weather] += 1
                road_surface_dist[road_surface] += 1
                road_shape_dist[road_shape] += 1
                day_night_dist[day_night] += 1
                party_type_dist[party_a] += 1
                party_type_dist[party_b] += 1

                cross_weather_accident[weather][accident_type] += 1
                cross_daynight_accident[day_night][accident_type] += 1
                cross_roadshape_accident[road_shape][accident_type] += 1

                age_band_a = age_to_band(get_value(row, idx["age_a"]))
                age_band_b = age_to_band(get_value(row, idx["age_b"]))
                injury_a = decode_code(get_value(row, idx["injury_a"]), INJURY_MAP)
                injury_b = decode_code(get_value(row, idx["injury_b"]), INJURY_MAP)
                cross_age_injury[age_band_a][injury_a] += 1
                cross_age_injury[age_band_b][injury_b] += 1

                pref_code_raw = get_value(row, idx["pref_code"])
                pref_code = pref_code_raw.zfill(2) if pref_code_raw.isdigit() else pref_code_raw
                pref_name = PREFECTURE_MAP.get(pref_code, pref_code_raw)
                update_pref_profile(
                    prefecture_profiles[pref_name],
                    accident_type=accident_type,
                    weather=weather,
                    road_surface=road_surface,
                    road_shape=road_shape,
                    day_night=day_night,
                )

                w = WEATHER_RISK.get(weather, 1.0)
                s = SURFACE_RISK.get(road_surface, 1.0)
                d = DAY_NIGHT_RISK.get(day_night, 1.0)
                r = ROAD_SHAPE_RISK.get(road_shape, 1.0)
                risk = w * s * d * r
                risk_total += risk
                risk_count += 1
                risk_min = risk if risk_min is None else min(risk_min, risk)
                risk_max = risk if risk_max is None else max(risk_max, risk)
                risk_bucket[f"{risk:.2f}"] += 1

                _ = accident_content

        yearly_trend[year] = year_count

    pref_out = {}
    for pref_name, profile in sorted(prefecture_profiles.items(), key=lambda x: x[0]):
        pref_out[pref_name] = {
            "count": profile["count"],
            "top_accident_type": counter_to_sorted_dict(profile["accident_type"]),
            "top_weather": counter_to_sorted_dict(profile["weather"]),
            "top_road_surface": counter_to_sorted_dict(profile["road_surface"]),
            "top_road_shape": counter_to_sorted_dict(profile["road_shape"]),
            "top_day_night": counter_to_sorted_dict(profile["day_night"]),
        }

    result = {
        "metadata": {
            "source_dir": str(base_dir),
            "selected_files": {year: str(path) for year, path in files_by_year.items()},
            "years_requested": YEARS,
            "total_rows": total_rows,
            "encoding": "cp932",
        },
        "accident_type_dist": counter_to_sorted_dict(accident_type_dist),
        "weather_dist": counter_to_sorted_dict(weather_dist),
        "road_surface_dist": counter_to_sorted_dict(road_surface_dist),
        "road_shape_dist": counter_to_sorted_dict(road_shape_dist),
        "day_night_dist": counter_to_sorted_dict(day_night_dist),
        "party_type_dist": counter_to_sorted_dict(party_type_dist),
        "cross_tabs": {
            "weather_x_accident_type": nested_counter_to_dict(cross_weather_accident),
            "day_night_x_accident_type": nested_counter_to_dict(cross_daynight_accident),
            "road_shape_x_accident_type": nested_counter_to_dict(cross_roadshape_accident),
            "age_band_x_injury_degree": nested_counter_to_dict(cross_age_injury),
        },
        "risk_multipliers": {
            "factor_tables": {
                "weather": WEATHER_RISK,
                "road_surface": SURFACE_RISK,
                "day_night": DAY_NIGHT_RISK,
                "road_shape": ROAD_SHAPE_RISK,
            },
            "summary": {
                "count": risk_count,
                "average": round((risk_total / risk_count), 6) if risk_count else None,
                "min": round(risk_min, 6) if risk_min is not None else None,
                "max": round(risk_max, 6) if risk_max is not None else None,
                "distribution": counter_to_sorted_dict(risk_bucket),
            },
        },
        "prefecture_profiles": pref_out,
        "yearly_trend": {year: yearly_trend.get(year, 0) for year in YEARS},
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Wrote {output_path} (rows={total_rows})")


if __name__ == "__main__":
    main()
