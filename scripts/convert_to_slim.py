#!/usr/bin/env python3
"""Convert crawl_fushinsha_full.py output (events_7days.json) to realtime_slim.json format.

realtime_slim format: [[lat, lon, subtype_ja, severity, date], ...]
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS_PATH = os.path.join(BASE_DIR, "docs", "data", "events_7days.json")
SLIM_PATH = os.path.join(BASE_DIR, "docs", "data", "realtime_slim.json")
SUMMARY_PATH = os.path.join(BASE_DIR, "docs", "data", "summary.json")
HIST_BASELINE_PATH = os.path.join(BASE_DIR, "docs", "data", "historical_crime_baseline.json")

# Map English subtypes back to Japanese for dashboard compatibility
SUBTYPE_JA = {
    "suspicious_person": "不審者",
    "solicitation": "声かけ",
    "stalking": "つきまとい",
    "groping": "痴漢",
    "voyeurism": "盗撮",
    "indecent_act": "わいせつ",
    "exposure": "露出",
    "purse_snatching": "ひったくり",
    "robbery": "強盗",
    "assault": "暴行",
    "weapon": "凶器",
    "bear": "クマ",
    "fraud": "特殊詐欺",
    "dangerous_animal": "危険動物",
    "monkey": "サル",
    "boar": "イノシシ",
    "other": "その他",
}

SEVERITY_MAP = {
    "不審者": 2, "声かけ": 2, "つきまとい": 3,
    "痴漢": 4, "盗撮": 3, "わいせつ": 4,
    "露出": 3, "ひったくり": 4, "強盗": 5,
    "暴行": 4, "凶器": 5, "クマ": 3,
    "特殊詐欺": 3, "危険動物": 3, "サル": 2,
    "イノシシ": 3, "その他": 2,
}


def main():
    if not os.path.exists(EVENTS_PATH):
        print(f"[WARN] No events file at {EVENTS_PATH}, skipping conversion")
        sys.exit(0)

    with open(EVENTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    events = data.get("events", [])
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).date()
    print(f"[INFO] Loaded {len(events)} events; filtering to >= {cutoff}")

    slim_rows = []
    skipped = 0
    filtered_old = 0

    for evt in events:
        lat = evt.get("lat")
        lon = evt.get("lon")
        if lat is None or lon is None:
            skipped += 1
            continue

        date_str = evt.get("date") or datetime.now().strftime("%Y-%m-%d")

        # Filter out events older than 7 days
        try:
            evt_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            if evt_date < cutoff:
                filtered_old += 1
                continue
        except ValueError:
            pass  # Keep events with unparseable dates

        subtype_en = evt.get("subtype", "other")
        subtype_ja = SUBTYPE_JA.get(subtype_en, subtype_en)
        severity = SEVERITY_MAP.get(subtype_ja, 2)

        slim_rows.append([
            round(float(lat), 4),
            round(float(lon), 4),
            subtype_ja,
            severity,
            date_str,
        ])

    # Optional historical layer from baseline hotspots (top 50 by incident count).
    if os.path.exists(HIST_BASELINE_PATH):
        try:
            with open(HIST_BASELINE_PATH, "r", encoding="utf-8") as f:
                baseline = json.load(f)
            pref_map = baseline.get("prefectures", {}) if isinstance(baseline, dict) else {}
            hotspots = []
            for pref, item in pref_map.items():
                lat = item.get("lat")
                lon = item.get("lon")
                total = int(item.get("total_incidents", 0) or 0)
                if lat is None or lon is None:
                    continue
                hotspots.append((total, lat, lon, pref))
            hotspots.sort(key=lambda x: x[0], reverse=True)
            today = datetime.now().strftime("%Y-%m-%d")
            for total, lat, lon, pref in hotspots[:50]:
                slim_rows.append([
                    round(float(lat), 4),
                    round(float(lon), 4),
                    f"履歴ホットスポット:{pref}",
                    2,
                    today,
                    "historical",
                ])
        except Exception as e:
            print(f"[WARN] Could not append historical hotspots: {e}")

    # Write slim
    os.makedirs(os.path.dirname(SLIM_PATH), exist_ok=True)
    with open(SLIM_PATH, "w", encoding="utf-8") as f:
        json.dump(slim_rows, f, ensure_ascii=False)

    # Update summary
    summary = {}
    if os.path.exists(SUMMARY_PATH):
        with open(SUMMARY_PATH, "r", encoding="utf-8") as f:
            summary = json.load(f)

    summary["generated_at"] = datetime.now().isoformat(timespec="seconds")
    summary["total_rows"] = len(slim_rows)
    summary["skipped_no_geo"] = skipped
    summary["source"] = "police_hp_direct"

    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False)

    print(f"[DONE] realtime_slim.json: {len(slim_rows)} rows (skipped {skipped} no-geo, {filtered_old} older than 7d)")


if __name__ == "__main__":
    main()
