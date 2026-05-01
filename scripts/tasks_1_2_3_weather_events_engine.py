#!/usr/bin/env python3
"""
Tasks 1-3: Weather Forecasts, Event Calendar, and Dynamic Risk Engine
=====================================================================
Task 1: JMA weather forecasts + AMEDAS observations
Task 2: Holiday calendar + temporal proxy events
Task 3: Dynamic risk engine with calc_dynamic_expected_harm()
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Any, Tuple
import math
import traceback

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEATHER_DIR = os.path.join(BASE_DIR, "data", "dynamic", "weather")
EVENTS_DIR = os.path.join(BASE_DIR, "data", "dynamic", "events")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")

os.makedirs(WEATHER_DIR, exist_ok=True)
os.makedirs(EVENTS_DIR, exist_ok=True)

# ── Prefecture Codes ───────────────────────────────────────────────────────
PREFECTURE_CODES = {
    "北海道": "011000", "青森県": "020000", "岩手県": "030000", "宮城県": "040000",
    "秋田県": "050000", "山形県": "060000", "福島県": "070000", "茨城県": "080000",
    "栃木県": "090000", "群馬県": "100000", "埼玉県": "110000", "千葉県": "120000",
    "東京都": "130000", "神奈川県": "140000", "新潟県": "150000", "富山県": "160000",
    "石川県": "170000", "福井県": "180000", "山梨県": "190000", "長野県": "200000",
    "岐阜県": "210000", "静岡県": "220000", "愛知県": "230000", "三重県": "240000",
    "滋賀県": "250000", "京都府": "260000", "大阪府": "270000", "兵庫県": "280000",
    "奈良県": "290000", "和歌山県": "300000", "鳥取県": "310000", "島根県": "320000",
    "岡山県": "330000", "広島県": "340000", "山口県": "350000", "徳島県": "360000",
    "香川県": "370000", "愛媛県": "380000", "高知県": "390000", "福岡県": "400000",
    "佐賀県": "410000", "長崎県": "420000", "熊本県": "430000", "大分県": "440000",
    "宮崎県": "450000", "鹿児島県": "460100", "沖縄県": "471000",
}


def fetch_json(url: str, timeout: int = 15) -> Optional[Any]:
    """Fetch JSON from URL with error handling."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (RiskSpace/1.0; research)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [WARN] fetch failed: {url} -> {e}")
        return None


