#!/usr/bin/env python3
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

INDEX_RES = 0.1
MAX_DISTANCE_KM = 1.5
CLOUDY_WET_LIFT = 27.073
SCHOOL_RETURN_MULT = 1.8

ROOT = Path(__file__).resolve().parent.parent
GRID_PATH = ROOT / "dashboard/data/grid_risk.json"
SCHOOLS_PATH = ROOT / "data/schools/elementary_schools.json"
SUMMARY_OUT = ROOT / "data/analysis/school_risk_v2/summary_v2.json"
PROFILES_OUT = ROOT / "data/analysis/school_risk_v2/school_profiles_v2.json"

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
    return (int(math.floor(lat / INDEX_RES)), int(math.floor(lon / INDEX_RES)))


def build_spatial_index(cells):
    idx = defaultdict(list)
    for i, c in enumerate(cells):
        lat = c.get("lat")
        lon = c.get("lon")
        if lat is None or lon is None:
            continue
        idx[bucket_key(float(lat), float(lon))].append(i)
    return idx


def find_nearest_cell(index, cells, lat, lon):
    bi, bj = bucket_key(lat, lon)
    nearest = None
    best_d = float("inf")

    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            for ci in index.get((bi + di, bj + dj), []):
                c = cells[ci]
                clat = c.get("lat")
                clon = c.get("lon")
                if clat is None or clon is None:
                    continue
                d = haversine_km(lat, lon, float(clat), float(clon))
                if d <= MAX_DISTANCE_KM and d < best_d:
                    best_d = d
                    nearest = c

    if nearest is None:
        return None, None
    return nearest, best_d


def pct(n, d):
    return round((n / d) * 100, 2) if d else 0.0


def to_pref_code(v):
    s = str(v or "").strip()
    if not s:
        return ""
    if s.isdigit():
        code = s[:2].zfill(2)
        if 1 <= int(code) <= 47:
            return code
    return ""


def get_pref_name(school_pref_code, cell_pref):
    code = to_pref_code(school_pref_code)
    if code:
        return code, PREF_CODE_TO_NAME[code]
    if cell_pref and isinstance(cell_pref, str):
        return "", cell_pref
    return "", "不明"


