#!/usr/bin/env python3
"""Check freshness of critical JSON data files."""

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


def main():
    any_problem = check_files()
    sys.exit(1 if any_problem else 0)


if __name__ == "__main__":
    main()
