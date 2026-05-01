#!/usr/bin/env python3
"""
integrate_historical.py

Integrates all historical data sources (crime, earthquake, traffic) with
current realtime data (police, weather, earthquakes) into a unified
prefecture-level risk profile.

Outputs: docs/data/integrated_risk_profile.json
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path("/Users/reikumaki/Library/CloudStorage/GoogleDrive-teddykmk@gmail.com/マイドライブ/piracy_detector/claude_code/risk_space")

HISTORICAL_CRIME    = BASE / "docs/data/historical_crime_baseline.json"
HISTORICAL_EQ       = BASE / "data/historical/earthquakes_2021_2025.json"
HISTORICAL_TRAFFIC  = BASE / "data/historical/traffic_accidents_2020_2024.json"
REALTIME_SLIM       = BASE / "docs/data/realtime_slim.json"
AMEDAS_CURRENT      = BASE / "docs/data/amedas_current.json"
EARTHQUAKES_LATEST  = BASE / "docs/data/earthquakes_latest.json"
PREF_CENTROIDS      = BASE / "docs/data/pref_centroids.json"
CRIME_TRENDS        = BASE / "docs/data/crime_trends.json"

OUTPUT = BASE / "docs/data/integrated_risk_profile.json"

# ---------------------------------------------------------------------------
# Weights for composite score
# ---------------------------------------------------------------------------
WEIGHTS = {
    "crime":      0.4,
    "earthquake": 0.2,
    "traffic":    0.3,
    "weather":    0.1,
}

# ---------------------------------------------------------------------------
# Prefecture master — code + lat/lon from pref_centroids.json
# ---------------------------------------------------------------------------
PREF_CODES = {
    "北海道": "01", "青森県": "02", "岩手県": "03", "宮城県": "04", "秋田県": "05",
    "山形県": "06", "福島県": "07", "茨城県": "08", "栃木県": "09", "群馬県": "10",
    "埼玉県": "11", "千葉県": "12", "東京都": "13", "神奈川県": "14", "新潟県": "15",
    "富山県": "16", "石川県": "17", "福井県": "18", "山梨県": "19", "長野県": "20",
    "岐阜県": "21", "静岡県": "22", "愛知県": "23", "三重県": "24", "滋賀県": "25",
    "京都府": "26", "大阪府": "27", "兵庫県": "28", "奈良県": "29", "和歌山県": "30",
    "鳥取県": "31", "島根県": "32", "岡山県": "33", "広島県": "34", "山口県": "35",
    "徳島県": "36", "香川県": "37", "愛媛県": "38", "高知県": "39", "福岡県": "40",
    "佐賀県": "41", "長崎県": "42", "熊本県": "43", "大分県": "44", "宮崎県": "45",
    "鹿児島県": "46", "沖縄県": "47",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json(path: Path, default=None):
    """Load JSON file; return default if missing or corrupt."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[WARN] Missing: {path} — using defaults", file=sys.stderr)
        return default
    except json.JSONDecodeError as e:
        print(f"[WARN] Bad JSON in {path}: {e} — using defaults", file=sys.stderr)
        return default


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


# ---------------------------------------------------------------------------
# 1. Build prefecture centroid map from pref_centroids.json
# ---------------------------------------------------------------------------

