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
EARTHQUAKES_PATH = os.path.join(BASE_DIR, "docs", "data", "earthquakes_latest.json")
TRAFFIC_PATH = os.path.join(BASE_DIR, "docs", "data", "traffic_incidents_latest.json")

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


def _severity_from_mag(mag) -> int:
    """Map earthquake magnitude to severity 1-5."""
    try:
        m = float(mag)
    except (TypeError, ValueError):
        return 2
    if m >= 7.0:
        return 5
    if m >= 6.0:
        return 4
    if m >= 5.0:
        return 3
    if m >= 4.0:
        return 2
    return 1


def append_earthquakes(slim_rows: list) -> int:
    """Read earthquakes_latest.json and append entries. Returns count added."""
    if not os.path.exists(EARTHQUAKES_PATH):
        print("[INFO] earthquakes_latest.json not found, skipping")
        return 0
    try:
        with open(EARTHQUAKES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[WARN] Could not read earthquakes_latest.json: {e}")
        return 0

    # Normalise to a flat list of earthquake records
    if isinstance(data, list):
        quakes = data
    elif isinstance(data, dict):
        quakes = data.get("earthquakes", data.get("features", data.get("items", [])))
    else:
        quakes = []

    added = 0
    today = datetime.now().strftime("%Y-%m-%d")
    for q in quakes:
        # Support both flat dict and GeoJSON Feature formats
        if isinstance(q, dict) and q.get("type") == "Feature":
            props = q.get("properties", {})
            coords = (q.get("geometry") or {}).get("coordinates", [])
            lat = coords[1] if len(coords) >= 2 else None
            lon = coords[0] if len(coords) >= 2 else None
            mag = props.get("mag", props.get("magnitude"))
            date = props.get("time", props.get("date", today))
        else:
            lat = q.get("lat")
            lon = q.get("lon")
            mag = q.get("mag", q.get("magnitude"))
            date = q.get("time", q.get("date", today))

        if lat is None or lon is None:
            continue
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            continue

        # Truncate date to YYYY-MM-DD
        date_str = str(date)[:10] if date else today
        mag_str = f"{float(mag):.1f}" if mag is not None else "?"
        slim_rows.append([
            round(lat, 4),
            round(lon, 4),
            f"地震M{mag_str}",
            _severity_from_mag(mag),
            date_str,
        ])
        added += 1

    print(f"[INFO] Appended {added} earthquake entries to slim output")
    return added


def append_traffic(slim_rows: list) -> int:
    """Read traffic_incidents_latest.json and append entries with lat/lon. Returns count added."""
    if not os.path.exists(TRAFFIC_PATH):
        print("[INFO] traffic_incidents_latest.json not found, skipping")
        return 0
    try:
        with open(TRAFFIC_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[WARN] Could not read traffic_incidents_latest.json: {e}")
        return 0

    if isinstance(data, list):
        incidents = data
    elif isinstance(data, dict):
        incidents = data.get("incidents", data.get("features", data.get("items", [])))
    else:
        incidents = []

    added = 0
    today = datetime.now().strftime("%Y-%m-%d")
    for inc in incidents:
        if isinstance(inc, dict) and inc.get("type") == "Feature":
            props = inc.get("properties", {})
            coords = (inc.get("geometry") or {}).get("coordinates", [])
            lat = coords[1] if len(coords) >= 2 else None
            lon = coords[0] if len(coords) >= 2 else None
            label = props.get("subtype", props.get("type", "交通事故"))
            date = props.get("date", props.get("time", today))
            severity = int(props.get("severity", 3))
        else:
            lat = inc.get("lat")
            lon = inc.get("lon")
            if lat is None or lon is None:
                continue  # skip entries without coordinates
            label = inc.get("subtype", inc.get("type", "交通事故"))
            date = inc.get("date", inc.get("time", today))
            severity = int(inc.get("severity", 3))

        if lat is None or lon is None:
            continue
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            continue

        date_str = str(date)[:10] if date else today
        slim_rows.append([
            round(lat, 4),
            round(lon, 4),
            str(label) if label else "交通事故",
            severity,
            date_str,
        ])
        added += 1

    print(f"[INFO] Appended {added} traffic incident entries to slim output")
    return added


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

        raw_date = evt.get("date")
        date_str = raw_date or datetime.now().strftime("%Y-%m-%d")

        # Filter out events older than 7 days
        if raw_date:
            try:
                evt_date = datetime.strptime(str(raw_date)[:10], "%Y-%m-%d").date()
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

    # Append earthquake and traffic data from other sources
    append_earthquakes(slim_rows)
    append_traffic(slim_rows)

    # Guarantee minimum row count for dashboard.
    min_rows = 50
    if len(slim_rows) < min_rows and os.path.exists(HIST_BASELINE_PATH):
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
            need = min_rows - len(slim_rows)
            for total, lat, lon, pref in hotspots[:max(0, need)]:
                slim_rows.append([
                    round(float(lat), 4),
                    round(float(lon), 4),
                    f"履歴ホットスポット:{pref}",
                    2,
                    today,
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
    summary["source"] = "police_hp_direct+earthquake+traffic"

    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False)

    print(f"[DONE] realtime_slim.json: {len(slim_rows)} rows (skipped {skipped} no-geo, {filtered_old} older than 7d)")


if __name__ == "__main__":
    main()