def fetch_text(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch text from URL."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (RiskSpace/1.0; research)",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8").strip()
    except Exception as e:
        print(f"  [WARN] fetch failed: {url} -> {e}")
        return None


def save_json(data: Any, path: str):
    """Save JSON to file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  [OK] Saved: {path} ({os.path.getsize(path):,} bytes)")


# ═══════════════════════════════════════════════════════════════════════════
# TASK 1: Weather Forecasts
# ═══════════════════════════════════════════════════════════════════════════

def weather_code_to_multipliers(code: int) -> Dict[str, float]:
    """Map JMA weather code to incident/escape multipliers."""
    if code >= 500:  # Storm / Typhoon
        return {"incident": 0.6, "escape": 0.5, "category": "storm"}
    elif code >= 400:  # Snow
        return {"incident": 1.1, "escape": 0.7, "category": "snow"}
    elif code in (303, 313):  # Heavy rain
        return {"incident": 1.25, "escape": 0.7, "category": "heavy_rain"}
    elif code >= 300:  # Rain
        return {"incident": 1.15, "escape": 0.85, "category": "rain"}
    elif code >= 200:  # Cloudy
        return {"incident": 1.05, "escape": 1.0, "category": "cloudy"}
    elif code >= 100:  # Clear / Fine
        return {"incident": 1.0, "escape": 1.1, "category": "clear"}
    else:
        return {"incident": 1.0, "escape": 1.0, "category": "unknown"}


def parse_forecast(data: List, pref_name: str, area_code: str) -> Dict:
    """Parse JMA forecast JSON into structured risk data."""
    result = {
        "prefecture": pref_name,
        "area_code": area_code,
        "fetched_at": datetime.now().isoformat(),
        "areas": [],
    }

    if not data or not isinstance(data, list) or len(data) == 0:
        return result

    try:
        ts = data[0].get("timeSeries", [])
        if not ts:
            return result

        # First timeSeries: weather + wind
        weather_ts = ts[0] if len(ts) > 0 else None
        # Second timeSeries: precipitation probability (pops)
        pop_ts = ts[1] if len(ts) > 1 else None
        # Third timeSeries: temperature
        temp_ts = ts[2] if len(ts) > 2 else None

        if weather_ts:
            time_defines = weather_ts.get("timeDefines", [])
            areas = weather_ts.get("areas", [])

            for area in areas:
                area_info = {
                    "name": area["area"]["name"],
                    "area_code": area["area"].get("code", ""),
                    "forecasts": [],
                }

                weather_codes = area.get("weatherCodes", [])
                weathers = area.get("weathers", [])
                winds = area.get("winds", [])

                for i, td in enumerate(time_defines):
                    wcode = int(weather_codes[i]) if i < len(weather_codes) else 100
                    mults = weather_code_to_multipliers(wcode)
                    forecast = {
                        "time": td,
                        "weather_code": wcode,
                        "weather": weathers[i] if i < len(weathers) else "",
                        "wind": winds[i] if i < len(winds) else "",
                        "incident_multiplier": mults["incident"],
                        "escape_multiplier": mults["escape"],
                        "category": mults["category"],
                    }
                    area_info["forecasts"].append(forecast)

                # Add precipitation probability if available
                if pop_ts:
                    pop_areas = pop_ts.get("areas", [])
                    pop_time_defines = pop_ts.get("timeDefines", [])
                    for pa in pop_areas:
                        if pa["area"]["name"] == area["area"]["name"]:
                            pops = pa.get("pops", [])
                            area_info["precipitation_probability"] = [
                                {"time": pop_time_defines[j], "pop": pops[j]}
                                for j in range(min(len(pop_time_defines), len(pops)))
                            ]
                            break

                result["areas"].append(area_info)

    except Exception as e:
        result["parse_error"] = str(e)

    return result


def task1_1_forecasts():
    """Task 1-1: Get 47 prefecture weather forecasts."""
    print("\n" + "=" * 70)
    print("TASK 1-1: Weather Forecasts for 47 Prefectures")
    print("=" * 70)

    all_forecasts = {}
    success = 0
    failed = 0

    for pref_name, area_code in PREFECTURE_CODES.items():
        url = f"https://www.jma.go.jp/bosai/forecast/data/forecast/{area_code}.json"
        print(f"  Fetching {pref_name} ({area_code})...", end=" ")

        data = fetch_json(url)
        if data:
            parsed = parse_forecast(data, pref_name, area_code)
            all_forecasts[area_code] = parsed
            n_areas = len(parsed.get("areas", []))
            print(f"OK ({n_areas} areas)")
            success += 1
        else:
            all_forecasts[area_code] = {
                "prefecture": pref_name,
                "area_code": area_code,
                "error": "fetch_failed",
                "fetched_at": datetime.now().isoformat(),
            }
            print("FAILED")
            failed += 1

        time.sleep(0.3)  # Be polite to JMA servers

    output = {
        "metadata": {
            "source": "JMA Forecast API",
            "fetched_at": datetime.now().isoformat(),
            "total_prefectures": len(PREFECTURE_CODES),
            "success": success,
            "failed": failed,
        },
        "forecasts": all_forecasts,
    }

    save_json(output, os.path.join(WEATHER_DIR, "forecasts_all.json"))
    print(f"\n  Summary: {success}/{len(PREFECTURE_CODES)} prefectures fetched")
    return output


def task1_2_amedas():
    """Task 1-2: Get current AMEDAS observations."""
    print("\n" + "=" * 70)
    print("TASK 1-2: AMEDAS Current Observations")
    print("=" * 70)

    # Step 1: Get latest time
    print("  Getting latest AMEDAS time...")
    latest_time_str = fetch_text("https://www.jma.go.jp/bosai/amedas/data/latest_time.txt")
    if not latest_time_str:
        print("  [ERROR] Could not get latest AMEDAS time")
        return None

    print(f"  Latest time: {latest_time_str}")

    # Parse and format time for URL
    # Format: "2024-01-15T12:00:00+09:00" -> "20240115120000"
    try:
        lt = latest_time_str.replace("-", "").replace(":", "").replace("T", "")
        lt = lt[:14]  # "20240115120000"
    except:
        lt = latest_time_str
    print(f"  Formatted time: {lt}")

    # Step 2: Get station master
    print("  Getting AMEDAS station table...")
    stations = fetch_json("https://www.jma.go.jp/bosai/amedas/const/amedastable.json")
    if not stations:
        print("  [ERROR] Could not get AMEDAS station table")
        return None
    print(f"  Stations: {len(stations)} total")

    # Step 3: Get observations
    obs_url = f"https://www.jma.go.jp/bosai/amedas/data/map/{lt}.json"
    print(f"  Getting observations from {obs_url}...")
    observations = fetch_json(obs_url)
    if not observations:
        print("  [ERROR] Could not get AMEDAS observations")
        return None
    print(f"  Observations: {len(observations)} stations")

    # Step 4: Process and calculate multipliers
    processed = {}
    for stn_id, obs in observations.items():
        station_info = stations.get(stn_id, {})

        # Parse lat/lon from [degrees, minutes] format
        lat_raw = station_info.get("lat", [0, 0])
        lon_raw = station_info.get("lon", [0, 0])
        if isinstance(lat_raw, list) and len(lat_raw) >= 2:
            lat = lat_raw[0] + lat_raw[1] / 60.0
        else:
            lat = float(lat_raw) if lat_raw else 0
        if isinstance(lon_raw, list) and len(lon_raw) >= 2:
            lon = lon_raw[0] + lon_raw[1] / 60.0
        else:
            lon = float(lon_raw) if lon_raw else 0

        # Extract observation values (JMA uses [value, QC_flag] format)
        def get_val(d, key):
            v = d.get(key)
            if isinstance(v, list) and len(v) > 0:
                return v[0]
            return v

        precip_1h = get_val(obs, "precipitation1h") or 0
        precip_10m = get_val(obs, "precipitation10m") or 0
        wind_speed = get_val(obs, "wind") or 0
        wind_dir = get_val(obs, "windDirection") or 0
        temp = get_val(obs, "temp") or 15
        humidity = get_val(obs, "humidity") or 50
        snow_depth = get_val(obs, "snow") or 0

        # Calculate multipliers from observations
        inc_mult = 1.0
        esc_mult = 1.0

        # Precipitation effect
        if precip_1h and isinstance(precip_1h, (int, float)):
            if precip_1h >= 30:  # Heavy rain
                inc_mult *= 1.25
                esc_mult *= 0.7
            elif precip_1h >= 10:  # Moderate rain
                inc_mult *= 1.15
                esc_mult *= 0.85
            elif precip_1h >= 1:  # Light rain
                inc_mult *= 1.1
                esc_mult *= 0.9

        # Wind effect
        if wind_speed and isinstance(wind_speed, (int, float)):
            if wind_speed >= 20:  # Storm
                inc_mult *= 0.7
                esc_mult *= 0.6
            elif wind_speed >= 10:  # Strong wind
                inc_mult *= 0.9
                esc_mult *= 0.8

        # Temperature extreme effect
        if temp and isinstance(temp, (int, float)):
            if temp >= 35:  # Extreme heat
                inc_mult *= 1.15
                esc_mult *= 0.9
            elif temp <= -5:  # Extreme cold
                inc_mult *= 0.9
                esc_mult *= 0.8

        # Snow depth effect
        if snow_depth and isinstance(snow_depth, (int, float)):
            if snow_depth >= 50:
                inc_mult *= 0.8
                esc_mult *= 0.6
            elif snow_depth >= 10:
                inc_mult *= 0.95
                esc_mult *= 0.75

        processed[stn_id] = {
            "name": station_info.get("kjName", station_info.get("knName", stn_id)),
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "prefecture": station_info.get("prefName", ""),
            "observations": {
                "precipitation_1h": precip_1h,
                "precipitation_10m": precip_10m,
                "wind_speed": wind_speed,
                "wind_direction": wind_dir,
                "temperature": temp,
                "humidity": humidity,
                "snow_depth": snow_depth,
            },
            "risk_multipliers": {
                "incident": round(inc_mult, 3),
                "escape": round(esc_mult, 3),
            },
        }

    output = {
        "metadata": {
            "source": "JMA AMEDAS",
            "observation_time": latest_time_str,
            "fetched_at": datetime.now().isoformat(),
            "total_stations": len(processed),
        },
        "stations": processed,
    }

    save_json(output, os.path.join(WEATHER_DIR, "amedas_current.json"))
    print(f"\n  Summary: {len(processed)} stations processed")
    return output


# ═══════════════════════════════════════════════════════════════════════════
# TASK 2: Event Calendar
# ═══════════════════════════════════════════════════════════════════════════

def task2_1_holidays():
    """Task 2-1: Japanese holidays."""
    print("\n" + "=" * 70)
    print("TASK 2-1: Japanese Holidays")
    print("=" * 70)

    data = fetch_json("https://holidays-jp.github.io/api/v1/date.json")
    if not data:
        print("  [ERROR] Could not fetch holidays")
        return {}

    holidays = {}
    for date_str, name in data.items():
        holidays[date_str] = {
            "name": name,
            "type": "national_holiday",
            "risk_multipliers": {
                "incident": 1.15,
                "escape": 0.95,
            },
        }

    print(f"  Holidays loaded: {len(holidays)} entries")
    save_json(holidays, os.path.join(EVENTS_DIR, "holidays.json"))
    return holidays


def task2_2_temporal_proxies():
    """Task 2-2: Generate temporal proxy events."""
    print("\n" + "=" * 70)
    print("TASK 2-2: Temporal Proxy Events")
    print("=" * 70)

    now = datetime.now()
    year = now.year
    events = []

    # Payday events (25th and month-end) for current year
    for month in range(1, 13):
        # 25th payday
        events.append({
            "date": f"{year}-{month:02d}-25",
            "name": f"給料日 ({month}月25日)",
            "type": "payday",
            "risk_multipliers": {"incident": 1.2, "escape": 1.0},
        })
        # Month-end (last day)
        if month == 12:
            last_day = 31
        elif month in (4, 6, 9, 11):
            last_day = 30
        elif month == 2:
            last_day = 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28
        else:
            last_day = 31
        events.append({
            "date": f"{year}-{month:02d}-{last_day}",
            "name": f"月末 ({month}月)",
            "type": "payday",
            "risk_multipliers": {"incident": 1.2, "escape": 1.0},
        })

    # Summer festival season (Jul-Aug, every weekend)
    for month in (7, 8):
        d = date(year, month, 1)
        end = date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)
        while d < end:
            if d.weekday() in (4, 5, 6):  # Fri, Sat, Sun
                events.append({
                    "date": d.isoformat(),
                    "name": f"夏祭りシーズン ({d.strftime('%m/%d')})",
                    "type": "summer_festival",
                    "risk_multipliers": {"incident": 1.4, "escape": 0.9},
                })
            d += timedelta(days=1)

    # Year-end / New Year (Dec 28 - Jan 3)
    for day in range(28, 32):
        events.append({
            "date": f"{year}-12-{day:02d}",
            "name": f"年末年始 (12/{day})",
            "type": "year_end",
            "risk_multipliers": {"incident": 1.1, "escape": 0.9},
            "burglary_multiplier": 1.3,
        })
    for day in range(1, 4):
        events.append({
            "date": f"{year}-01-{day:02d}",
            "name": f"年末年始 (1/{day})",
            "type": "year_end",
            "risk_multipliers": {"incident": 1.1, "escape": 0.9},
            "burglary_multiplier": 1.3,
        })

    # Golden Week (Apr 29 - May 5)
    for day in range(29, 31):
        events.append({
            "date": f"{year}-04-{day:02d}",
            "name": f"ゴールデンウィーク (4/{day})",
            "type": "golden_week",
            "risk_multipliers": {"incident": 1.3, "escape": 0.95},
        })
    for day in range(1, 6):
        events.append({
            "date": f"{year}-05-{day:02d}",
            "name": f"ゴールデンウィーク (5/{day})",
            "type": "golden_week",
            "risk_multipliers": {"incident": 1.3, "escape": 0.95},
        })

    # Obon (Aug 13-17)
    for day in range(13, 18):
        events.append({
            "date": f"{year}-08-{day:02d}",
            "name": f"お盆 (8/{day})",
            "type": "obon",
            "risk_multipliers": {"incident": 1.1, "escape": 0.95},
            "burglary_multiplier": 1.2,
        })

    print(f"  Generated {len(events)} temporal proxy events")
    return events


def task2_3_web_events():
    """Task 2-3: Best-effort scraping of jalan.net fireworks and yahoo events."""
    print("\n" + "=" * 70)
    print("TASK 2-3: Web Event Scraping (best-effort)")
    print("=" * 70)

    web_events = []

    # Try jalan.net fireworks
    print("  Trying jalan.net fireworks...")
    try:
        url = "https://www.jalan.net/event/evt_0013/"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        # Simple extraction of event titles
        import re
        titles = re.findall(r'<h[23][^>]*class="[^"]*title[^"]*"[^>]*>([^<]+)</h', html)
        if not titles:
            titles = re.findall(r'<span class="[^"]*cassette_ttl[^"]*"[^>]*>([^<]+)</span', html)
        for t in titles[:20]:
            web_events.append({
                "name": t.strip(),
                "type": "fireworks",
                "source": "jalan.net",
                "risk_multipliers": {"incident": 1.3, "escape": 0.85},
            })
        print(f"    Found {len(titles[:20])} fireworks events")
    except Exception as e:
        print(f"    [SKIP] jalan.net: {e}")

    # Try Yahoo events
    print("  Trying Yahoo events...")
    try:
        url = "https://event.yahoo.co.jp/"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        import re
        titles = re.findall(r'<h[23][^>]*>([^<]{5,50})</h', html)
        for t in titles[:20]:
            web_events.append({
                "name": t.strip(),
                "type": "event",
                "source": "yahoo",
                "risk_multipliers": {"incident": 1.2, "escape": 0.9},
            })
        print(f"    Found {len(titles[:20])} Yahoo events")
    except Exception as e:
        print(f"    [SKIP] Yahoo events: {e}")

    print(f"  Total web events: {len(web_events)}")
    return web_events


def task2_all():
    """Combine all Task 2 outputs."""
    holidays = task2_1_holidays()
    temporal = task2_2_temporal_proxies()
    web_events = task2_3_web_events()

    all_events = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "sources": ["holidays-jp API", "temporal proxies", "web scraping (best-effort)"],
        },
        "holidays": holidays,
        "temporal_events": temporal,
        "web_events": web_events,
    }

    save_json(all_events, os.path.join(EVENTS_DIR, "all_events.json"))
    return all_events


# ═══════════════════════════════════════════════════════════════════════════
# TASK 3: Dynamic Risk Engine
# ═══════════════════════════════════════════════════════════════════════════

def get_temporal_multipliers(dt: datetime) -> Dict[str, float]:
    """Calculate temporal risk multipliers based on hour, weekday, etc."""
    hour = dt.hour
    weekday = dt.weekday()  # 0=Mon, 6=Sun
    day = dt.day
    month = dt.month

    inc = 1.0
    esc = 1.0

    # Hour-of-day effect
    if 22 <= hour or hour <= 4:  # Late night
        inc *= 1.4
        esc *= 0.7
    elif 18 <= hour < 22:  # Evening
        inc *= 1.2
        esc *= 0.85
    elif 6 <= hour < 9:  # Morning rush
        inc *= 0.9
        esc *= 1.1
    elif 9 <= hour < 18:  # Daytime
        inc *= 0.85
        esc *= 1.15

    # Day-of-week effect
    if weekday == 4:  # Friday
        inc *= 1.15
        esc *= 0.95
    elif weekday == 5:  # Saturday
        inc *= 1.25
        esc *= 0.9
    elif weekday == 6:  # Sunday
        inc *= 1.1
        esc *= 0.95

    # Payday proximity (25th or last day of month)
    if day in (24, 25, 26):
        inc *= 1.2
        esc *= 1.0

    return {"incident": round(inc, 3), "escape": round(esc, 3)}


def get_weather_multipliers(weather_data: Optional[Dict], area_code: str = "130000") -> Dict[str, float]:
    """Get weather multipliers for an area from forecast data."""
    if not weather_data:
        return {"incident": 1.0, "escape": 1.0}

    forecasts = weather_data.get("forecasts", {})
    area_forecast = forecasts.get(area_code, {})
    areas = area_forecast.get("areas", [])

    if not areas:
        return {"incident": 1.0, "escape": 1.0}

    # Use first area's first forecast as current weather
    first_area = areas[0]
    fc_list = first_area.get("forecasts", [])
    if not fc_list:
        return {"incident": 1.0, "escape": 1.0}

    return {
        "incident": fc_list[0].get("incident_multiplier", 1.0),
        "escape": fc_list[0].get("escape_multiplier", 1.0),
    }


def get_event_multipliers(events_data: Optional[Dict], dt: datetime) -> Dict[str, float]:
    """Get event multipliers for a specific date."""
    if not events_data:
        return {"incident": 1.0, "escape": 1.0}

    date_str = dt.strftime("%Y-%m-%d")
    inc = 1.0
    esc = 1.0

    # Check holidays
    holidays = events_data.get("holidays", {})
    if date_str in holidays:
        h = holidays[date_str]
        mults = h.get("risk_multipliers", {})
        inc *= mults.get("incident", 1.0)
        esc *= mults.get("escape", 1.0)

    # Check temporal events
    temporal = events_data.get("temporal_events", [])
    for ev in temporal:
        if ev.get("date") == date_str:
            mults = ev.get("risk_multipliers", {})
            inc = max(inc, mults.get("incident", 1.0))  # Use max, not multiply (avoid stacking)
            esc = min(esc, mults.get("escape", 1.0))

    return {"incident": round(inc, 3), "escape": round(esc, 3)}


def calc_dynamic_expected_harm(
    base_p_incident: float,
    severity: float,
    base_p_escape: float,
    dt: datetime,
    weather_data: Optional[Dict] = None,
    events_data: Optional[Dict] = None,
    area_code: str = "130000",
) -> Dict[str, Any]:
    """
    Calculate dynamic expected harm combining weather, events, and temporal factors.

    Formula:
        incident_mult = min(3.0, weather_inc x event_inc x temporal_inc)
        escape_mult = max(0.2, weather_esc x event_esc x temporal_esc)
        dynamic_EH = min(1.0, base_p_incident x incident_mult) x (severity/5) x
                      (1 - min(1.0, base_p_escape x escape_mult))

    Args:
        base_p_incident: Base probability of incident [0,1]
        severity: Severity score [1-5]
        base_p_escape: Base probability of escape [0,1]
        dt: Datetime for the calculation
        weather_data: Weather forecast data (from task1_1)
        events_data: Events data (from task2)
        area_code: JMA area code for weather lookup

    Returns:
        Dict with multipliers, probabilities, and final expected harm
    """
    # Get component multipliers
    weather_m = get_weather_multipliers(weather_data, area_code)
    event_m = get_event_multipliers(events_data, dt)
    temporal_m = get_temporal_multipliers(dt)

    # Combined multipliers with caps
    incident_mult = min(3.0,
        weather_m["incident"] * event_m["incident"] * temporal_m["incident"]
    )
    escape_mult = max(0.2,
        weather_m["escape"] * event_m["escape"] * temporal_m["escape"]
    )

    # Dynamic expected harm
    effective_p_incident = min(1.0, base_p_incident * incident_mult)
    effective_p_escape = min(1.0, base_p_escape * escape_mult)
    dynamic_EH = effective_p_incident * (severity / 5.0) * (1.0 - effective_p_escape)

    return {
        "input": {
            "base_p_incident": base_p_incident,
            "severity": severity,
            "base_p_escape": base_p_escape,
            "datetime": dt.isoformat(),
            "area_code": area_code,
        },
        "multipliers": {
            "weather": weather_m,
            "event": event_m,
            "temporal": temporal_m,
            "combined_incident": round(incident_mult, 4),
            "combined_escape": round(escape_mult, 4),
        },
        "effective": {
            "p_incident": round(effective_p_incident, 4),
            "p_escape": round(effective_p_escape, 4),
        },
        "dynamic_expected_harm": round(dynamic_EH, 6),
    }


def task3_test(weather_data: Optional[Dict], events_data: Optional[Dict]):
    """Task 3: Test dynamic risk engine with 4 cases."""
    print("\n" + "=" * 70)
    print("TASK 3: Dynamic Risk Engine Tests")
    print("=" * 70)

    year = datetime.now().year

    cases = [
        {
            "name": "Case 1: Shinjuku, payday Friday night 22:00 summer",
            "base_p_incident": 0.35,
            "severity": 3.5,
            "base_p_escape": 0.55,
            "dt": datetime(year, 7, 25, 22, 0),  # July 25th (payday, summer)
            "area_code": "130000",  # Tokyo
        },
        {
            "name": "Case 2: Shinjuku, weekday afternoon 15:00",
            "base_p_incident": 0.35,
            "severity": 3.5,
            "base_p_escape": 0.55,
            "dt": datetime(year, 3, 12, 15, 0),  # Wed in March
            "area_code": "130000",  # Tokyo
        },
        {
            "name": "Case 3: Kobe suburb, New Year's Eve midnight",
            "base_p_incident": 0.15,
            "severity": 2.5,
            "base_p_escape": 0.70,
            "dt": datetime(year, 12, 31, 0, 0),  # Dec 31 midnight
            "area_code": "280000",  # Hyogo
        },
        {
            "name": "Case 4: Rural area, normal day",
            "base_p_incident": 0.05,
            "severity": 2.0,
            "base_p_escape": 0.85,
            "dt": datetime(year, 4, 9, 10, 0),  # Wed morning in April
            "area_code": "200000",  # Nagano
        },
    ]

    results = []
    for c in cases:
        print(f"\n  {c['name']}")
        print(f"  {'─' * 60}")

        result = calc_dynamic_expected_harm(
            base_p_incident=c["base_p_incident"],
            severity=c["severity"],
            base_p_escape=c["base_p_escape"],
            dt=c["dt"],
            weather_data=weather_data,
            events_data=events_data,
            area_code=c["area_code"],
        )

        m = result["multipliers"]
        e = result["effective"]
        print(f"    Weather mult:  inc={m['weather']['incident']:.2f}, esc={m['weather']['escape']:.2f}")
        print(f"    Event mult:    inc={m['event']['incident']:.2f}, esc={m['event']['escape']:.2f}")
        print(f"    Temporal mult: inc={m['temporal']['incident']:.2f}, esc={m['temporal']['escape']:.2f}")
        print(f"    Combined mult: inc={m['combined_incident']:.3f}, esc={m['combined_escape']:.3f}")
        print(f"    Effective:     P(inc)={e['p_incident']:.4f}, P(esc)={e['p_escape']:.4f}")
        print(f"    >>> Dynamic Expected Harm = {result['dynamic_expected_harm']:.6f}")

        result["case_name"] = c["name"]
        results.append(result)

    return results


# ═══════════════════════════════════════════════════════════════════════════
# Save standalone engine script (Task 3 requirement)
# ═══════════════════════════════════════════════════════════════════════════

DYNAMIC_RISK_ENGINE_CODE = '''#!/usr/bin/env python3
"""
Dynamic Risk Engine for Risk Space MCP
=======================================
Combines weather, events, and temporal factors to calculate dynamic expected harm.

Usage:
    from dynamic_risk_engine import calc_dynamic_expected_harm
    result = calc_dynamic_expected_harm(
        base_p_incident=0.35, severity=3.5, base_p_escape=0.55,
        dt=datetime.now(), weather_data=weather, events_data=events,
        area_code="130000"
    )
"""

import json
import os
from datetime import datetime
from typing import Dict, Optional, Any


def get_temporal_multipliers(dt: datetime) -> Dict[str, float]:
    """Calculate temporal risk multipliers based on hour, weekday, payday."""
    hour = dt.hour
    weekday = dt.weekday()  # 0=Mon, 6=Sun
    day = dt.day

    inc = 1.0
    esc = 1.0

    # Hour-of-day
    if 22 <= hour or hour <= 4:
        inc *= 1.4; esc *= 0.7
    elif 18 <= hour < 22:
        inc *= 1.2; esc *= 0.85
    elif 6 <= hour < 9:
        inc *= 0.9; esc *= 1.1
    elif 9 <= hour < 18:
        inc *= 0.85; esc *= 1.15

    # Day-of-week
    if weekday == 4:    inc *= 1.15; esc *= 0.95
    elif weekday == 5:  inc *= 1.25; esc *= 0.9
    elif weekday == 6:  inc *= 1.1;  esc *= 0.95

    # Payday proximity
    if day in (24, 25, 26):
        inc *= 1.2

    return {"incident": round(inc, 3), "escape": round(esc, 3)}


def get_weather_multipliers(weather_data: Optional[Dict], area_code: str = "130000") -> Dict[str, float]:
    """Get weather multipliers for an area from forecast data."""
    if not weather_data:
        return {"incident": 1.0, "escape": 1.0}
    forecasts = weather_data.get("forecasts", {})
    area_forecast = forecasts.get(area_code, {})
    areas = area_forecast.get("areas", [])
    if not areas:
        return {"incident": 1.0, "escape": 1.0}
    first_area = areas[0]
    fc_list = first_area.get("forecasts", [])
    if not fc_list:
        return {"incident": 1.0, "escape": 1.0}
    return {
        "incident": fc_list[0].get("incident_multiplier", 1.0),
        "escape": fc_list[0].get("escape_multiplier", 1.0),
    }


def get_event_multipliers(events_data: Optional[Dict], dt: datetime) -> Dict[str, float]:
    """Get event multipliers for a specific date."""
    if not events_data:
        return {"incident": 1.0, "escape": 1.0}
    date_str = dt.strftime("%Y-%m-%d")
    inc = 1.0
    esc = 1.0
    holidays = events_data.get("holidays", {})
    if date_str in holidays:
        h = holidays[date_str]
        mults = h.get("risk_multipliers", {})
        inc *= mults.get("incident", 1.0)
        esc *= mults.get("escape", 1.0)
    temporal = events_data.get("temporal_events", [])
    for ev in temporal:
        if ev.get("date") == date_str:
            mults = ev.get("risk_multipliers", {})
            inc = max(inc, mults.get("incident", 1.0))
            esc = min(esc, mults.get("escape", 1.0))
    return {"incident": round(inc, 3), "escape": round(esc, 3)}


def calc_dynamic_expected_harm(
    base_p_incident: float,
    severity: float,
    base_p_escape: float,
    dt: datetime,
    weather_data: Optional[Dict] = None,
    events_data: Optional[Dict] = None,
    area_code: str = "130000",
) -> Dict[str, Any]:
    """
    Calculate dynamic expected harm.

    Formula:
        incident_mult = min(3.0, weather_inc x event_inc x temporal_inc)
        escape_mult = max(0.2, weather_esc x event_esc x temporal_esc)
        dynamic_EH = min(1.0, base_p_incident x incident_mult) x (severity/5) x
                      (1 - min(1.0, base_p_escape x escape_mult))
    """
    weather_m = get_weather_multipliers(weather_data, area_code)
    event_m = get_event_multipliers(events_data, dt)
    temporal_m = get_temporal_multipliers(dt)

    incident_mult = min(3.0,
        weather_m["incident"] * event_m["incident"] * temporal_m["incident"])
    escape_mult = max(0.2,
        weather_m["escape"] * event_m["escape"] * temporal_m["escape"])

    effective_p_incident = min(1.0, base_p_incident * incident_mult)
    effective_p_escape = min(1.0, base_p_escape * escape_mult)
    dynamic_EH = effective_p_incident * (severity / 5.0) * (1.0 - effective_p_escape)

    return {
        "input": {
            "base_p_incident": base_p_incident,
            "severity": severity,
            "base_p_escape": base_p_escape,
            "datetime": dt.isoformat(),
            "area_code": area_code,
        },
        "multipliers": {
            "weather": weather_m,
            "event": event_m,
            "temporal": temporal_m,
            "combined_incident": round(incident_mult, 4),
            "combined_escape": round(escape_mult, 4),
        },
        "effective": {
            "p_incident": round(effective_p_incident, 4),
            "p_escape": round(effective_p_escape, 4),
        },
        "dynamic_expected_harm": round(dynamic_EH, 6),
    }


def load_data(base_dir: str = None):
    """Load weather and events data from disk."""
    if base_dir is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    weather_path = os.path.join(base_dir, "data", "dynamic", "weather", "forecasts_all.json")
    events_path = os.path.join(base_dir, "data", "dynamic", "events", "all_events.json")
    weather_data = None
    events_data = None
    if os.path.exists(weather_path):
        with open(weather_path, "r", encoding="utf-8") as f:
            weather_data = json.load(f)
    if os.path.exists(events_path):
        with open(events_path, "r", encoding="utf-8") as f:
            events_data = json.load(f)
    return weather_data, events_data


if __name__ == "__main__":
    weather_data, events_data = load_data()
    result = calc_dynamic_expected_harm(
        base_p_incident=0.35, severity=3.5, base_p_escape=0.55,
        dt=datetime.now(), weather_data=weather_data, events_data=events_data,
    )
    import pprint
    pprint.pprint(result)
'''


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║  Risk Space MCP — Tasks 1-3: Weather, Events, Dynamic Risk Engine  ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print(f"  Start time: {datetime.now().isoformat()}")

    # ── Task 1-1: Weather Forecasts ──
    weather_data = task1_1_forecasts()

    # ── Task 1-2: AMEDAS ──
    amedas_data = task1_2_amedas()

    # ── Task 2: Events ──
    events_data = task2_all()

    # ── Save standalone engine script ──
    engine_path = os.path.join(SCRIPTS_DIR, "dynamic_risk_engine.py")
    with open(engine_path, "w", encoding="utf-8") as f:
        f.write(DYNAMIC_RISK_ENGINE_CODE)
    print(f"\n  [OK] Saved engine: {engine_path}")

    # ── Task 3: Test Dynamic Risk Engine ──
    test_results = task3_test(weather_data, events_data)

    # ── Summary ──
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    forecasts = weather_data.get("metadata", {}) if weather_data else {}
    print(f"  Weather forecasts: {forecasts.get('success', 0)}/{forecasts.get('total_prefectures', 47)} prefectures")
    if amedas_data:
        print(f"  AMEDAS stations:   {amedas_data['metadata']['total_stations']} stations")
    else:
        print(f"  AMEDAS stations:   FAILED")

    n_holidays = len(events_data.get("holidays", {})) if events_data else 0
    n_temporal = len(events_data.get("temporal_events", [])) if events_data else 0
    n_web = len(events_data.get("web_events", [])) if events_data else 0
    print(f"  Events:            {n_holidays} holidays, {n_temporal} temporal, {n_web} web")

    print(f"\n  Dynamic Expected Harm results:")
    for r in test_results:
        print(f"    {r['case_name']}: EH={r['dynamic_expected_harm']:.6f}")

    print(f"\n  Files saved:")
    print(f"    {os.path.join(WEATHER_DIR, 'forecasts_all.json')}")
    print(f"    {os.path.join(WEATHER_DIR, 'amedas_current.json')}")
    print(f"    {os.path.join(EVENTS_DIR, 'holidays.json')}")
    print(f"    {os.path.join(EVENTS_DIR, 'all_events.json')}")
    print(f"    {engine_path}")
    print(f"\n  Done at {datetime.now().isoformat()}")