def build_centroid_map() -> dict:
    """Returns {pref_name: {"lat": ..., "lon": ...}}"""
    raw = load_json(PREF_CENTROIDS, default=[])
    result = {}
    for item in raw:
        name = item.get("prefecture") or item.get("name", "")
        lat  = item.get("lat") or item.get("latitude")
        lon  = item.get("lon") or item.get("longitude")
        if name and lat and lon:
            result[name] = {"lat": float(lat), "lon": float(lon)}
    # Fallback hard-coded centroids for the most important prefectures
    defaults = {
        "北海道": (43.0642, 141.3469), "青森県": (40.8244, 140.7400),
        "岩手県": (39.7036, 141.1527), "宮城県": (38.2688, 140.8721),
        "秋田県": (39.7186, 140.1023), "山形県": (38.2404, 140.3633),
        "福島県": (37.7500, 140.4676), "茨城県": (36.3418, 140.4468),
        "栃木県": (36.5659, 139.8836), "群馬県": (36.3912, 139.0608),
        "埼玉県": (35.8575, 139.6490), "千葉県": (35.6050, 140.1233),
        "東京都": (35.6762, 139.6503), "神奈川県": (35.4478, 139.6425),
        "新潟県": (37.9026, 139.0232), "富山県": (36.6953, 137.2113),
        "石川県": (36.5944, 136.6256), "福井県": (36.0652, 136.2217),
        "山梨県": (35.6635, 138.5684), "長野県": (36.6513, 138.1810),
        "岐阜県": (35.3912, 136.7223), "静岡県": (34.9769, 138.3831),
        "愛知県": (35.1802, 136.9066), "三重県": (34.7303, 136.5086),
        "滋賀県": (35.0045, 135.8686), "京都府": (35.0211, 135.7556),
        "大阪府": (34.6937, 135.5023), "兵庫県": (34.6913, 135.1830),
        "奈良県": (34.6851, 135.8050), "和歌山県": (34.2260, 135.1675),
        "鳥取県": (35.5011, 134.2351), "島根県": (35.4723, 133.0505),
        "岡山県": (34.6618, 133.9344), "広島県": (34.3853, 132.4553),
        "山口県": (34.1861, 131.4706), "徳島県": (34.0658, 134.5593),
        "香川県": (34.3401, 134.0434), "愛媛県": (33.8417, 132.7657),
        "高知県": (33.5597, 133.5311), "福岡県": (33.6064, 130.4181),
        "佐賀県": (33.2494, 130.2988), "長崎県": (32.7448, 129.8738),
        "熊本県": (32.7898, 130.7417), "大分県": (33.2382, 131.6126),
        "宮崎県": (31.9111, 131.4239), "鹿児島県": (31.5602, 130.5581),
        "沖縄県": (26.2124, 127.6809),
    }
    for name, (lat, lon) in defaults.items():
        if name not in result:
            result[name] = {"lat": lat, "lon": lon}
    return result


# ---------------------------------------------------------------------------
# 2. Crime — historical baseline
# ---------------------------------------------------------------------------

def build_crime_baselines(centroids: dict) -> dict:
    """
    Returns {pref_name: {"historical_monthly_avg": float, "trend": str, "annual_2019": int, "annual_2024": int}}

    Primary source: docs/data/historical_crime_baseline.json
    Fallback:       docs/data/crime_trends.json (national-level by_prefecture)
    """
    hist = load_json(HISTORICAL_CRIME, default=None)
    result = {}

    if hist is not None:
        # Expected shape: {"prefectures": {"東京都": {"monthly_avg": ..., "trend": ..., ...}}}
        pref_data = hist.get("prefectures", hist)  # tolerate flat dict too
        for name in centroids:
            entry = pref_data.get(name, {})
            monthly_avg_raw = entry.get("monthly_avg", entry.get("historical_monthly_avg", 0))
            # monthly_avg can be a dict {crime_type: avg} or a scalar
            if isinstance(monthly_avg_raw, dict):
                monthly_avg_val = sum(monthly_avg_raw.values())
            else:
                monthly_avg_val = float(monthly_avg_raw or 0)
            result[name] = {
                "historical_monthly_avg": round(monthly_avg_val, 1),
                "trend": entry.get("trend", "unknown"),
                "annual_2019": entry.get("annual_2019", 0),
                "annual_2024": entry.get("annual_2024", 0),
            }
        return result

    # Fallback: crime_trends.json
    trends = load_json(CRIME_TRENDS, default=None)
    if trends is not None:
        years = trends.get("years", [])
        by_pref = trends.get("by_prefecture", {})
        # Find indices for 2022/2023 (latest available) and 2006 (oldest)
        idx_latest = len(years) - 1
        idx_early  = 0
        idx_2019   = years.index(2019) if 2019 in years else None
        idx_2023   = years.index(2023) if 2023 in years else idx_latest

        for name in centroids:
            series = by_pref.get(name, [])
            # Filter None
            non_null = [v for v in series if v is not None]
            avg = (sum(non_null) / len(non_null) / 12) if non_null else 0

            early_val  = next((series[i] for i in range(idx_early, min(idx_early+3, len(series))) if series[i] is not None), 0)
            latest_val = next((series[i] for i in range(len(series)-1, max(len(series)-4, -1), -1) if series[i] is not None), 0)
            if early_val and latest_val:
                trend = "decreasing" if latest_val < early_val * 0.95 else ("increasing" if latest_val > early_val * 1.05 else "stable")
            else:
                trend = "unknown"

            v2019 = series[idx_2019] if idx_2019 is not None and idx_2019 < len(series) else 0
            v2023 = series[idx_2023] if idx_2023 < len(series) else 0

            result[name] = {
                "historical_monthly_avg": round(avg, 1),
                "trend": trend,
                "annual_2019": v2019 or 0,
                "annual_2024": v2023 or 0,
            }
        return result

    # Final fallback: zeros
    for name in centroids:
        result[name] = {"historical_monthly_avg": 0, "trend": "unknown", "annual_2019": 0, "annual_2024": 0}
    return result


