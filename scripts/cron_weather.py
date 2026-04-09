#!/usr/bin/env python3
import json
import os
from datetime import datetime

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(BASE_DIR, "docs", "data", "amedas_current.json")

LATEST_TIME_URL = "https://www.jma.go.jp/bosai/amedas/data/latest_time.txt"
STATION_TABLE_URL = "https://www.jma.go.jp/bosai/amedas/const/amedastable.json"
MAP_URL_TMPL = "https://www.jma.go.jp/bosai/amedas/data/map/{time}.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RiskSpaceMCP/1.0)"}


def fetch_json(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_text(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text.strip()


def deg_min_to_deg(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, list) and len(v) >= 2:
        deg = float(v[0])
        minute = float(v[1])
        return deg + minute / 60.0
    return None


def get_obs_value(v):
    if isinstance(v, list) and v:
        return v[0]
    return v


def to_float_or_none(v):
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def calc_multipliers(precip10m, wind_ms, temp_c, snow_cm):
    incident = 1.0
    escape = 1.0

    if precip10m is not None:
        if precip10m >= 2.0:
            incident *= 1.12
            escape *= 1.25
        elif precip10m >= 1.0:
            incident *= 1.08
            escape *= 1.15
        elif precip10m > 0:
            incident *= 1.03
            escape *= 1.08

    if wind_ms is not None:
        if wind_ms >= 15:
            incident *= 0.90
            escape *= 0.80
        elif wind_ms >= 10:
            incident *= 0.95
            escape *= 0.88
        elif wind_ms >= 7:
            incident *= 0.98
            escape *= 0.94

    if temp_c is not None:
        if temp_c >= 35 or temp_c <= -5:
            incident *= 1.12
            escape *= 1.18
        elif temp_c >= 30 or temp_c <= 0:
            incident *= 1.07
            escape *= 1.10

    if snow_cm is not None:
        if snow_cm >= 20:
            incident *= 1.15
            escape *= 1.30
        elif snow_cm >= 5:
            incident *= 1.08
            escape *= 1.15

    return round(incident, 3), round(escape, 3)


def main():
    latest_time_raw = fetch_text(LATEST_TIME_URL)
    print(f"[INFO] latest_time_raw={latest_time_raw}")
    # Convert ISO format "2026-04-09T10:20:00+09:00" to "20260409102000"
    import re as _re
    latest_time = _re.sub(r'[^0-9]', '', latest_time_raw)[:14]
    print(f"[INFO] latest_time_url={latest_time}")

    station_table = fetch_json(STATION_TABLE_URL)
    obs_map = fetch_json(MAP_URL_TMPL.format(time=latest_time))

    stations = {}

    for station_id, meta in station_table.items():
        obs = obs_map.get(station_id)
        if not obs:
            continue

        lat = deg_min_to_deg(meta.get("lat"))
        lon = deg_min_to_deg(meta.get("lon"))

        precip10m = to_float_or_none(get_obs_value(obs.get("precipitation10m")))
        wind_ms = to_float_or_none(get_obs_value(obs.get("wind")))
        temp_c = to_float_or_none(get_obs_value(obs.get("temp")))
        snow_cm = to_float_or_none(get_obs_value(obs.get("snow")))

        incident_multiplier, escape_multiplier = calc_multipliers(precip10m, wind_ms, temp_c, snow_cm)

        stations[station_id] = {
            "name": meta.get("kjName") or meta.get("enName") or "",
            "lat": round(lat, 6) if isinstance(lat, float) else None,
            "lon": round(lon, 6) if isinstance(lon, float) else None,
            "precip10m": precip10m,
            "wind_ms": wind_ms,
            "temp_c": temp_c,
            "snow_cm": snow_cm,
            "incident_multiplier": incident_multiplier,
            "escape_multiplier": escape_multiplier,
        }

    out = {
        "source": "JMA AMEDAS",
        "observation_time": latest_time,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "station_count": len(stations),
        "stations": stations,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)

    print(f"[DONE] wrote {OUT_PATH}, stations={len(stations)}")


if __name__ == "__main__":
    main()
