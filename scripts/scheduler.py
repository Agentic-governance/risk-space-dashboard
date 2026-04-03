#!/usr/bin/env python3
"""
scheduler.py - Periodic task scheduler for Risk Space MCP data collection.

Uses the `schedule` library to run crawlers and integration scripts
on a fixed schedule. This script defines the schedule but does NOT
start the run loop by default.

To actually run the scheduler:
    python scheduler.py --run

Schedule:
    Every 30 min: fushinsha_crawler.py
    Every 30 min: collect_new_sources.py
    Every 10 min: collect_amedas.py (weather)
    Every day at 00:00: integrate_full.py
"""

import os
import sys
import subprocess
import time
from datetime import datetime

import schedule

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(os.path.dirname(SCRIPTS_DIR), "logs")


def log(msg):
    """Log message to stdout and logfile."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [scheduler] {msg}"
    print(line, flush=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, "scheduler.log"), "a") as f:
        f.write(line + "\n")


def run_script(name):
    """Run a script in the scripts directory and log the result."""
    path = os.path.join(SCRIPTS_DIR, name)
    log(f"Starting {name}")
    try:
        result = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=SCRIPTS_DIR,
        )
        if result.returncode == 0:
            log(f"OK: {name} (exit 0)")
            if result.stdout.strip():
                log(f"  stdout: {result.stdout.strip()[:200]}")
        else:
            log(f"FAIL: {name} (exit {result.returncode})")
            if result.stderr.strip():
                log(f"  stderr: {result.stderr.strip()[:200]}")
    except subprocess.TimeoutExpired:
        log(f"TIMEOUT: {name} (>300s)")
    except Exception as e:
        log(f"ERROR: {name}: {e}")


# ---- Define scheduled tasks ----

schedule.every(30).minutes.do(run_script, "fushinsha_crawler.py")
schedule.every(30).minutes.do(run_script, "collect_new_sources.py")
schedule.every(10).minutes.do(run_script, "collect_amedas.py")
schedule.every().day.at("00:00").do(run_script, "integrate_full.py")

log("Schedule configured:")
log("  Every 30 min: fushinsha_crawler.py")
log("  Every 30 min: collect_new_sources.py")
log("  Every 10 min: collect_amedas.py")
log("  Every day at 00:00: integrate_full.py")


if __name__ == "__main__":
    if "--run" in sys.argv:
        log("Starting scheduler loop (Ctrl+C to stop)")
        while True:
            schedule.run_pending()
            time.sleep(1)
    else:
        log("Schedule defined but NOT running. Use --run to start the loop.")
        print("\nDefined jobs:")
        for job in schedule.get_jobs():
            print(f"  {job}")
        print("\nRun with --run flag to start the scheduler loop.")