# ---------------------------------------------------------------------------
# 3. Realtime crime — 7-day counts and top types per prefecture
# ---------------------------------------------------------------------------

def assign_pref_from_coords(lat: float, lon: float, centroids: dict) -> str:
    """Find nearest prefecture centroid."""
    best_name, best_dist = None, float("inf")
    for name, c in centroids.items():
        d = haversine_km(lat, lon, c["lat"], c["lon"])
        if d < best_dist:
            best_dist = d
            best_name = name
    return best_name


def build_realtime_crime(centroids: dict) -> dict:
    """
    Returns {pref_name: {"current_7d_count": int, "top_types": [str, ...]}}
    realtime_slim rows: [lat, lon, crime_type, count, date]
    """
    raw = load_json(REALTIME_SLIM, default=[])
    pref_counts: dict[str, dict[str, int]] = {n: {} for n in centroids}
    pref_totals: dict[str, int] = {n: 0 for n in centroids}

    for row in raw:
        try:
            lat, lon, crime_type = float(row[0]), float(row[1]), str(row[2])
            count = int(row[3]) if len(row) > 3 else 1
        except (ValueError, IndexError, TypeError):
            continue
        pref = assign_pref_from_coords(lat, lon, centroids)
        if pref:
            pref_totals[pref] = pref_totals.get(pref, 0) + count
            bucket = pref_counts.setdefault(pref, {})
            bucket[crime_type] = bucket.get(crime_type, 0) + count

    result = {}
    for name in centroids:
        type_counts = pref_counts.get(name, {})
        top_types = sorted(type_counts, key=lambda x: -type_counts[x])[:3]
        result[name] = {
            "current_7d_count": pref_totals.get(name, 0),
            "top_types": top_types,
        }
    return result


# ---------------------------------------------------------------------------
# 4. Earthquake — historical + latest
# ---------------------------------------------------------------------------

