#!/usr/bin/env python3
"""Produce a one-line pipeline health report for all output JSONs.

Output format:
  HEALTH: events={N} slim={N} quake={N} traffic={N} weather={N} geo_rate={pct}%
  or
  DEGRADED: events={N} slim={N} quake={N} traffic={N} weather={N} geo_rate={pct}%

Thresholds:
  events  >= 20
  slim    >= 50
  quake   >= 1
  traffic >= 1
  geo_rate >= 60  (% of slim rows that have real coordinates, not 0/0)
"""
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
DOCS_DATA = BASE_DIR / "docs" / "data"

THRESHOLDS = {
    "events": 20,
    "slim": 50,
    "quake": 1,
    "traffic": 1,
    "geo_rate": 60,
}


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def count_events() -> int:
    data = _load_json(DOCS_DATA / "events_7days.json")
    if data is None:
        return 0
    if isinstance(data, dict):
        return len(data.get("events", []))
    if isinstance(data, list):
        return len(data)
    return 0


def count_slim() -> int:
    data = _load_json(DOCS_DATA / "realtime_slim.json")
    if isinstance(data, list):
        return len(data)
    return 0


def count_quake() -> int:
    data = _load_json(DOCS_DATA / "earthquakes_latest.json")
    if data is None:
        return 0
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        items = data.get("earthquakes", data.get("features", data.get("items", [])))
        return len(items) if isinstance(items, list) else 0
    return 0


def count_traffic() -> int:
    data = _load_json(DOCS_DATA / "traffic_incidents_latest.json")
    if data is None:
        return 0
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        items = data.get("incidents", data.get("features", data.get("items", [])))
        return len(items) if isinstance(items, list) else 0
    return 0


def count_weather() -> int:
    """Return number of AMeDAS stations present in current weather data."""
    data = _load_json(DOCS_DATA / "amedas_current.json")
    if data is None:
        return 0
    if isinstance(data, dict):
        # Could be {stations: [...]} or a flat dict of station records
        stations = data.get("stations", None)
        if isinstance(stations, list):
            return len(stations)
        # Flat dict keyed by station id
        return len(data)
    if isinstance(data, list):
        return len(data)
    return 0


def calc_geo_rate() -> float:
    """% of slim rows with non-zero lat/lon."""
    data = _load_json(DOCS_DATA / "realtime_slim.json")
    if not isinstance(data, list) or len(data) == 0:
        return 0.0
    geocoded = sum(
        1 for row in data
        if isinstance(row, list) and len(row) >= 2
        and row[0] != 0 and row[1] != 0
    )
    return round(geocoded / len(data) * 100, 1)


def main():
    metrics = {
        "events": count_events(),
        "slim": count_slim(),
        "quake": count_quake(),
        "traffic": count_traffic(),
        "weather": count_weather(),
        "geo_rate": calc_geo_rate(),
    }

    degraded_fields = [
        k for k, threshold in THRESHOLDS.items()
        if metrics.get(k, 0) < threshold
    ]

    prefix = "DEGRADED" if degraded_fields else "HEALTH"
    report = (
        f"{prefix}: "
        f"events={metrics['events']} "
        f"slim={metrics['slim']} "
        f"quake={metrics['quake']} "
        f"traffic={metrics['traffic']} "
        f"weather={metrics['weather']} "
        f"geo_rate={metrics['geo_rate']}%"
    )
    print(report)

    if degraded_fields:
        print(f"[DEGRADED fields] {', '.join(degraded_fields)}")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
