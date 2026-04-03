#!/usr/bin/env python3
"""
collect_amedas.py - Collect latest AMEDAS weather observation data from JMA.

Fetches the latest available AMEDAS timestamp, downloads observation data
for all stations, and saves normalized output to data/normalized/weather_amedas.json.
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "normalized")
LOG_DIR = os.path.join(BASE_DIR, "logs")

AMEDAS_LATEST_URL = "https://www.jma.go.jp/bosai/amedas/data/latest_time.txt"
AMEDAS_DATA_URL = "https://www.jma.go.jp/bosai/amedas/data/map/{timestamp}.json"


def log(msg):
    """Log message to stdout and logfile."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, "amedas.log"), "a") as f:
        f.write(line + "\n")


def fetch_json(url):
    """Fetch JSON from URL."""
    req = urllib.request.Request(url, headers={"User-Agent": "RiskSpaceMCP/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_text(url):
    """Fetch text from URL."""
    req = urllib.request.Request(url, headers={"User-Agent": "RiskSpaceMCP/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8").strip()


def get_latest_amedas_time():
    """Get the latest AMEDAS observation timestamp from JMA."""
    try:
        text = fetch_text(AMEDAS_LATEST_URL)
        # Format: "2026-04-04T12:00:00+09:00" or similar
        # Convert to the URL format: YYYYMMDDHHMMSS
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.strftime("%Y%m%d%H%M%S")
    except Exception as e:
        log(f"Failed to get latest time: {e}")
        # Fallback: try current time rounded to 10min
        now = datetime.utcnow() + timedelta(hours=9)  # JST
        now = now.replace(minute=(now.minute // 10) * 10, second=0, microsecond=0)
        return now.strftime("%Y%m%d%H%M%S")


def collect_amedas():
    """Main collection routine."""
    log("Starting AMEDAS collection")

    timestamp = get_latest_amedas_time()
    log(f"Latest AMEDAS time: {timestamp}")

    url = AMEDAS_DATA_URL.format(timestamp=timestamp)
    log(f"Fetching: {url}")

    try:
        raw = fetch_json(url)
    except urllib.error.HTTPError as e:
        log(f"HTTP error {e.code}: {e.reason}")
        # Try 10 minutes earlier
        dt = datetime.strptime(timestamp, "%Y%m%d%H%M%S")
        dt -= timedelta(minutes=10)
        timestamp = dt.strftime("%Y%m%d%H%M%S")
        url = AMEDAS_DATA_URL.format(timestamp=timestamp)
        log(f"Retrying with: {url}")
        raw = fetch_json(url)

    # Normalize: extract key weather fields per station
    normalized = {}
    for station_id, obs in raw.items():
        entry = {
            "station_id": station_id,
            "timestamp": timestamp,
        }
        # Extract available fields (AMEDAS JSON uses nested [value, flag] format)
        for field in ["temp", "humidity", "precipitation10m", "precipitation1h",
                       "precipitation3h", "precipitation24h", "windDirection",
                       "wind", "maxGust", "snow", "snow1h", "snow6h", "snow12h",
                       "snow24h", "sun10m", "sun1h", "pressure"]:
            if field in obs:
                val = obs[field]
                if isinstance(val, list) and len(val) >= 1:
                    entry[field] = val[0]
                else:
                    entry[field] = val

        normalized[station_id] = entry

    # Save
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "weather_amedas.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "collected_at": datetime.now().isoformat(),
            "amedas_time": timestamp,
            "station_count": len(normalized),
            "stations": normalized,
        }, f, ensure_ascii=False, indent=2)

    log(f"Saved {len(normalized)} stations to {out_path}")
    return len(normalized)


if __name__ == "__main__":
    try:
        count = collect_amedas()
        print(f"OK: {count} stations collected")
    except Exception as e:
        log(f"FATAL: {e}")
        sys.exit(1)