def parse_magnitude(v) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def build_earthquake_profile(centroids: dict) -> dict:
    """
    Returns {pref_name: {"annual_avg_events": float, "max_magnitude_5yr": float, "last_event": str}}
    """
    hist = load_json(HISTORICAL_EQ, default=None)
    latest = load_json(EARTHQUAKES_LATEST, default={"earthquakes": []})

    all_events = []

    # Historical file expected shape: {"earthquakes": [...]} or list
    if isinstance(hist, dict):
        all_events.extend(hist.get("earthquakes", []))
    elif isinstance(hist, list):
        all_events.extend(hist)

    # Latest
    latest_eqs = latest.get("earthquakes", []) if isinstance(latest, dict) else (latest if isinstance(latest, list) else [])
    all_events.extend(latest_eqs)

    # Assign events to prefectures by epicenter name match or coords
    pref_events: dict[str, list] = {n: [] for n in centroids}

    def match_by_epicenter(epicenter: str):
        for name in centroids:
            short = name.rstrip("都道府県")
            if short and short in epicenter:
                return name
        return None

    for eq in all_events:
        if not isinstance(eq, dict):
            continue
        epicenter = eq.get("epicenter", "")
        lat_raw = eq.get("lat", "")
        lon_raw = eq.get("lon", "")
        time_str = eq.get("time", "")
        mag = parse_magnitude(eq.get("magnitude", 0))

        matched = None
        if epicenter:
            matched = match_by_epicenter(epicenter)
        if matched is None and lat_raw and lon_raw:
            try:
                matched = assign_pref_from_coords(float(lat_raw), float(lon_raw), centroids)
            except (ValueError, TypeError):
                pass

        if matched:
            pref_events[matched].append({"time": time_str, "magnitude": mag})

    # Compute metrics
    # Estimate years span for annual avg: historical covers 2021-2025 (~5yr), latest ~3mo
    HIST_YEARS = 5.0  # approximate

    result = {}
    for name in centroids:
        events = pref_events[name]
        annual_avg = round(len(events) / HIST_YEARS, 1) if events else 0.0
        mags = [e["magnitude"] for e in events if e["magnitude"] > 0]
        max_mag = round(max(mags), 1) if mags else 0.0
        times = sorted([e["time"] for e in events if e["time"]], reverse=True)
        last_event = times[0][:10] if times else "unknown"

        result[name] = {
            "annual_avg_events": annual_avg,
            "max_magnitude_5yr": max_mag,
            "last_event": last_event,
        }
    return result


# ---------------------------------------------------------------------------
# 5. Traffic — historical
# ---------------------------------------------------------------------------

def build_traffic_profile(centroids: dict) -> dict:
    """
    Returns {pref_name: {"annual_fatalities": int, "annual_injuries": int, "trend": str}}
    """
    hist = load_json(HISTORICAL_TRAFFIC, default=None)
    result = {}

    if isinstance(hist, dict):
        pref_data = hist.get("prefectures", hist)
        for name in centroids:
            entry = pref_data.get(name, {})
            # Support both nested and flat structures
            fatalities = entry.get("annual_fatalities", entry.get("fatalities_avg", 0)) or 0
            injuries   = entry.get("annual_injuries",   entry.get("injuries_avg",   0)) or 0
            trend      = entry.get("trend", "unknown")
            result[name] = {"annual_fatalities": int(fatalities), "annual_injuries": int(injuries), "trend": trend}
    elif isinstance(hist, list):
        # List of {prefecture, year, fatalities, injuries}
        from collections import defaultdict
        pref_years: dict[str, dict[int, dict]] = defaultdict(dict)
        for row in hist:
            pname = row.get("prefecture", "")
            year  = row.get("year", 0)
            if pname:
                pref_years[pname][year] = row

        for name in centroids:
            years_data = pref_years.get(name, {})
            if not years_data:
                result[name] = {"annual_fatalities": 0, "annual_injuries": 0, "trend": "unknown"}
                continue
            sorted_years = sorted(years_data.keys())
            avg_f = sum(years_data[y].get("fatalities", 0) or 0 for y in sorted_years) / len(sorted_years)
            avg_i = sum(years_data[y].get("injuries",   0) or 0 for y in sorted_years) / len(sorted_years)
            # trend: compare first vs last year
            first_f = years_data[sorted_years[0]].get("fatalities", 0) or 0
            last_f  = years_data[sorted_years[-1]].get("fatalities", 0) or 0
            if first_f and last_f:
                trend = "decreasing" if last_f < first_f * 0.95 else ("increasing" if last_f > first_f * 1.05 else "stable")
            else:
                trend = "unknown"
            result[name] = {"annual_fatalities": int(avg_f), "annual_injuries": int(avg_i), "trend": trend}
    else:
        # No data at all
        for name in centroids:
            result[name] = {"annual_fatalities": 0, "annual_injuries": 0, "trend": "unknown"}

    return result


