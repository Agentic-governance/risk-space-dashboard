#!/usr/bin/env python3
"""Check freshness of critical JSON data files."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent

SEARCH_DIRS = [
    BASE_DIR / "docs" / "data",
    BASE_DIR / "data" / "realtime",
    BASE_DIR / "data" / "historical",
]

CRITICAL_FILES = {
    "realtime_slim.json",
    "amedas_current.json",
    "events_7days.json",
    "summary.json",
}

MAX_AGE_HOURS = 2
HIST_WARN_DAYS = 7

# Minimum row/event counts
MIN_SLIM_ROWS = 50
MIN_EVENTS = 20


def check_files():
    now = datetime.now(timezone.utc)

    # Build a map: filename -> Path for all JSON files found
    found: dict[str, Path] = {}
    for d in SEARCH_DIRS:
        if d.exists():
            for p in d.glob("*.json"):
                found[p.name] = p

    rows = []
    any_problem = False

    # Collect all JSON files from search dirs for display
    all_names = set(found.keys()) | CRITICAL_FILES

    for name in sorted(all_names):
        is_critical = name in CRITICAL_FILES
        path = found.get(name)

        if path is None:
            status = "MISSING" if is_critical else "OK"
            rows.append((name, "-", "-", status, is_critical))
            if is_critical:
                any_problem = True
            continue

        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        age_hours = (now - mtime).total_seconds() / 3600

        if is_critical:
            status = "OK" if age_hours <= MAX_AGE_HOURS else "STALE"
            if status != "OK":
                any_problem = True
        else:
            status = "OK"
            if "data/historical" in str(path) and age_hours > HIST_WARN_DAYS * 24:
                status = "WARN"

        rows.append((name, mtime.strftime("%Y-%m-%d %H:%M UTC"), f"{age_hours:.2f}", status, is_critical))

    # Print table
    col_w = [40, 22, 10, 8]
    header = (
        f"{'FILENAME':<{col_w[0]}} {'LAST_MODIFIED':<{col_w[1]}} {'AGE_HOURS':>{col_w[2]}} {'STATUS':<{col_w[3]}}"
    )
    sep = "-" * (sum(col_w) + 3)
    print(header)
    print(sep)
    for name, mtime_str, age_str, status, is_critical in rows:
        marker = "*" if is_critical else " "
        print(
            f"{marker}{name:<{col_w[0]-1}} {mtime_str:<{col_w[1]}} {age_str:>{col_w[2]}} {status:<{col_w[3]}}"
        )

    print()
    print(f"* = critical file (must be updated within {MAX_AGE_HOURS}h)")
    print(f"Checked at: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"HISTORICAL WARN threshold: {HIST_WARN_DAYS} days")

    return any_problem


def check_data_volume(found: dict[str, Path]) -> bool:
    """Check minimum row/event counts. Returns True if any volume check fails."""
    low_volume = False

    # Check realtime_slim.json row count
    slim_path = found.get("realtime_slim.json")
    if slim_path and slim_path.exists():
        try:
            with open(slim_path, "r", encoding="utf-8") as f:
                slim_data = json.load(f)
            n = len(slim_data) if isinstance(slim_data, list) else 0
            if n < MIN_SLIM_ROWS:
                print(f"[WARN] LOW DATA: realtime_slim has only {n} rows (minimum {MIN_SLIM_ROWS} expected)")
                low_volume = True
        except Exception as e:
            print(f"[WARN] Could not read realtime_slim.json for volume check: {e}")

    # Check events_7days.json event count
    events_path = found.get("events_7days.json")
    if events_path and events_path.exists():
        try:
            with open(events_path, "r", encoding="utf-8") as f:
                events_data = json.load(f)
            if isinstance(events_data, dict):
                n = len(events_data.get("events", []))
            elif isinstance(events_data, list):
                n = len(events_data)
            else:
                n = 0
            if n < MIN_EVENTS:
                print(f"[WARN] LOW DATA: events_7days has only {n} events (minimum {MIN_EVENTS} expected)")
                low_volume = True
        except Exception as e:
            print(f"[WARN] Could not read events_7days.json for volume check: {e}")

    return low_volume


def main():
    # Build found map once for reuse
    found: dict[str, Path] = {}
    for d in SEARCH_DIRS:
        if d.exists():
            for p in d.glob("*.json"):
                found[p.name] = p

    any_problem = check_files()
    low_volume = check_data_volume(found)

    if low_volume and not any_problem:
        # Files are fresh but data volume is low -> exit code 2 (warning)
        sys.exit(2)
    elif any_problem:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
