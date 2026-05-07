#!/usr/bin/env python3
"""Pipeline SLO Gate: Fail the pipeline if data quality is below thresholds.

Brain recommendation: "パイプライン成功=データ妥当性通過に変更"
- If events < MIN_EVENTS → exit 1 (fail the workflow)
- If geocode_rate < MIN_GEO_RATE → exit 1
- Reports metrics for observability

Usage: Run AFTER crawl + convert, BEFORE git commit.
If this exits non-zero, the workflow should NOT commit empty data.
"""
import json
import os
import sys
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS_PATH = os.path.join(BASE_DIR, "docs", "data", "events_7days.json")
SLIM_PATH = os.path.join(BASE_DIR, "docs", "data", "realtime_slim.json")

# SLO Thresholds (Brain-recommended)
MIN_EVENTS = 10          # Minimum events to consider crawl successful
MIN_SLIM_ROWS = 30       # Minimum map rows
MIN_GEO_RATE = 0.40      # At least 40% of events must be geocoded
MAX_DATE_MISSING = 0.80   # No more than 80% date-less events

def main():
    print(f"[SLO GATE] Checking data quality thresholds...")
    print(f"  Checked at: {datetime.now(timezone.utc).isoformat()}")

    violations = []

    # Check events_7days.json
    if os.path.exists(EVENTS_PATH):
        with open(EVENTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        events = data.get("events", [])
        stats = data.get("stats", {})
        total = len(events)
        
        print(f"  events_7days: {total} events")
        
        if total < MIN_EVENTS:
            violations.append(f"EVENTS_COUNT={total} < {MIN_EVENTS}")
        
        # Check date missing rate
        date_missing = sum(1 for e in events if not e.get("date"))
        date_missing_rate = date_missing / total if total > 0 else 1.0
        print(f"  date_missing_rate: {date_missing_rate:.1%}")
        if date_missing_rate > MAX_DATE_MISSING:
            violations.append(f"DATE_MISSING={date_missing_rate:.0%} > {MAX_DATE_MISSING:.0%}")

        # Check geocode rate
        geocoded = sum(1 for e in events if e.get("lat") is not None)
        geo_rate = geocoded / total if total > 0 else 0
        print(f"  geocode_rate: {geo_rate:.1%}")
        if geo_rate < MIN_GEO_RATE:
            violations.append(f"GEO_RATE={geo_rate:.0%} < {MIN_GEO_RATE:.0%}")
    else:
        violations.append("events_7days.json MISSING")

    # Check realtime_slim.json
    if os.path.exists(SLIM_PATH):
        with open(SLIM_PATH, "r", encoding="utf-8") as f:
            slim = json.load(f)
        slim_count = len(slim) if isinstance(slim, list) else 0
        print(f"  realtime_slim: {slim_count} rows")
        if slim_count < MIN_SLIM_ROWS:
            violations.append(f"SLIM_ROWS={slim_count} < {MIN_SLIM_ROWS}")
    else:
        violations.append("realtime_slim.json MISSING")

    # Verdict
    if violations:
        print(f"\n[SLO GATE] ❌ FAILED — {len(violations)} violation(s):")
        for v in violations:
            print(f"  - {v}")
        print(f"\n  Data will NOT be committed. Previous good data preserved.")
        sys.exit(1)
    else:
        print(f"\n[SLO GATE] ✓ PASSED — All thresholds met")
        sys.exit(0)


if __name__ == "__main__":
    main()
