#!/usr/bin/env python3
"""
Task 1: Weather Layer Integration
- Fetch AMEDAS latest observations → weather risk events
- Fetch weather warnings for all 47 prefectures
- Generate heat_weather.json for dashboard
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NORM_DIR = os.path.join(BASE, "data", "normalized")
DASH_DATA = os.path.join(BASE, "dashboard", "data")
DOCS_DATA = os.path.join(BASE, "docs", "data")

os.makedirs(NORM_DIR, exist_ok=True)
os.makedirs(DASH_DATA, exist_ok=True)
os.makedirs(DOCS_DATA, exist_ok=True)


def fetch_json(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RiskSpaceMCP/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, Exception) as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"  WARN: Failed to fetch {url}: {e}", file=sys.stderr)
                return None


def fetch_text(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RiskSpaceMCP/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8").strip()
    except Exception as e:
        print(f"  WARN: Failed to fetch {url}: {e}", file=sys.stderr)
        return None


def deg_min_to_decimal(arr):
    """Convert [degrees, minutes] to decimal degrees."""
    if not arr or len(arr) < 2:
        return None
    return arr[0] + arr[1] / 60.0


def compute_severity(precip10m, wind, snow_depth):
    """Compute severity based on thresholds."""
    sev = 0
    reason = []
    if precip10m is not None and precip10m >= 20:
        sev = max(sev, 4)
        reason.append(f"precip={precip10m}mm/10min")
    elif precip10m is not None and precip10m >= 5:
        sev = max(sev, 2)
        reason.append(f"precip={precip10m}mm/10min")
    if wind is not None and wind >= 20:
        sev = max(sev, 3)
        reason.append(f"wind={wind}m/s")
    elif wind is not None and wind >= 15:
        sev = max(sev, 2)
        reason.append(f"wind={wind}m/s")
    if snow_depth is not None and snow_depth >= 30:
        sev = max(sev, 3)
        reason.append(f"snow={snow_depth}cm")
    elif snow_depth is not None and snow_depth >= 20:
        sev = max(sev, 2)
        reason.append(f"snow={snow_depth}cm")
    return sev, reason


# ── 1-1: AMEDAS data ──────────────────────────────────────

def fetch_amedas():
    print("=== Task 1-1: AMEDAS Observation Data ===")

    # Get latest time
    latest_raw = fetch_text("https://www.jma.go.jp/bosai/amedas/data/latest_time.txt")
    if not latest_raw:
        print("  ERROR: Could not fetch latest_time.txt")
        return []
    print(f"  Latest time: {latest_raw}")

    # Parse time for URL: "2026-04-04T03:30:00+09:00" → "20260404033000"
    dt = datetime.fromisoformat(latest_raw)
    time_str = dt.strftime("%Y%m%d%H%M%S")
    print(f"  URL time param: {time_str}")

    # Get station master
    print("  Fetching station master...")
    stations = fetch_json("https://www.jma.go.jp/bosai/amedas/const/amedastable.json")
    if not stations:
        print("  ERROR: Could not fetch amedastable.json")
        return []
    print(f"  Stations: {len(stations)}")

    # Build station coords lookup
    station_coords = {}
    for sid, info in stations.items():
        lat = deg_min_to_decimal(info.get("lat"))
        lon = deg_min_to_decimal(info.get("lon"))
        if lat and lon:
            station_coords[sid] = {
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "name": info.get("kjName", ""),
                "en_name": info.get("enName", ""),
            }

    # Get observation data
    obs_url = f"https://www.jma.go.jp/bosai/amedas/data/map/{time_str}.json"
    print(f"  Fetching observations: {obs_url}")
    obs = fetch_json(obs_url)
    if not obs:
        print("  ERROR: Could not fetch observation data")
        return []
    print(f"  Observation stations: {len(obs)}")

    # Process into risk events
    events = []
    risk_count = 0
    for sid, data in obs.items():
        if sid not in station_coords:
            continue
        coord = station_coords[sid]

        precip10m = data.get("precipitation10m", [None])[0] if "precipitation10m" in data else None
        wind_speed = data.get("wind", [None])[0] if "wind" in data else None
        # Snow fields: snowDepth, snow1h, snow6h, snow12h, snow24h (may not be present)
        snow_depth = None
        for snow_key in ("snowDepth", "snow", "snow1h"):
            if snow_key in data:
                snow_depth = data[snow_key][0]
                break

        sev, reasons = compute_severity(precip10m, wind_speed, snow_depth)

        if sev >= 2:
            risk_count += 1
            subtype = "heavy_rain" if precip10m and precip10m >= 5 else \
                      "strong_wind" if wind_speed and wind_speed >= 15 else \
                      "heavy_snow" if snow_depth and snow_depth >= 20 else "weather_alert"
            events.append({
                "event_id": f"amedas_{sid}_{time_str}",
                "lat": coord["lat"],
                "lon": coord["lon"],
                "layer": "weather",
                "subtype": subtype,
                "severity": sev,
                "occurred_at": latest_raw,
                "source": "jma_amedas",
                "station_name": coord["name"],
                "details": "; ".join(reasons),
                "precip10m": precip10m,
                "wind": wind_speed,
                "snow_depth": snow_depth,
            })

    print(f"  Risk events (sev>=2): {risk_count}")

    # Save
    out_path = os.path.join(NORM_DIR, "weather_amedas.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    print(f"  Saved: {out_path} ({len(events)} events)")

    return events


# ── 1-2: Weather Warnings ────────────────────────────────

# All 47 prefecture codes
PREF_CODES = [
    "010000", "020000", "030000", "040000", "050000", "060000", "070000",
    "080000", "090000", "100000", "110000", "120000", "130000", "140000",
    "150000", "160000", "170000", "180000", "190000", "200000", "210000",
    "220000", "230000", "240000", "250000", "260000", "270000", "280000",
    "290000", "300000", "310000", "320000", "330000", "340000", "350000",
    "360000", "370000", "380000", "390000", "400000", "410000", "420000",
    "430000", "440000", "450000", "460000", "471000",
]

PREF_NAMES = {
    "010000": "北海道", "020000": "青森", "030000": "岩手", "040000": "宮城",
    "050000": "秋田", "060000": "山形", "070000": "福島", "080000": "茨城",
    "090000": "栃木", "100000": "群馬", "110000": "埼玉", "120000": "千葉",
    "130000": "東京", "140000": "神奈川", "150000": "新潟", "160000": "富山",
    "170000": "石川", "180000": "福井", "190000": "山梨", "200000": "長野",
    "210000": "岐阜", "220000": "静岡", "230000": "愛知", "240000": "三重",
    "250000": "滋賀", "260000": "京都", "270000": "大阪", "280000": "兵庫",
    "290000": "奈良", "300000": "和歌山", "310000": "鳥取", "320000": "島根",
    "330000": "岡山", "340000": "広島", "350000": "山口", "360000": "徳島",
    "370000": "香川", "380000": "愛媛", "390000": "高知", "400000": "福岡",
    "410000": "佐賀", "420000": "長崎", "430000": "熊本", "440000": "大分",
    "450000": "宮崎", "460000": "鹿児島", "471000": "沖縄",
}

WARNING_CODE_MAP = {
    "02": "暴風雪警報", "03": "大雨警報", "04": "洪水警報",
    "05": "暴風警報", "06": "大雪警報", "07": "波浪警報",
    "08": "高潮警報", "10": "大雨注意報", "12": "大雪注意報",
    "13": "風雪注意報", "14": "雷注意報", "15": "強風注意報",
    "16": "波浪注意報", "17": "融雪注意報", "18": "洪水注意報",
    "19": "高潮注意報", "20": "濃霧注意報", "21": "乾燥注意報",
    "22": "なだれ注意報", "23": "低温注意報", "24": "霜注意報",
    "25": "着氷注意報", "26": "着雪注意報",
    "32": "暴風雪特別警報", "33": "大雨特別警報", "35": "暴風特別警報",
    "36": "大雪特別警報", "37": "波浪特別警報", "38": "高潮特別警報",
}


def extract_active_warnings(data, pref_code):
    """Extract active warnings from a prefecture warning JSON."""
    warnings = []
    if not data or "areaTypes" not in data:
        return warnings

    report_time = data.get("reportDatetime", "")

    for area_type in data["areaTypes"]:
        for area in area_type.get("areas", []):
            area_name = area.get("name", "")
            area_code = area.get("code", "")
            for w in area.get("warnings", []):
                status = w.get("status", "")
                if status in ("発表", "継続"):
                    code = w.get("code", "")
                    warnings.append({
                        "pref_code": pref_code,
                        "pref_name": PREF_NAMES.get(pref_code, ""),
                        "area_name": area_name,
                        "area_code": area_code,
                        "warning_code": code,
                        "warning_name": WARNING_CODE_MAP.get(code, f"警報コード{code}"),
                        "status": status,
                        "report_time": report_time,
                    })
    return warnings


def fetch_warnings():
    print("\n=== Task 1-2: Weather Warnings (47 prefectures) ===")
    all_warnings = []
    ok = 0
    fail = 0

    for i, pcode in enumerate(PREF_CODES):
        url = f"https://www.jma.go.jp/bosai/warning/data/warning/{pcode}.json"
        data = fetch_json(url)
        if data:
            ws = extract_active_warnings(data, pcode)
            all_warnings.extend(ws)
            ok += 1
            if ws:
                print(f"  [{i+1}/47] {PREF_NAMES.get(pcode, pcode)}: {len(ws)} active warnings")
        else:
            fail += 1
        # Be polite to JMA servers
        if i % 10 == 9:
            time.sleep(0.5)

    print(f"  Fetched: {ok}/47 prefectures, {fail} failed")
    print(f"  Total active warnings: {len(all_warnings)}")

    out_path = os.path.join(NORM_DIR, "weather_warnings.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_warnings, f, ensure_ascii=False, indent=2)
    print(f"  Saved: {out_path}")

    return all_warnings


# ── 1-3: Generate heat_weather.json ──────────────────────

def generate_heat_weather(amedas_events):
    print("\n=== Task 1-3: Generate heat_weather.json ===")

    # Combine AMEDAS risk events into heatmap points [lat, lon, intensity]
    points = []
    for ev in amedas_events:
        intensity = ev["severity"] / 5.0
        points.append([ev["lat"], ev["lon"], round(intensity, 3)])

    print(f"  Heatmap points: {len(points)}")

    for dest in [DASH_DATA, DOCS_DATA]:
        out_path = os.path.join(dest, "heat_weather.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(points, f)
        print(f"  Saved: {out_path}")


# ── Main ──────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Weather Layer Integration")
    print("=" * 60)

    amedas_events = fetch_amedas()
    warnings = fetch_warnings()
    generate_heat_weather(amedas_events)

    print("\n" + "=" * 60)
    print(f"DONE: {len(amedas_events)} AMEDAS risk events, {len(warnings)} active warnings")
    print("=" * 60)