# ---------------------------------------------------------------------------
# 6. Weather multiplier — nearest AMeDAS station
# ---------------------------------------------------------------------------

def build_weather_multiplier(centroids: dict) -> dict:
    """
    Returns {pref_name: float} — average incident_multiplier from nearby stations.
    """
    amedas = load_json(AMEDAS_CURRENT, default={})
    stations = amedas.get("stations", {}) if isinstance(amedas, dict) else {}

    # Build list of (lat, lon, multiplier)
    station_list = []
    for sid, s in stations.items():
        if isinstance(s, dict):
            lat = s.get("lat")
            lon = s.get("lon")
            mul = s.get("incident_multiplier", 1.0)
            if lat is not None and lon is not None:
                station_list.append((float(lat), float(lon), float(mul or 1.0)))

    result = {}
    for name, c in centroids.items():
        if not station_list:
            result[name] = 1.0
            continue
        # 5 nearest stations, weighted by inverse distance
        dists = []
        for slat, slon, mul in station_list:
            d = haversine_km(c["lat"], c["lon"], slat, slon)
            dists.append((d, mul))
        dists.sort(key=lambda x: x[0])
        top5 = dists[:5]
        # Inverse-distance weighted average
        total_w = sum(1.0 / max(d, 0.1) for d, _ in top5)
        weighted = sum((1.0 / max(d, 0.1)) * mul for d, mul in top5)
        result[name] = round(weighted / total_w, 4) if total_w else 1.0

    return result


# ---------------------------------------------------------------------------
# 7. Composite risk score
# ---------------------------------------------------------------------------

# Reference maxima for normalisation (Japanese national context)
CRIME_MAX_MONTHLY   = 15000   # ~大阪府 peak
CRIME_7D_MAX        = 50
EQ_ANNUAL_MAX       = 300     # 東北 / 関東 high-seismicity
EQ_MAG_MAX          = 7.5
TRAFFIC_FAT_MAX     = 400
TRAFFIC_INJ_MAX     = 60000
WEATHER_MUL_MAX     = 1.5     # upper bound of multiplier


def compute_composite(
    crime_hist: dict,
    crime_rt:   dict,
    eq:         dict,
    traffic:    dict,
    weather_mul: float,
) -> float:
    """Return composite risk score in [0, 1]."""

    # --- Crime sub-score ---
    hist_avg = crime_hist.get("historical_monthly_avg", 0) or 0
    rt_count = crime_rt.get("current_7d_count", 0) or 0
    crime_score = clamp01(
        0.7 * (hist_avg / CRIME_MAX_MONTHLY) +
        0.3 * (rt_count / CRIME_7D_MAX)
    )

    # --- Earthquake sub-score ---
    annual_eq = eq.get("annual_avg_events", 0) or 0
    max_mag   = eq.get("max_magnitude_5yr", 0) or 0
    eq_score = clamp01(
        0.5 * (annual_eq / EQ_ANNUAL_MAX) +
        0.5 * (max_mag   / EQ_MAG_MAX)
    )

    # --- Traffic sub-score ---
    fat = traffic.get("annual_fatalities", 0) or 0
    inj = traffic.get("annual_injuries",   0) or 0
    traffic_score = clamp01(
        0.6 * (fat / TRAFFIC_FAT_MAX) +
        0.4 * (inj / TRAFFIC_INJ_MAX)
    )

    # --- Weather sub-score ---
    weather_score = clamp01((weather_mul - 1.0) / (WEATHER_MUL_MAX - 1.0))

    composite = (
        WEIGHTS["crime"]      * crime_score   +
        WEIGHTS["earthquake"] * eq_score       +
        WEIGHTS["traffic"]    * traffic_score  +
        WEIGHTS["weather"]    * weather_score
    )
    return round(clamp01(composite), 4)


