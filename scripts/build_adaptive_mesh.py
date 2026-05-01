#!/usr/bin/env python3
"""
Build adaptive quadtree mesh for risk scoring.

Resolution policy (based on event count in coarse 0.05° cell):
  ultra (0.0025°): count >= 200
  high  (0.005°):  count >= 50
  mid   (0.01°):   count >= 10
  low   (0.05°):   count < 10

Data sources:
  1. data/normalized/crime_all.json (geocoded crime events)
  2. data/crime/national/synthetic_events.json (population-weighted synthetic)
  3. data/normalized/traffic_collision_full.json (1.4GB, streamed via ijson)
  4. data/normalized/disaster_quake.json
  5. data/crime/prefectures/**/*.csv (direct CSV processing with chardet)
"""

import json
import os
import sys
import math
import glob
import csv
import time
from collections import defaultdict
from datetime import datetime

# Base path
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
NORM = os.path.join(DATA, "normalized")

# Resolution thresholds
COARSE_DEG = 0.05
THRESHOLDS = [
    (200, 0.0025, "ultra"),
    (50,  0.005,  "high"),
    (10,  0.01,   "mid"),
    (0,   0.05,   "low"),
]

# Japan bounding box (approximate)
LAT_MIN, LAT_MAX = 24.0, 46.0
LON_MIN, LON_MAX = 122.0, 146.0


def cell_key(lat, lon, deg):
    """Return grid cell key as (lat_idx, lon_idx) for given resolution."""
    lat_idx = int(math.floor(lat / deg))
    lon_idx = int(math.floor(lon / deg))
    return (lat_idx, lon_idx)


def coarse_key(lat, lon):
    return cell_key(lat, lon, COARSE_DEG)


class EventAccumulator:
    """Accumulates events into coarse grid cells with metadata."""

    def __init__(self):
        # key -> list of (lat, lon, severity, hour, layer)
        self.coarse_cells = defaultdict(list)
        self.total_events = 0
        self.source_counts = defaultdict(int)

    def add(self, lat, lon, severity=None, hour=None, layer="unknown"):
        if lat is None or lon is None:
            return
        if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
            return
        key = coarse_key(lat, lon)
        self.coarse_cells[key].append((lat, lon, severity, hour, layer))
        self.total_events += 1
        self.source_counts[layer] += 1

    def status(self, msg):
        print(f"  [{self.total_events:,} events] {msg}")


def load_crime_all(acc):
    """Load crime_all.json (geocoded events only)."""
    path = os.path.join(NORM, "crime_all.json")
    if not os.path.exists(path):
        print("  SKIP: crime_all.json not found")
        return
    with open(path) as f:
        data = json.load(f)
    count = 0
    for ev in data:
        geom = ev.get("geometry")
        if not geom:
            continue
        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])
        sev = ev.get("severity")
        hour = None
        occ = ev.get("occurred_at", "")
        if occ and "T" in occ:
            try:
                hour = int(occ.split("T")[1][:2])
            except (ValueError, IndexError):
                pass
        acc.add(lat, lon, severity=sev, hour=hour, layer="crime")
        count += 1
    acc.status(f"crime_all.json: {count:,} events loaded")


def load_synthetic_events(acc):
    """Load synthetic crime events (population-weighted geocoded)."""
    path = os.path.join(DATA, "crime", "national", "synthetic_events.json")
    if not os.path.exists(path):
        print("  SKIP: synthetic_events.json not found")
        return
    with open(path) as f:
        data = json.load(f)
    count = 0
    for ev in data:
        lat = ev.get("lat")
        lon = ev.get("lon")
        if lat is None or lon is None:
            continue
        hour = None
        date_str = ev.get("date", "")
        # synthetic events don't have time, so hour=None
        acc.add(float(lat), float(lon), severity=2, hour=hour, layer="crime_synthetic")
        count += 1
    acc.status(f"synthetic_events.json: {count:,} events loaded")


def load_disaster_quake(acc):
    """Load earthquake events."""
    path = os.path.join(NORM, "disaster_quake.json")
    if not os.path.exists(path):
        print("  SKIP: disaster_quake.json not found")
        return
    with open(path) as f:
        data = json.load(f)
    count = 0
    for ev in data:
        geom = ev.get("geometry")
        if not geom:
            continue
        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])
        sev = ev.get("severity")
        hour = None
        occ = ev.get("occurred_at", "")
        if occ and "T" in occ:
            try:
                hour = int(occ.split("T")[1][:2])
            except (ValueError, IndexError):
                pass
        # Earthquakes get higher base severity
        if sev is None:
            mag_str = (ev.get("raw") or {}).get("mag", "")
            try:
                mag = float(mag_str)
                sev = min(5, max(1, int(mag)))
            except (ValueError, TypeError):
                sev = 3
        acc.add(lat, lon, severity=sev, hour=hour, layer="disaster")
        count += 1
    acc.status(f"disaster_quake.json: {count:,} events loaded")


