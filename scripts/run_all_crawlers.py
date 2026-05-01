#!/usr/bin/env python3
"""Run all crawlers in sequence with error handling."""
import subprocess
import sys
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = [
    ("Gaccom Crawl", "scripts/cron_crawl.py"),
    ("AMeDAS Weather", "scripts/cron_weather.py"),
    ("Fushinsha Full", "scripts/crawl_fushinsha_full.py"),
]

def main():
    print(f"[ORCHESTRATOR] Starting at {datetime.now().isoformat()}")
    results = []

    for name, script in SCRIPTS:
        script_path = os.path.join(BASE_DIR, script)
        print(f"\n{'='*60}")
        print(f"[RUN] {name}: {script}")
        print(f"{'='*60}")

        try:
            result = subprocess.run(
                [sys.executable, script_path],
                cwd=BASE_DIR,
                timeout=600,  # 10 min max per script
                capture_output=False,
            )
            status = "OK" if result.returncode == 0 else f"FAIL (rc={result.returncode})"
        except subprocess.TimeoutExpired:
            status = "TIMEOUT"
        except Exception as e:
            status = f"ERROR: {e}"

        results.append((name, status))
        print(f"[RESULT] {name}: {status}")

    print(f"\n{'='*60}")
    print("[SUMMARY]")
    for name, status in results:
        print(f"  {name}: {status}")

    failures = [r for r in results if r[1] != "OK"]
    if failures:
        print(f"\n[WARN] {len(failures)} crawler(s) had issues")
        sys.exit(1)
    else:
        print(f"\n[OK] All crawlers completed successfully")
        sys.exit(0)

if __name__ == "__main__":
    main()
