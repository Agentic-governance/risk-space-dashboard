"""
fetch_historical_earthquakes.py
One-time script to fetch historical earthquake data (2021-2025) for Japan
from the USGS FDSNWS event API.

Output: data/historical/earthquakes_2021_2025.json
"""

import json
import math
import os
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"

# Japan bounding box
LAT_MIN, LAT_MAX = 24.0, 46.0
LON_MIN, LON_MAX = 122.0, 146.0

# Only earthquakes M3+ to keep volume manageable
MAG_MIN = 3.0

# Years to fetch
YEARS = list(range(2021, 2026))  # 2021 – 2025 inclusive

# Rate-limit: 1 request per second (USGS asks ≤ ~1 req/sec for automation)
SLEEP_BETWEEN_REQUESTS = 1.0

# Retry settings
MAX_RETRIES = 5
RETRY_BACKOFF_BASE = 2  # seconds; exponential backoff

# Output path (relative to this script's grandparent, i.e. risk_space/)
SCRIPT_DIR = Path(__file__).parent
RISK_SPACE_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = RISK_SPACE_DIR / "data" / "historical"
OUTPUT_FILE = OUTPUT_DIR / "earthquakes_2021_2025.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fetch_json(url: str, params: dict) -> dict:
    """HTTP GET with retry + exponential backoff. Returns parsed JSON."""
    from urllib.parse import urlencode

    full_url = f"{url}?{urlencode(params)}"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = Request(full_url, headers={"User-Agent": "risk-space-mcp/1.0 (research)"})
            with urlopen(req, timeout=60) as resp:
                raw = resp.read()
            return json.loads(raw)
        except HTTPError as e:
            if e.code == 429 or e.code >= 500:
                wait = RETRY_BACKOFF_BASE ** attempt
                print(f"  HTTP {e.code} on attempt {attempt}/{MAX_RETRIES}, retrying in {wait}s …")
                time.sleep(wait)
            else:
                raise
        except URLError as e:
            wait = RETRY_BACKOFF_BASE ** attempt
            print(f"  URLError {e.reason} on attempt {attempt}/{MAX_RETRIES}, retrying in {wait}s …")
            time.sleep(wait)
    raise RuntimeError(f"Failed to fetch after {MAX_RETRIES} attempts: {full_url}")


def month_windows(year: int):
    """Yield (starttime, endtime) strings for every month in `year`."""
    for month in range(1, 13):
        start = date(year, month, 1)
        # Last day of month
        if month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)
        yield start.isoformat(), end.isoformat()


def grid_cell(lat: float, lon: float, cell_deg: float = 0.5) -> str:
    """Return a string key for a spatial grid cell."""
    row = math.floor(lat / cell_deg)
    col = math.floor(lon / cell_deg)
    cell_lat = round(row * cell_deg, 2)
    cell_lon = round(col * cell_deg, 2)
    return f"{cell_lat:.2f},{cell_lon:.2f}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def fetch_year(year: int) -> list[dict]:
    """Fetch all earthquakes for a single year, month-by-month."""
    events = []
    for start, end in month_windows(year):
        print(f"  Fetching {start} – {end} …", end=" ", flush=True)
        params = {
            "format": "geojson",
            "starttime": start,
            "endtime": end,
            "minlatitude": LAT_MIN,
            "maxlatitude": LAT_MAX,
            "minlongitude": LON_MIN,
            "maxlongitude": LON_MAX,
            "minmagnitude": MAG_MIN,
            "orderby": "time-asc",
            "limit": 20000,  # USGS max per request
        }
        data = fetch_json(BASE_URL, params)
        features = data.get("features", [])
        print(f"{len(features):,} events")

        for feat in features:
            props = feat.get("properties", {})
            coords = feat.get("geometry", {}).get("coordinates", [None, None, None])
            events.append({
                "time": props.get("time"),          # epoch ms
                "mag": props.get("mag"),
                "lat": coords[1],
                "lon": coords[0],
                "depth_km": coords[2],
                "place": props.get("place"),
                "id": feat.get("id"),
            })

        time.sleep(SLEEP_BETWEEN_REQUESTS)

    return events


def aggregate(events: list[dict]) -> dict:
    """Compute monthly counts and spatial density (0.5° grid)."""
    monthly: dict[str, int] = defaultdict(int)
    spatial: dict[str, dict] = defaultdict(lambda: {"count": 0, "max_mag": 0.0, "total_mag": 0.0})

    for ev in events:
        # Monthly
        ts_ms = ev.get("time")
        if ts_ms is not None:
            ts_s = ts_ms / 1000
            import datetime
            dt = datetime.datetime.utcfromtimestamp(ts_s)
            ym = dt.strftime("%Y-%m")
            monthly[ym] += 1

        # Spatial
        lat, lon, mag = ev.get("lat"), ev.get("lon"), ev.get("mag")
        if lat is not None and lon is not None:
            key = grid_cell(lat, lon)
            cell = spatial[key]
            cell["count"] += 1
            if mag is not None:
                if mag > cell["max_mag"]:
                    cell["max_mag"] = mag
                cell["total_mag"] += mag

    # Compute mean magnitude per cell
    for key, cell in spatial.items():
        cnt = cell["count"]
        cell["mean_mag"] = round(cell["total_mag"] / cnt, 2) if cnt else 0.0
        del cell["total_mag"]
        # Round max_mag
        cell["max_mag"] = round(cell["max_mag"], 2)
        # Add lat/lon for convenience
        lat_str, lon_str = key.split(",")
        cell["cell_lat"] = float(lat_str)
        cell["cell_lon"] = float(lon_str)

    return {
        "monthly_counts": dict(sorted(monthly.items())),
        "spatial_density": {k: v for k, v in sorted(spatial.items(), key=lambda x: -x[1]["count"])},
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_events: list[dict] = []

    for year in YEARS:
        print(f"\n=== Year {year} ===")
        year_events = fetch_year(year)
        all_events.extend(year_events)
        print(f"  → {len(year_events):,} events collected for {year}")

    print(f"\nTotal events: {len(all_events):,}")
    print("Computing aggregations …")
    agg = aggregate(all_events)

    # Summary stats
    mags = [e["mag"] for e in all_events if e.get("mag") is not None]
    summary = {
        "total_events": len(all_events),
        "period": f"{YEARS[0]}-01-01 to {YEARS[-1]}-12-31",
        "bbox": {"lat_min": LAT_MIN, "lat_max": LAT_MAX, "lon_min": LON_MIN, "lon_max": LON_MAX},
        "mag_min_filter": MAG_MIN,
        "mag_stats": {
            "min": round(min(mags), 2) if mags else None,
            "max": round(max(mags), 2) if mags else None,
            "mean": round(sum(mags) / len(mags), 2) if mags else None,
        },
        "source": "USGS FDSNWS event API",
        "fetched_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }

    output = {
        "summary": summary,
        "monthly_counts": agg["monthly_counts"],
        "spatial_density_grid_0_5deg": agg["spatial_density"],
        "events": all_events,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = OUTPUT_FILE.stat().st_size / 1024 / 1024
    print(f"\nSaved → {OUTPUT_FILE}  ({size_mb:.1f} MB)")
    print("Summary:")
    print(f"  Total events : {summary['total_events']:,}")
    print(f"  Mag range    : {summary['mag_stats']['min']} – {summary['mag_stats']['max']}")
    print(f"  Mag mean     : {summary['mag_stats']['mean']}")
    print(f"  Monthly bins : {len(agg['monthly_counts'])}")
    print(f"  Grid cells   : {len(agg['spatial_density'])}")


if __name__ == "__main__":
    main()