def load_traffic_collision_full(acc):
    """Stream traffic_collision_full.json via ijson (1.4GB)."""
    path = os.path.join(NORM, "traffic_collision_full.json")
    if not os.path.exists(path):
        print("  SKIP: traffic_collision_full.json not found")
        return
    try:
        import ijson
    except ImportError:
        print("  SKIP: ijson not installed, falling back to traffic_collision.json")
        load_traffic_collision_small(acc)
        return

    print("  Streaming traffic_collision_full.json (1.4GB)...")
    count = 0
    t0 = time.time()
    with open(path, "rb") as f:
        for item in ijson.items(f, "item"):
            geom = item.get("geometry")
            if not geom:
                continue
            coords = geom.get("coordinates", [])
            if len(coords) < 2:
                continue
            try:
                lon = float(coords[0])
                lat = float(coords[1])
            except (ValueError, TypeError):
                continue
            sev = item.get("severity")
            if sev is not None:
                sev = int(sev)
            hour = None
            occ = item.get("occurred_at", "")
            if occ and "T" in occ:
                try:
                    hour = int(occ.split("T")[1][:2])
                except (ValueError, IndexError):
                    pass
            acc.add(lat, lon, severity=sev, hour=hour, layer="traffic")
            count += 1
            if count % 500000 == 0:
                elapsed = time.time() - t0
                acc.status(f"traffic streaming... {count:,} ({elapsed:.0f}s)")

    elapsed = time.time() - t0
    acc.status(f"traffic_collision_full.json: {count:,} events loaded ({elapsed:.0f}s)")


def load_traffic_collision_small(acc):
    """Fallback: load smaller traffic_collision.json."""
    path = os.path.join(NORM, "traffic_collision.json")
    if not os.path.exists(path):
        return
    with open(path) as f:
        data = json.load(f)
    count = 0
    for ev in data:
        geom = ev.get("geometry")
        if not geom:
            continue
        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])
        sev = ev.get("severity")
        hour = None
        occ = ev.get("occurred_at", "")
        if occ and "T" in occ:
            try:
                hour = int(occ.split("T")[1][:2])
            except (ValueError, IndexError):
                pass
        acc.add(lat, lon, severity=sev, hour=hour, layer="traffic")
        count += 1
    acc.status(f"traffic_collision.json: {count:,} events loaded")


def load_crime_csvs(acc):
    """Process prefecture crime CSVs directly.

    CSVs don't have lat/lon, but have city_code. We use city centroids
    for geocoding, similar to synthetic events approach.
    """
    centroid_path = os.path.join(DATA, "crime", "national", "city_centroids.json")
    pref_centroid_path = os.path.join(DATA, "crime", "national", "pref_centroids.json")

    city_centroids = {}
    pref_centroids = {}

    if os.path.exists(centroid_path):
        with open(centroid_path) as f:
            city_centroids = json.load(f)

    if os.path.exists(pref_centroid_path):
        with open(pref_centroid_path) as f:
            pref_data = json.load(f)
        # Convert list format to dict keyed by prefecture name
        if isinstance(pref_data, list):
            for item in pref_data:
                name = item.get("prefecture", "")
                if name:
                    pref_centroids[name] = {"lat": item["lat"], "lon": item["lon"]}
        else:
            pref_centroids = pref_data

    if not city_centroids and not pref_centroids:
        print("  SKIP: No centroid data for geocoding CSVs")
        return

    csv_dir = os.path.join(DATA, "crime", "prefectures")
    if not os.path.exists(csv_dir):
        print("  SKIP: prefectures directory not found")
        return

    csv_files = glob.glob(os.path.join(csv_dir, "**", "*.csv"), recursive=True)
    print(f"  Processing {len(csv_files)} CSV files...")

    try:
        import chardet
    except ImportError:
        print("  SKIP: chardet not installed")
        return

    count = 0
    skipped = 0
    for i, csv_path in enumerate(csv_files):
        try:
            with open(csv_path, "rb") as f:
                raw = f.read()
            det = chardet.detect(raw[:10000])
            encoding = det.get("encoding", "utf-8") or "utf-8"
            # Common fallbacks for Japanese
            if encoding.lower() in ("ascii", "windows-1252"):
                encoding = "cp932"
            text = raw.decode(encoding, errors="replace")
            lines = text.strip().split("\n")
            if len(lines) < 2:
                continue

            reader = csv.reader(lines)
            header = next(reader)

            # Find relevant column indices
            city_code_idx = None
            pref_idx = None
            city_idx = None
            date_idx = None
            hour_idx = None

            for idx, col in enumerate(header):
                col_clean = col.strip()
                if "市区町村コード" in col_clean:
                    city_code_idx = idx
                elif "都道府県" in col_clean and "市区町村" not in col_clean:
                    pref_idx = idx
                elif "市区町村" in col_clean and "コード" not in col_clean:
                    city_idx = idx
                elif "発生年月日" in col_clean:
                    date_idx = idx
                elif "発生時" in col_clean:
                    hour_idx = idx

            for row in reader:
                if len(row) <= max(filter(None, [city_code_idx, pref_idx, 0])):
                    continue

                lat, lon = None, None

                # Try pref+city name lookup (e.g. "長野県_中野市")
                pref_name = ""
                city_name = ""
                if pref_idx is not None and pref_idx < len(row):
                    pref_name = row[pref_idx].strip()
                if city_idx is not None and city_idx < len(row):
                    city_name = row[city_idx].strip()

                if pref_name and city_name:
                    lookup_key = f"{pref_name}_{city_name}"
                    if lookup_key in city_centroids:
                        c = city_centroids[lookup_key]
                        if isinstance(c, dict):
                            lat, lon = c.get("lat"), c.get("lon")

                # Fall back to prefecture centroid
                if lat is None and pref_name and pref_name in pref_centroids:
                    c = pref_centroids[pref_name]
                    if isinstance(c, dict):
                        lat, lon = c.get("lat"), c.get("lon")
                    elif isinstance(c, (list, tuple)) and len(c) >= 2:
                        lat, lon = c[0], c[1]

                if lat is None or lon is None:
                    skipped += 1
                    continue

                hour = None
                if hour_idx is not None and hour_idx < len(row):
                    try:
                        hour = int(row[hour_idx].strip())
                    except (ValueError, IndexError):
                        pass

                acc.add(float(lat), float(lon), severity=2, hour=hour, layer="crime_csv")
                count += 1

        except Exception as e:
            # Skip problematic files silently
            pass

        if (i + 1) % 100 == 0:
            acc.status(f"CSV progress: {i+1}/{len(csv_files)} files")

    acc.status(f"Crime CSVs: {count:,} events loaded ({skipped:,} skipped, no geocode)")