def main():
    if not GRID_PATH.exists():
        raise FileNotFoundError(f"Missing grid input: {GRID_PATH}")
    if not SCHOOLS_PATH.exists():
        raise FileNotFoundError(f"Missing schools input: {SCHOOLS_PATH}")

    grid = json.loads(GRID_PATH.read_text(encoding="utf-8"))
    schools = json.loads(SCHOOLS_PATH.read_text(encoding="utf-8"))

    index = build_spatial_index(grid)

    total = len(schools)
    in_coverage = 0
    adaptive_coverage = 0
    background_coverage = 0
    out_of_coverage = 0

    high_risk_schools = 0
    haven_deficit_schools = 0
    double_risk_schools = 0

    risk_levels = Counter()

    pref_stats = {
        code: {
            "prefecture": name,
            "total": 0,
            "high_risk": 0,
        }
        for code, name in PREF_CODE_TO_NAME.items()
    }

    profiles = []

    for s in schools:
        lat = s.get("lat")
        lon = s.get("lon")

        if lat is None or lon is None:
            out_of_coverage += 1
            risk_levels["out_of_coverage"] += 1
            profiles.append(
                {
                    "id": s.get("id"),
                    "name": s.get("name"),
                    "lat": lat,
                    "lon": lon,
                    "pref_code": to_pref_code(s.get("pref_code")),
                    "prefecture": get_pref_name(s.get("pref_code"), None)[1],
                    "in_coverage": False,
                    "coverage_type": "none",
                    "risk_level": "out_of_coverage",
                }
            )
            continue

        lat = float(lat)
        lon = float(lon)
        nearest, distance_km = find_nearest_cell(index, grid, lat, lon)

        if nearest is None:
            out_of_coverage += 1
            risk_levels["out_of_coverage"] += 1
            pref_code = to_pref_code(s.get("pref_code"))
            pref_name = PREF_CODE_TO_NAME.get(pref_code, "不明") if pref_code else "不明"
            if pref_code:
                pref_stats[pref_code]["total"] += 1
            profiles.append(
                {
                    "id": s.get("id"),
                    "name": s.get("name"),
                    "lat": lat,
                    "lon": lon,
                    "pref_code": pref_code,
                    "prefecture": pref_name,
                    "in_coverage": False,
                    "coverage_type": "none",
                    "risk_level": "out_of_coverage",
                }
            )
            continue

        in_coverage += 1
        is_background = bool(nearest.get("is_background", False))
        coverage_type = "background" if is_background else "adaptive"
        if is_background:
            background_coverage += 1
        else:
            adaptive_coverage += 1

        base_risk = float(nearest.get("risk_score", 0.0))
        base_p_escape = float(nearest.get("p_escape", 0.0))
        haven_count = int(float(nearest.get("haven_count_500m", 0)))
        base_eh = float(nearest.get("expected_harm", 0.0))

        child_p_escape = base_p_escape * 0.7
        dynamic_crime_risk = min(1.0, base_risk * SCHOOL_RETURN_MULT)
        dynamic_traffic_risk = min(1.0, 0.15 * CLOUDY_WET_LIFT)
        eh_crime = dynamic_crime_risk * 0.5 * (1 - child_p_escape)
        eh_traffic = dynamic_traffic_risk * 0.5 * 0.5
        eh_total = min(1.0, eh_crime + eh_traffic)

        if base_risk >= 0.619:
            level = "high"
        elif base_risk >= 0.395:
            level = "medium_high"
        else:
            level = "medium"

        haven_deficit = haven_count <= 1
        high_risk = level in {"high", "very_high"}
        double_risk = high_risk and haven_deficit

        if haven_deficit:
            haven_deficit_schools += 1
        if high_risk:
            high_risk_schools += 1
        if double_risk:
            double_risk_schools += 1

        risk_levels[level] += 1

        pref_code, pref_name = get_pref_name(s.get("pref_code"), nearest.get("pref"))
        if pref_code:
            pref_stats[pref_code]["total"] += 1
            if high_risk:
                pref_stats[pref_code]["high_risk"] += 1

        profiles.append(
            {
                "id": s.get("id"),
                "name": s.get("name"),
                "lat": lat,
                "lon": lon,
                "pref_code": pref_code,
                "prefecture": pref_name,
                "in_coverage": True,
                "coverage_type": coverage_type,
                "nearest_cell_lat": nearest.get("lat"),
                "nearest_cell_lon": nearest.get("lon"),
                "distance_km": round(float(distance_km), 4),
                "base_risk": round(base_risk, 6),
                "base_p_escape": round(base_p_escape, 6),
                "haven_count_500m": haven_count,
                "base_expected_harm": round(base_eh, 6),
                "child_p_escape": round(child_p_escape, 6),
                "dynamic_crime_risk": round(dynamic_crime_risk, 6),
                "dynamic_traffic_risk": round(dynamic_traffic_risk, 6),
                "eh_crime": round(eh_crime, 6),
                "eh_traffic": round(eh_traffic, 6),
                "eh_total": round(eh_total, 6),
                "risk_level": level,
                "haven_deficit": haven_deficit,
                "high_risk": high_risk,
                "double_risk": double_risk,
            }
        )

    ranked = []
    for code in sorted(pref_stats.keys(), key=lambda x: int(x)):
        row = pref_stats[code]
        total_s = row["total"]
        high_s = row["high_risk"]
        ranked.append(
            {
                "pref_code": code,
                "prefecture": row["prefecture"],
                "total_schools": total_s,
                "high_risk_schools": high_s,
                "high_risk_pct": round((high_s / total_s) * 100, 2) if total_s else 0.0,
            }
        )

    ranked_desc = sorted(ranked, key=lambda x: (-x["high_risk_pct"], -x["high_risk_schools"], x["pref_code"]))
    ranked_asc = sorted(ranked, key=lambda x: (x["high_risk_pct"], x["high_risk_schools"], x["pref_code"]))

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": "v2_national_grid",
        "total_schools": total,
        "in_coverage": in_coverage,
        "coverage_pct": pct(in_coverage, total),
        "adaptive_coverage": adaptive_coverage,
        "background_coverage": background_coverage,
        "out_of_coverage": out_of_coverage,
        "high_risk_schools": high_risk_schools,
        "haven_deficit_schools": haven_deficit_schools,
        "double_risk_schools": double_risk_schools,
        "risk_level_distribution": dict(risk_levels),
        "prefecture_high_risk_top10": ranked_desc[:10],
        "prefecture_high_risk_bottom10": ranked_asc[:10],
    }

    SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    PROFILES_OUT.write_text(json.dumps(profiles, ensure_ascii=False), encoding="utf-8")

    print(f"total_schools={total}")
    print(f"in_coverage={in_coverage}")
    print(f"adaptive_coverage={adaptive_coverage}")
    print(f"background_coverage={background_coverage}")
    print(f"out_of_coverage={out_of_coverage}")
    print(f"high_risk_schools={high_risk_schools}")
    print(f"haven_deficit_schools={haven_deficit_schools}")
    print(f"double_risk_schools={double_risk_schools}")


if __name__ == "__main__":
    main()
