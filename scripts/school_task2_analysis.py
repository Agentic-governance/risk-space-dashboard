#!/usr/bin/env python3
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

INDEX_RES = 0.1
RADIUS_KM = 0.5

SCHOOLS_PATH = Path("data/schools/elementary_schools.json")
GRID_PATH = Path("dashboard/data/grid_risk.json")
INTERACTION_PATH = Path("data/analysis/interaction/traffic_interaction_table.json")
SUMMARY_OUT = Path("data/analysis/school_risk/national_school_risk_summary.json")
PROFILES_OUT = Path("data/analysis/school_risk/school_profiles_full.json")

WEATHER_SCENARIOS = {
    "sunny_dry": ("sunny", "dry"),
    "cloudy_wet": ("cloudy", "wet"),
    "rain_wet": ("rain", "wet"),
    "snow_snow_covered": ("snow", "snow_covered"),
}

PREF_CODE_TO_NAME = {
    "01": "北海道", "02": "青森県", "03": "岩手県", "04": "宮城県", "05": "秋田県", "06": "山形県", "07": "福島県",
    "08": "茨城県", "09": "栃木県", "10": "群馬県", "11": "埼玉県", "12": "千葉県", "13": "東京都", "14": "神奈川県",
    "15": "新潟県", "16": "富山県", "17": "石川県", "18": "福井県", "19": "山梨県", "20": "長野県", "21": "岐阜県",
    "22": "静岡県", "23": "愛知県", "24": "三重県", "25": "滋賀県", "26": "京都府", "27": "大阪府", "28": "兵庫県",
    "29": "奈良県", "30": "和歌山県", "31": "鳥取県", "32": "島根県", "33": "岡山県", "34": "広島県", "35": "山口県",
    "36": "徳島県", "37": "香川県", "38": "愛媛県", "39": "高知県", "40": "福岡県", "41": "佐賀県", "42": "長崎県",
    "43": "熊本県", "44": "大分県", "45": "宮崎県", "46": "鹿児島県", "47": "沖縄県",
}


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def bucket_key(lat, lon):
    return (round(math.floor(lat / INDEX_RES) * INDEX_RES, 1), round(math.floor(lon / INDEX_RES) * INDEX_RES, 1))


def build_spatial_index(cells):
    idx = defaultdict(list)
    for c in cells:
        lat = c.get("lat")
        lon = c.get("lon")
        if lat is None or lon is None:
            continue
        idx[bucket_key(float(lat), float(lon))].append(c)
    return idx


def find_nearby_cells(index, lat, lon, radius_km=RADIUS_KM):
    lat = float(lat)
    lon = float(lon)
    lat_delta = radius_km / 111.0
    lon_delta = radius_km / max(111.0 * math.cos(math.radians(lat)), 1e-9)

    min_b_lat = math.floor((lat - lat_delta) / INDEX_RES) * INDEX_RES
    max_b_lat = math.floor((lat + lat_delta) / INDEX_RES) * INDEX_RES
    min_b_lon = math.floor((lon - lon_delta) / INDEX_RES) * INDEX_RES
    max_b_lon = math.floor((lon + lon_delta) / INDEX_RES) * INDEX_RES

    nearby = []
    b_lat = min_b_lat
    while b_lat <= max_b_lat + 1e-9:
        b_lon = min_b_lon
        while b_lon <= max_b_lon + 1e-9:
            for c in index.get((round(b_lat, 1), round(b_lon, 1)), []):
                d = haversine_km(lat, lon, float(c["lat"]), float(c["lon"]))
                if d <= radius_km:
                    cc = dict(c)
                    cc["distance_km"] = d
                    nearby.append(cc)
            b_lon += INDEX_RES
        b_lat += INDEX_RES
    return nearby


def lookup_lift(table, weather, road, day_dim="day_dim"):
    keys = [
        f"child+pedestrian+{weather}+{road}+{day_dim}",
        f"child+pedestrian+{weather}+{road}",
        f"child+pedestrian+{weather}",
        "child+pedestrian",
    ]
    for k in keys:
        v = table.get(k)
        if isinstance(v, dict) and "lift" in v:
            return float(v["lift"]), k
    return 5.0, "default"