def determine_resolution(event_count):
    """Determine target resolution based on event count."""
    for threshold, deg, name in THRESHOLDS:
        if event_count >= threshold:
            return deg, name
    return COARSE_DEG, "low"


def build_adaptive_cells(acc):
    """Build adaptive mesh from coarse grid."""
    print("\n--- Building adaptive mesh ---")
    resolution_counts = defaultdict(int)
    # adaptive_cell: key=(lat_idx, lon_idx, deg) -> {events, metadata}
    adaptive_cells = {}

    for coarse_k, events in acc.coarse_cells.items():
        count = len(events)
        target_deg, res_name = determine_resolution(count)
        resolution_counts[res_name] += 1  # will be updated below

        if target_deg == COARSE_DEG:
            # Keep as coarse cell
            adaptive_cells[(coarse_k[0], coarse_k[1], COARSE_DEG)] = events
        else:
            # Subdivide: redistribute events into finer cells
            sub_cells = defaultdict(list)
            for (lat, lon, sev, hour, layer) in events:
                sub_k = cell_key(lat, lon, target_deg)
                sub_cells[(sub_k[0], sub_k[1], target_deg)].append(
                    (lat, lon, sev, hour, layer)
                )
            for sub_k, sub_evts in sub_cells.items():
                adaptive_cells[sub_k] = sub_evts

    # Recount by resolution
    resolution_counts = defaultdict(int)
    for (_, _, deg), _ in adaptive_cells.items():
        for _, d, name in THRESHOLDS:
            if abs(deg - d) < 1e-6:
                resolution_counts[name] += 1
                break

    print(f"  Total adaptive cells: {len(adaptive_cells):,}")
    for name in ["ultra", "high", "mid", "low"]:
        print(f"    {name}: {resolution_counts[name]:,} cells")

    return adaptive_cells, resolution_counts