def build_monthly_timeseries(score: float) -> dict:
    """Create 2025 monthly timeseries from a base score."""
    return {f"2025-{m:02d}": round(score, 4) for m in range(1, 13)}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("integrate_historical.py — building prefecture risk profiles", flush=True)

    centroids   = build_centroid_map()
    print(f"  Prefectures loaded: {len(centroids)}")

    print("  Building crime baselines…")
    crime_hist  = build_crime_baselines(centroids)

    print("  Building realtime crime (7d)…")
    crime_rt    = build_realtime_crime(centroids)

    print("  Building earthquake profiles…")
    eq_profiles = build_earthquake_profile(centroids)

    print("  Building traffic profiles…")
    traffic     = build_traffic_profile(centroids)

    print("  Building weather multipliers…")
    weather     = build_weather_multiplier(centroids)

    print("  Computing composite scores…")
    prefectures = {}
    for name in sorted(centroids.keys()):
        c   = centroids[name]
        ch  = crime_hist.get(name, {})
        cr  = crime_rt.get(name, {})
        eq  = eq_profiles.get(name, {})
        tr  = traffic.get(name, {})
        wm  = weather.get(name, 1.0)

        # Determine overall crime trend (prefer historical, fall back to unknown)
        trend_val = ch.get("trend", "unknown")

        composite = compute_composite(ch, cr, eq, tr, wm)

        prefectures[name] = {
            "code": PREF_CODES.get(name, "??"),
            "lat":  c["lat"],
            "lon":  c["lon"],
            "crime": {
                "historical_monthly_avg": ch.get("historical_monthly_avg", 0),
                "trend":                 trend_val,
                "current_7d_count":      cr.get("current_7d_count", 0),
                "top_types":             cr.get("top_types", []),
            },
            "earthquake": {
                "annual_avg_events":  eq.get("annual_avg_events", 0),
                "max_magnitude_5yr":  eq.get("max_magnitude_5yr", 0),
                "last_event":         eq.get("last_event", "unknown"),
            },
            "traffic": {
                "annual_fatalities": tr.get("annual_fatalities", 0),
                "annual_injuries":   tr.get("annual_injuries", 0),
                "trend":             tr.get("trend", "unknown"),
            },
            "weather_multiplier":    wm,
            "composite_risk_score":  composite,
            "timeseries":            build_monthly_timeseries(composite),
        }

    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "weights": WEIGHTS,
        "normalisation": {
            "crime_monthly_max":  CRIME_MAX_MONTHLY,
            "eq_annual_max":      EQ_ANNUAL_MAX,
            "eq_mag_max":         EQ_MAG_MAX,
            "traffic_fat_max":    TRAFFIC_FAT_MAX,
            "traffic_inj_max":    TRAFFIC_INJ_MAX,
            "weather_mul_max":    WEATHER_MUL_MAX,
        },
        "data_sources": {
            "historical_crime":    str(HISTORICAL_CRIME),
            "historical_eq":       str(HISTORICAL_EQ),
            "historical_traffic":  str(HISTORICAL_TRAFFIC),
            "realtime_slim":       str(REALTIME_SLIM),
            "amedas_current":      str(AMEDAS_CURRENT),
            "earthquakes_latest":  str(EARTHQUAKES_LATEST),
        },
        "prefecture_count": len(prefectures),
        "timeseries": {name: p["timeseries"] for name, p in prefectures.items()},
        "prefectures": prefectures,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nOutput written: {OUTPUT}")
    # Quick sanity check
    scores = [v["composite_risk_score"] for v in prefectures.values()]
    print(f"Score range: {min(scores):.4f} – {max(scores):.4f}")
    top3 = sorted(prefectures.items(), key=lambda x: -x[1]["composite_risk_score"])[:3]
    print("Top-3 risk prefectures:")
    for pname, pdata in top3:
        print(f"  {pname}: {pdata['composite_risk_score']:.4f}")


if __name__ == "__main__":
    main()