def pref_name_from_code(pref_code):
    code = str(pref_code or "").strip()[:2].zfill(2)
    return PREF_CODE_TO_NAME.get(code, "不明")


def pct(n, d):
    return round((n / d) * 100, 2) if d else 0.0


def percentile(values, p):
    if not values:
        return 0.0
    vals = sorted(float(v) for v in values)
    if len(vals) == 1:
        return vals[0]
    p = max(0.0, min(1.0, p))
    k = (len(vals) - 1) * p
    f = int(math.floor(k))
    c = int(math.ceil(k))
    if f == c:
        return vals[f]
    return vals[f] * (c - k) + vals[c] * (k - f)


def main():
    if not SCHOOLS_PATH.exists():
        raise FileNotFoundError(f"Missing schools input: {SCHOOLS_PATH}")
    if not GRID_PATH.exists():
        raise FileNotFoundError(f"Missing grid input: {GRID_PATH}")
    if not INTERACTION_PATH.exists():
        raise FileNotFoundError(f"Missing interaction input: {INTERACTION_PATH}")

    schools = json.loads(SCHOOLS_PATH.read_text(encoding="utf-8"))
    grid = json.loads(GRID_PATH.read_text(encoding="utf-8"))
    interaction_root = json.loads(INTERACTION_PATH.read_text(encoding="utf-8"))
    interaction = interaction_root.get("table", interaction_root)

    index = build_spatial_index(grid)
    grid_risk_scores = [float(c.get("risk_score", 0.0)) for c in grid]
    risk_thresholds = {
        "p50": percentile(grid_risk_scores, 0.50),
        "p90": percentile(grid_risk_scores, 0.90),
        "p99": percentile(grid_risk_scores, 0.99),
    }

    levels = Counter()
    profiles = []

    coverage_count = 0
    haven_deficit_count = 0
    double_risk_count = 0
    high_risk_count = 0

    scenario_lifts = {}
    for label, (weather, road) in WEATHER_SCENARIOS.items():
        lift, source_key = lookup_lift(interaction, weather, road)
        scenario_lifts[label] = {
            "weather": weather,
            "road_surface": road,
            "lift": lift,
            "source_key": source_key,
        }

    cloudy_wet_lift, cloudy_wet_key = lookup_lift(interaction, "cloudy", "wet")

    pref_total = Counter()
    pref_high = Counter()

    total = len(schools)
    for i, s in enumerate(schools, start=1):
        lat = s.get("lat")
        lon = s.get("lon")
        if lat is None or lon is None:
            continue

        nearby = find_nearby_cells(index, lat, lon, radius_km=RADIUS_KM)

        in_coverage = len(nearby) > 0
        if in_coverage:
            coverage_count += 1

        if nearby:
            max_cell = max(nearby, key=lambda x: float(x.get("expected_harm", 0.0)))
            min_haven = min(int(float(c.get("haven_count_500m", 0))) for c in nearby)

            base_risk = float(max_cell.get("risk_score", 0.0))
            base_severity = float(max_cell.get("avg_severity", max_cell.get("max_severity", 5.0)))
            base_p_escape = float(max_cell.get("p_escape", 0.2))
        else:
            max_cell = None
            min_haven = 0
            base_risk = 0.0
            base_severity = 5.0
            base_p_escape = 0.2

        school_risk_metric = base_risk * cloudy_wet_lift
        dynamic_risk = min(1.0, school_risk_metric)
        child_p_escape = base_p_escape * 0.7
        dynamic_eh = dynamic_risk * (base_severity / 5.0) * (1.0 - child_p_escape)

        metric_thresholds = {k: v * cloudy_wet_lift for k, v in risk_thresholds.items()}
        if not in_coverage or base_risk <= 0:
            level = "out_of_coverage"
        elif school_risk_metric >= metric_thresholds["p99"]:
            level = "very_high"
        elif school_risk_metric >= metric_thresholds["p90"]:
            level = "high"
        elif school_risk_metric >= metric_thresholds["p50"]:
            level = "medium"
        else:
            level = "low"
        levels[level] += 1

        haven_deficit = min_haven <= 1
        is_high_risk = level in {"high", "very_high"}
        double_risk = is_high_risk and haven_deficit

        if haven_deficit:
            haven_deficit_count += 1
        if is_high_risk:
            high_risk_count += 1
        if double_risk:
            double_risk_count += 1

        pref_code = str(s.get("pref_code", "")).strip()[:2].zfill(2)
        if not (pref_code.isdigit() and 1 <= int(pref_code) <= 47):
            pref_code = ""
            pref = "不明"
        else:
            pref = pref_name_from_code(pref_code)
            pref_total[pref] += 1
            if is_high_risk:
                pref_high[pref] += 1

        profiles.append(
            {
                "id": s.get("id"),
                "name": s.get("name"),
                "lat": lat,
                "lon": lon,
                "pref_code": pref_code,
                "prefecture": pref,
                "type": s.get("type", "elementary_school"),
                "in_grid_coverage": in_coverage,
                "nearby_cell_count_500m": len(nearby),
                "max_cell": {
                    "lat": max_cell.get("lat") if max_cell else None,
                    "lon": max_cell.get("lon") if max_cell else None,
                    "expected_harm": float(max_cell.get("expected_harm", 0.0)) if max_cell else 0.0,
                    "risk_score": float(max_cell.get("risk_score", 0.0)) if max_cell else 0.0,
                },
                "min_haven_count_500m": min_haven,
                "cloudy_wet_lift": cloudy_wet_lift,
                "cloudy_wet_source_key": cloudy_wet_key,
                "school_risk_metric": round(school_risk_metric, 6),
                "dynamic_risk": round(dynamic_risk, 6),
                "child_p_escape": round(child_p_escape, 6),
                "dynamic_expected_harm": round(dynamic_eh, 6),
                "risk_level": level,
                "haven_deficit": haven_deficit,
                "double_risk": double_risk,
            }
        )

        if i % 1000 == 0:
            print(f"Processed {i}/{total} schools...")

    pref_rates = []
    for pref, n in pref_total.items():
        if pref == "不明":
            continue
        pref_rates.append(
            {
                "prefecture": pref,
                "schools": n,
                "high_risk_schools": pref_high[pref],
                "high_risk_rate_pct": pct(pref_high[pref], n),
            }
        )
    pref_rates.sort(key=lambda x: (x["high_risk_rate_pct"], x["prefecture"]), reverse=True)
    pref_rates_asc = sorted(pref_rates, key=lambda x: (x["high_risk_rate_pct"], x["prefecture"]))

    summary = {
        "generated_at": datetime.now().isoformat(),
        "total_schools_analyzed": total,
        "in_grid_coverage": {
            "count": coverage_count,
            "pct": pct(coverage_count, total),
        },
        "risk_level_distribution": {
            k: {"count": v, "pct": pct(v, total)} for k, v in levels.items()
        },
        "haven_deficit_schools": {
            "count": haven_deficit_count,
            "pct": pct(haven_deficit_count, total),
        },
        "double_risk_schools": {
            "count": double_risk_count,
            "pct": pct(double_risk_count, total),
        },
        "pct_high_risk": pct(high_risk_count, total),
        "pct_haven_deficit": pct(haven_deficit_count, total),
        "pct_double_risk": pct(double_risk_count, total),
        "weather_scenario_lifts": scenario_lifts,
        "risk_thresholds_base_risk": {k: round(v, 6) for k, v in risk_thresholds.items()},
        "risk_thresholds_school_metric": {k: round(v * cloudy_wet_lift, 6) for k, v in risk_thresholds.items()},
        "prefecture_count_included": len(pref_rates),
        "prefecture_high_risk_rate_top10": pref_rates[:10],
        "prefecture_high_risk_rate_bottom10": pref_rates_asc[:10],
        "key_finding": (
            f"全国小学校の{pct(high_risk_count, total)}%が、データ分位点（base_risk p90以上）に基づく高リスクゾーンに近接。"
            f"このうち{pct(double_risk_count, total)}%はSafe Haven不足（≤1）も同時に該当。"
        ),
    }

    SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    PROFILES_OUT.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote summary: {SUMMARY_OUT}")
    print(f"Wrote profiles: {PROFILES_OUT}")


if __name__ == "__main__":
    main()