def compute_risk_scores(adaptive_cells):
    """Calculate risk score per adaptive cell."""
    print("\n--- Computing risk scores ---")
    results = []

    for (lat_idx, lon_idx, grid_deg), events in adaptive_cells.items():
        count = len(events)
        if count == 0:
            continue

        # Cell center coordinates
        center_lat = (lat_idx + 0.5) * grid_deg
        center_lon = (lon_idx + 0.5) * grid_deg

        # area_factor: ratio of ultra cell area to this cell area
        area_factor = (0.0025 / grid_deg) ** 2

        # density_score
        density_score = min(1.0, count * area_factor / 100.0)

        # severity_score
        severities = [s for (_, _, s, _, _) in events if s is not None]
        avg_severity = sum(severities) / len(severities) if severities else 2.0
        severity_score = avg_severity / 5.0

        # night_factor
        hours = [h for (_, _, _, h, _) in events if h is not None]
        if hours:
            night_count = sum(1 for h in hours if h >= 22 or h < 6)
            night_ratio = night_count / len(hours)
        else:
            night_ratio = 0.0
        night_factor = 1.0 + 0.2 * night_ratio

        # risk_score
        risk_score = min(1.0, (density_score * 0.6 + severity_score * 0.4) * night_factor)

        # Determine resolution name
        res_name = "low"
        for _, d, name in THRESHOLDS:
            if abs(grid_deg - d) < 1e-6:
                res_name = name
                break

        # Layer breakdown
        layer_counts = defaultdict(int)
        for (_, _, _, _, layer) in events:
            layer_counts[layer] += 1

        results.append({
            "cell_id": f"{lat_idx}_{lon_idx}_{grid_deg}",
            "center": [round(center_lon, 6), round(center_lat, 6)],
            "grid_deg": grid_deg,
            "resolution": res_name,
            "bounds": {
                "south": round(lat_idx * grid_deg, 6),
                "north": round((lat_idx + 1) * grid_deg, 6),
                "west": round(lon_idx * grid_deg, 6),
                "east": round((lon_idx + 1) * grid_deg, 6),
            },
            "event_count": count,
            "layers": dict(layer_counts),
            "density_score": round(density_score, 4),
            "severity_score": round(severity_score, 4),
            "night_ratio": round(night_ratio, 4),
            "night_factor": round(night_factor, 4),
            "risk_score": round(risk_score, 4),
        })

    # Sort by risk_score descending
    results.sort(key=lambda x: x["risk_score"], reverse=True)
    return results


def save_outputs(results, resolution_counts):
    """Save to all output paths."""
    output = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "description": "Adaptive quadtree mesh risk scoring",
            "resolution_policy": {
                "ultra_0.0025deg": "event_count >= 200",
                "high_0.005deg": "event_count >= 50",
                "mid_0.01deg": "event_count >= 10",
                "low_0.05deg": "event_count < 10",
            },
            "total_cells": len(results),
            "cells_by_resolution": dict(resolution_counts),
        },
        "cells": results,
    }

    paths = [
        os.path.join(NORM, "adaptive_mesh.json"),
        os.path.join(BASE, "dashboard", "data", "grid_risk.json"),
        os.path.join(BASE, "docs", "data", "grid_risk.json"),
    ]

    for path in paths:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, separators=(",", ":"))
        size_mb = os.path.getsize(path) / 1024 / 1024
        print(f"  Saved: {path} ({size_mb:.1f} MB)")


def print_summary(results, resolution_counts, acc):
    """Print final summary."""
    print("\n" + "=" * 60)
    print("ADAPTIVE MESH RISK SCORING - SUMMARY")
    print("=" * 60)

    print(f"\nTotal events processed: {acc.total_events:,}")
    print("Events by source:")
    for layer, count in sorted(acc.source_counts.items(), key=lambda x: -x[1]):
        print(f"  {layer}: {count:,}")

    print(f"\nTotal adaptive cells: {len(results):,}")
    print("Cells by resolution:")
    for name in ["ultra", "high", "mid", "low"]:
        print(f"  {name:6s}: {resolution_counts.get(name, 0):,} cells")

    print("\nTop 5 hotspots:")
    for i, cell in enumerate(results[:5]):
        print(
            f"  {i+1}. [{cell['center'][1]:.4f}, {cell['center'][0]:.4f}] "
            f"risk={cell['risk_score']:.4f} "
            f"events={cell['event_count']:,} "
            f"res={cell['resolution']} "
            f"layers={cell['layers']}"
        )
    print("=" * 60)


def main():
    print("=" * 60)
    print("Building Adaptive Mesh Risk Scoring")
    print("=" * 60)

    acc = EventAccumulator()

    # Step 1: Load all event sources
    print("\n--- Loading events ---")

    load_crime_all(acc)
    load_synthetic_events(acc)
    load_disaster_quake(acc)
    load_crime_csvs(acc)
    load_traffic_collision_full(acc)

    print(f"\n  Total events accumulated: {acc.total_events:,}")
    print(f"  Coarse cells occupied: {len(acc.coarse_cells):,}")

    # Step 2: Build adaptive mesh
    adaptive_cells, resolution_counts = build_adaptive_cells(acc)

    # Step 3: Compute risk scores
    results = compute_risk_scores(adaptive_cells)

    # Step 4: Save outputs
    print("\n--- Saving outputs ---")
    save_outputs(results, resolution_counts)

    # Step 5: Summary
    print_summary(results, resolution_counts, acc)


if __name__ == "__main__":
    main()
