#!/usr/bin/env python3
"""
cron_earthquake.py — JMA Earthquake Data Fetcher
=================================================
Fetches the latest earthquake list from JMA and enriches each entry
with detail data. Filters to the last 24 hours and computes an
earthquake_multiplier for the risk model.

Output: docs/data/earthquakes_latest.json

Usage:
    python scripts/cron_earthquake.py
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(BASE_DIR, "docs", "data", "earthquakes_latest.json")
NORM_DIR = os.path.join(BASE_DIR, "data", "normalized")

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
os.makedirs(NORM_DIR, exist_ok=True)

# ── Constants ──────────────────────────────────────────────────────────────
JMA_LIST_URL = "https://www.jma.go.jp/bosai/quake/data/list.json"
JMA_DETAIL_URL = "https://www.jma.go.jp/bosai/quake/data/{event_id}.json"
HEADERS = {"User-Agent": "RiskSpaceMCP/1.0 (cron_earthquake)"}
JST = timezone(timedelta(hours=9))

# ── HTTP helpers ───────────────────────────────────────────────────────────

def fetch_json(url: str, retries: int = 3):
    """Fetch JSON from URL with exponential-backoff retry. Returns None on failure."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            code = getattr(e, "code", None)
            print(f"  [WARN] fetch_json attempt {attempt + 1}/{retries} failed: {url} -> {e}",
                  file=sys.stderr)
            if code == 404:
                return None  # don't retry 404
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
        except Exception as e:
            print(f"  [WARN] fetch_json unexpected error: {url} -> {e}", file=sys.stderr)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None

# ── Coordinate parsing ────────────────────────────────────────────────────

# JMA list.json encodes coords in "code" field as ISO 6709 notation:
#   "+34.7+135.2-10000/" → lat=34.7, lon=135.2, depth=10km
_ISO6709_RE = re.compile(
    r"([+-]\d+\.?\d*)"   # lat
    r"([+-]\d+\.?\d*)"   # lon
    r"([+-]\d+)?"        # depth (mm, optional)
)

def parse_iso6709(code: str):
    """Parse ISO 6709 compact notation. Returns (lat, lon, depth_km) or (None, None, None)."""
    if not code:
        return None, None, None
    m = _ISO6709_RE.match(code.strip())
    if not m:
        return None, None, None
    lat = float(m.group(1))
    lon = float(m.group(2))
    depth_km = None
    if m.group(3):
        # depth is in metres with sign; negative = below surface (normal)
        depth_km = abs(int(m.group(3))) / 1000
    return lat, lon, depth_km

# ── Multiplier calculation ────────────────────────────────────────────────

def calc_earthquake_multiplier(magnitude: float, depth_km: Optional[float], max_shindo: Optional[float]) -> float:
    """
    Compute earthquake_multiplier for the risk model.

    Logic (additive contributions, then clamped):
    - magnitude drives the base (logistic curve around M5)
    - shallow depth amplifies (depth < 30 km → +20%)
    - high max_shindo adds direct observed-intensity boost

    Returns a multiplier in [1.0, 5.0].
    """
    mult = 1.0

    # Magnitude contribution: M < 3 → negligible; M7+ → major
    if magnitude >= 7.0:
        mult += 3.0
    elif magnitude >= 6.0:
        mult += 2.0
    elif magnitude >= 5.0:
        mult += 1.2
    elif magnitude >= 4.0:
        mult += 0.5
    elif magnitude >= 3.0:
        mult += 0.15

    # Depth contribution: shallower quakes are more damaging
    if depth_km is not None:
        if depth_km <= 10:
            mult += 0.5
        elif depth_km <= 30:
            mult += 0.3
        elif depth_km <= 60:
            mult += 0.1

    # Observed intensity (shindo) contribution
    if max_shindo is not None:
        if max_shindo >= 6:    # 震度6強 / 6弱
            mult += 1.0
        elif max_shindo >= 5:  # 震度5強 / 5弱
            mult += 0.5
        elif max_shindo >= 4:
            mult += 0.2
        elif max_shindo >= 3:
            mult += 0.05

    return round(min(mult, 5.0), 3)

# ── Shindo parsing ─────────────────────────────────────────────────────────

_SHINDO_MAP = {
    "1": 1, "2": 2, "3": 3, "4": 4,
    "5-": 4.5, "5+": 5.5, "5弱": 4.5, "5強": 5.5,
    "6-": 5.8, "6+": 6.2, "6弱": 5.8, "6強": 6.2,
    "7": 7,
}

def parse_shindo(raw: Optional[str]) -> Optional[float]:
    """Convert JMA shindo string to a numeric value for calculations."""
    if raw is None:
        return None
    raw = str(raw).strip()
    if raw in _SHINDO_MAP:
        return _SHINDO_MAP[raw]
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None

# ── Time parsing ───────────────────────────────────────────────────────────

def parse_jma_time(raw: Optional[str]) -> Optional[datetime]:
    """Parse JMA time string. Handles ISO-8601 and compact 'YYYYMMDDHHmmss' formats."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, AttributeError):
        pass
    # Compact: "20260405100321"
    try:
        return datetime.strptime(raw[:14], "%Y%m%d%H%M%S").replace(tzinfo=JST)
    except (ValueError, TypeError):
        return None

# ── Detail fetching ────────────────────────────────────────────────────────

def enrich_from_detail(event_id: str, base: dict) -> dict:
    """
    Fetch per-event detail JSON and extract lat/lon/depth if not already present.
    JMA detail files don't always exist for older entries — failures are silent.
    """
    url = JMA_DETAIL_URL.format(event_id=event_id)
    detail = fetch_json(url)
    if not detail:
        return base

    # detail is a list of report objects; take the first one
    if isinstance(detail, list) and detail:
        detail = detail[0]

    if not isinstance(detail, dict):
        return base

    # Try to extract coordinates from Body/Earthquake/Hypocenter
    try:
        hypo = detail["Body"]["Earthquake"]["Hypocenter"]["Area"]
        coord_str = hypo.get("Coordinate", "")
        if coord_str and (base.get("lat") is None or base.get("lat") == ""):
            lat, lon, depth_km = parse_iso6709(coord_str)
            if lat is not None:
                base["lat"] = round(lat, 4)
                base["lon"] = round(lon, 4)
            if depth_km is not None and base.get("depth") in (None, ""):
                base["depth_km"] = round(depth_km, 1)
    except (KeyError, TypeError):
        pass

    # Try max intensity from detail
    try:
        intensity_str = detail["Body"]["Intensity"]["Observation"]["MaxInt"]
        if intensity_str and base.get("max_shindo") is None:
            base["max_shindo_raw"] = intensity_str
            base["max_shindo"] = parse_shindo(intensity_str)
    except (KeyError, TypeError):
        pass

    return base

# ── Main pipeline ──────────────────────────────────────────────────────────

def main():
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(hours=24)

    print("=" * 60)
    print("cron_earthquake.py — JMA Earthquake Fetcher")
    print(f"  now_utc  : {now_utc.isoformat(timespec='seconds')}")
    print(f"  cutoff   : {cutoff.isoformat(timespec='seconds')} (last 24h)")
    print("=" * 60)

    # 1. Fetch list
    print(f"\n[1] Fetching earthquake list: {JMA_LIST_URL}")
    raw_list = fetch_json(JMA_LIST_URL)
    if not raw_list:
        print("[FATAL] Could not fetch JMA earthquake list.", file=sys.stderr)
        sys.exit(1)
    print(f"  Total entries in list: {len(raw_list)}")

    # 2. Filter to last 24 hours
    recent = []
    for entry in raw_list:
        # JMA list has "at" (announce time) and "en_anm" fields;
        # use "at" (発生時刻) if available, else "areaNameEn"
        time_raw = entry.get("at") or entry.get("anm") or ""
        dt = parse_jma_time(time_raw)
        if dt is None:
            continue
        # Ensure timezone-aware for comparison
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        dt_utc = dt.astimezone(timezone.utc)
        if dt_utc >= cutoff:
            recent.append((dt_utc, entry))

    print(f"  Entries within last 24h: {len(recent)}")

    if not recent:
        print("  No recent earthquakes. Writing empty result.")

    # 3. Process each entry
    earthquakes = []
    for idx, (dt_utc, entry) in enumerate(recent):
        event_id = entry.get("json", "").replace(".json", "").strip("/") or \
                   entry.get("id", "")

        # Parse list-level fields
        code = entry.get("cod", "") or entry.get("code", "")
        lat, lon, depth_km = parse_iso6709(code)

        # If list gave us lat/lon directly (some versions do)
        if lat is None:
            lat_raw = entry.get("lat", "")
            lon_raw = entry.get("lon", "")
            try:
                lat = float(lat_raw) if lat_raw not in ("", None) else None
                lon = float(lon_raw) if lon_raw not in ("", None) else None
            except (ValueError, TypeError):
                lat = lon = None

        mag_raw = entry.get("mag", "") or entry.get("magnitude", "")
        try:
            magnitude = float(mag_raw)
        except (ValueError, TypeError):
            magnitude = None

        max_int_raw = entry.get("maxi", "") or entry.get("max_intensity", "")
        max_shindo = parse_shindo(max_int_raw if max_int_raw not in ("", None) else None)

        location_name = (
            entry.get("en_anm") or entry.get("anm") or
            entry.get("epicenter") or entry.get("location", "")
        )

        depth_raw = entry.get("dep", "") or entry.get("depth", "")
        if depth_km is None and depth_raw not in ("", None):
            try:
                # JMA sometimes gives depth in km directly
                depth_km = float(str(depth_raw).replace("km", "").strip())
            except (ValueError, TypeError):
                pass

        record = {
            "event_id": event_id,
            "time": dt_utc.isoformat(timespec="seconds"),
            "time_jst": dt_utc.astimezone(JST).isoformat(timespec="seconds"),
            "lat": round(lat, 4) if lat is not None else None,
            "lon": round(lon, 4) if lon is not None else None,
            "magnitude": magnitude,
            "depth_km": round(depth_km, 1) if depth_km is not None else None,
            "max_shindo_raw": max_int_raw if max_int_raw not in ("", None) else None,
            "max_shindo": max_shindo,
            "location_name": location_name,
            "source": "jma_quake_list",
        }

        # 4. Enrich from per-event detail (best-effort, skip if no event_id)
        if event_id:
            record = enrich_from_detail(event_id, record)
            # Polite rate-limiting to JMA servers
            if idx < len(recent) - 1:
                time.sleep(0.3)

        # 5. Compute earthquake_multiplier
        record["earthquake_multiplier"] = calc_earthquake_multiplier(
            magnitude or 0.0,
            record.get("depth_km"),
            record.get("max_shindo"),
        )

        earthquakes.append(record)
        mag_str = f"M{magnitude}" if magnitude else "M?"
        shindo_str = f"shindo={max_int_raw}" if max_int_raw not in ("", None) else "shindo=?"
        print(f"  [{idx + 1:3d}] {mag_str:6s} {shindo_str:12s} {location_name[:30]:<30s} "
              f"mult={record['earthquake_multiplier']:.2f}")

    # 6. Save output
    output = {
        "metadata": {
            "source": "Japan Meteorological Agency (JMA)",
            "url": JMA_LIST_URL,
            "fetched_at": now_utc.isoformat(timespec="seconds"),
            "filter_window_hours": 24,
            "total_count": len(earthquakes),
            "description": (
                "Earthquakes in the last 24 hours with coordinates, magnitude, "
                "observed shindo, and earthquake_multiplier for the risk model."
            ),
        },
        "earthquakes": earthquakes,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Also write a copy to normalized/
    norm_path = os.path.join(NORM_DIR, "earthquakes_latest.json")
    with open(norm_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[DONE] {len(earthquakes)} earthquakes written to:")
    print(f"  {OUT_PATH}")
    print(f"  {norm_path}")
    if earthquakes:
        max_mult = max(e["earthquake_multiplier"] for e in earthquakes)
        max_mag = max((e["magnitude"] or 0) for e in earthquakes)
        print(f"  max magnitude     : M{max_mag}")
        print(f"  max multiplier    : {max_mult:.2f}")


if __name__ == "__main__":
    main()
