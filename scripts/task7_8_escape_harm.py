#!/usr/bin/env python3
"""
Task 7: Safe Haven Integration + P(escape) Engine
Task 8: Grid Expected Harm Integration
"""

import json
import math
import time
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# ─── Task 7 Step 1: Merge all safe havens ─────────────────────────────────

def load_havens():
    """Load and merge all safe haven files into ALL_HAVENS list."""
    havens = []

    # Simple list files
    list_files = [
        "data/safe_haven/police/police_ksj.json",
        "data/safe_haven/police/police_osm.json",
        "data/safe_haven/fire/fire_ksj.json",
        "data/safe_haven/hospital/hospitals_all.json",
        "data/safe_haven/aed/aed_osm.json",
    ]

    for fp in list_files:
        path = BASE / fp
        print(f"  Loading {fp}...")
        with open(path) as f:
            data = json.load(f)
        count = 0
        for item in data:
            lat, lon = item.get("lat"), item.get("lon")
            if lat is not None and lon is not None and isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and not (math.isnan(lat) or math.isnan(lon)):
                havens.append({
                    "lat": lat,
                    "lon": lon,
                    "name": item.get("name", ""),
                    "type": item.get("type", "unknown"),
                    "is_24h": item.get("is_24h", False),
                    "safety_score": item.get("safety_score", 0.5),
                    "source": item.get("source", fp),
                })
                count += 1
        print(f"    -> {count} valid items")

    # Convenience/station file (nested under 'data' key)
    fp = "data/safe_haven/convenience/havens_osm.json"
    print(f"  Loading {fp}...")
    with open(BASE / fp) as f:
        raw = json.load(f)
    count = 0
    for item in raw["data"]:
        lat, lon = item.get("lat"), item.get("lon")
        if lat is not None and lon is not None and isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and not (math.isnan(lat) or math.isnan(lon)):
            havens.append({
                "lat": lat,
                "lon": lon,
                "name": item.get("name", ""),
                "type": item.get("type", "unknown"),
                "is_24h": item.get("is_24h", False),
                "safety_score": item.get("safety_score", 0.5),
                "source": "osm_convenience",
            })
            count += 1
    print(f"    -> {count} valid items")

    print(f"\n  TOTAL ALL_HAVENS: {len(havens)}")
    return havens


# ─── Task 7 Step 2: Load arrival times ────────────────────────────────────

def load_arrival_times():
    """Load prefecture ambulance arrival times."""
    with open(BASE / "data/safe_haven/hospital/arrival_times.json") as f:
        raw = json.load(f)
    # Build prefecture -> minutes mapping
    mapping = {}
    for entry in raw["data"]:
        mapping[entry["prefecture"]] = entry["arrival_time_minutes"]
    national_avg = sum(mapping.values()) / len(mapping)
    print(f"  Loaded arrival times for {len(mapping)} prefectures (avg={national_avg:.1f} min)")
    return mapping, national_avg


# ─── Spatial Index ─────────────────────────────────────────────────────────

def build_spatial_index(havens, bucket_size=0.1):
    """Bucket havens into grid cells for fast spatial lookup."""
    index = defaultdict(list)
    for h in havens:
        bx = int(h["lon"] / bucket_size)
        by = int(h["lat"] / bucket_size)
        index[(bx, by)].append(h)
    print(f"  Spatial index: {len(index)} buckets (bucket_size={bucket_size}°)")
    return index, bucket_size


def query_nearby(index, bucket_size, lat, lon, radius_km, night_mode=False):
    """Find havens within radius_km using spatial index."""
    # Approximate: 1° lat ~ 111km, 1° lon ~ 111*cos(lat) km
    lat_range = radius_km / 111.0
    lon_range = radius_km / (111.0 * math.cos(math.radians(lat)))

    bx_center = int(lon / bucket_size)
    by_center = int(lat / bucket_size)

    # How many buckets to search in each direction
    bx_range = int(math.ceil(lon_range / bucket_size)) + 1
    by_range = int(math.ceil(lat_range / bucket_size)) + 1

    results = []
    for dx in range(-bx_range, bx_range + 1):
        for dy in range(-by_range, by_range + 1):
            bucket = index.get((bx_center + dx, by_center + dy))
            if not bucket:
                continue
            for h in bucket:
                if night_mode and not h["is_24h"]:
                    continue
                dist = haversine(lat, lon, h["lat"], h["lon"])
                if dist <= radius_km:
                    results.append((dist, h))
    return results


def haversine(lat1, lon1, lat2, lon2):
    """Distance in km between two points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ─── P(escape) Calculator ─────────────────────────────────────────────────

# Haven type weights
HAVEN_WEIGHTS = {
    "koban": 1.0,
    "police_station": 1.0,
    "police_box": 1.0,
    "fire_station": 0.90,
    "hospital": 0.80,
    "emergency_hospital": 0.85,
    "general_hospital": 0.80,
    "clinic": 0.75,
    "convenience_store": 0.85,
    "station": 0.70,
    "aed": 0.45,
}


def get_haven_weight(haven_type):
    """Get weight for a haven type."""
    t = haven_type.lower()
    if t in HAVEN_WEIGHTS:
        return HAVEN_WEIGHTS[t]
    # Fuzzy matches
    if "police" in t or "koban" in t:
        return 1.0
    if "fire" in t:
        return 0.90
    if "hospital" in t or "clinic" in t:
        return 0.80
    if "convenience" in t:
        return 0.85
    if "station" in t and "fire" not in t and "police" not in t:
        return 0.70
    if "aed" in t:
        return 0.45
    return 0.50


def distance_score(nearest_km):
    """Interpolate distance score."""
    if nearest_km is None:
        return 0.0
    # Breakpoints: (km, score)
    bp = [(0.1, 1.0), (0.3, 0.85), (0.5, 0.70), (1.0, 0.45), (2.0, 0.20)]
    if nearest_km <= bp[0][0]:
        return bp[0][1]
    if nearest_km >= bp[-1][0]:
        return bp[-1][1] * (bp[-1][0] / nearest_km) if nearest_km > 0 else 0.0
    for i in range(len(bp) - 1):
        d0, s0 = bp[i]
        d1, s1 = bp[i + 1]
        if d0 <= nearest_km <= d1:
            t = (nearest_km - d0) / (d1 - d0)
            return s0 + t * (s1 - s0)
    return 0.0


def arrival_score(arrival_min):
    """Convert arrival time to score. 4min=1.0, 15min=0.0, linear."""
    if arrival_min is None:
        return 0.5
    if arrival_min <= 4.0:
        return 1.0
    if arrival_min >= 15.0:
        return 0.0
    return 1.0 - (arrival_min - 4.0) / (15.0 - 4.0)


def night_penalty(hour):
    """Night penalty factor."""
    if 22 <= hour or hour < 6:
        return 0.65
    if 20 <= hour < 22:
        return 0.85
    return 1.0


def calc_p_escape(lat, lon, time_hour, spatial_idx, bucket_size, arrival_times, national_avg_arrival):
    """
    Calculate P(escape) for a given location and time.
    Returns dict with p_escape and component scores.
    """
    is_night = (22 <= time_hour or time_hour < 6)

    # Find havens within 2km
    nearby = query_nearby(spatial_idx, bucket_size, lat, lon, 2.0, night_mode=is_night)

    if not nearby:
        np = night_penalty(time_hour)
        return {
            "p_escape": 0.0,
            "distance_score": 0.0,
            "density_score": 0.0,
            "proximity_score": 0.0,
            "arrival_score": arrival_score(national_avg_arrival),
            "night_penalty": np,
            "haven_count_500m": 0,
            "haven_count_2km": 0,
            "nearest_haven_dist": None,
            "nearest_haven_type": None,
        }

    # Sort by distance
    nearby.sort(key=lambda x: x[0])
    nearest_dist = nearby[0][0]
    nearest_type = nearby[0][1]["type"]

    # Distance score (nearest haven)
    d_score = distance_score(nearest_dist)

    # Density score (havens within 500m)
    havens_500m = [h for d, h in nearby if d <= 0.5]
    den_score = min(1.0, len(havens_500m) / 5.0)

    # Proximity score (weighted sum of nearby havens, capped)
    prox_sum = 0.0
    for dist, h in nearby:
        if dist > 1.0:
            break
        w = get_haven_weight(h["type"])
        # Distance decay: closer = higher contribution
        decay = max(0, 1.0 - dist / 1.0)
        prox_sum += w * decay
    prox_score = min(1.0, prox_sum / 3.0)  # Normalize: 3 well-weighted nearby havens = 1.0

    # Arrival score - use nearest prefecture approximation
    # We'll use national average as default; grid integration uses cell-specific
    a_score = arrival_score(national_avg_arrival)

    # Night penalty
    np = night_penalty(time_hour)

    p_esc = (d_score * 0.35 + den_score * 0.25 + prox_score * 0.20 + a_score * 0.20) * np

    return {
        "p_escape": round(p_esc, 4),
        "distance_score": round(d_score, 4),
        "density_score": round(den_score, 4),
        "proximity_score": round(prox_score, 4),
        "arrival_score": round(a_score, 4),
        "night_penalty": np,
        "haven_count_500m": len(havens_500m),
        "haven_count_2km": len(nearby),
        "nearest_haven_dist": round(nearest_dist, 4),
        "nearest_haven_type": nearest_type,
    }


# ─── Prefecture lookup by coordinate (rough) ──────────────────────────────

# We'll map grid cells to nearest prefecture by ambulance arrival time
# For now, use a simple lat/lon bounding approach based on major regions

def get_prefecture_arrival(lat, lon, arrival_times, national_avg):
    """Rough prefecture lookup for arrival time. Returns minutes."""
    # Major cities / prefectures by rough bounding box
    # This is approximate - for production, use proper reverse geocoding
    prefectures_coords = [
        ("北海道", 41.5, 45.5, 139.5, 145.5),
        ("青森県", 40.2, 41.5, 139.5, 141.5),
        ("岩手県", 38.7, 40.5, 140.5, 142.0),
        ("宮城県", 37.8, 39.0, 140.3, 141.7),
        ("秋田県", 39.0, 40.5, 139.5, 140.8),
        ("山形県", 37.7, 39.2, 139.5, 140.5),
        ("福島県", 36.8, 38.0, 139.2, 141.0),
        ("茨城県", 35.7, 36.9, 139.7, 140.9),
        ("栃木県", 36.2, 37.2, 139.3, 140.3),
        ("群馬県", 36.0, 37.0, 138.5, 139.7),
        ("埼玉県", 35.7, 36.3, 138.9, 139.9),
        ("千葉県", 34.9, 36.0, 139.7, 140.9),
        ("東京都", 35.5, 35.9, 138.9, 139.9),
        ("神奈川県", 35.1, 35.7, 139.0, 139.8),
        ("新潟県", 36.7, 38.5, 137.8, 140.0),
        ("富山県", 36.3, 37.0, 136.7, 137.8),
        ("石川県", 36.0, 37.8, 136.2, 137.3),
        ("福井県", 35.5, 36.3, 135.5, 136.8),
        ("山梨県", 35.2, 35.9, 138.2, 139.1),
        ("長野県", 35.2, 37.0, 137.5, 138.7),
        ("岐阜県", 35.1, 36.5, 136.3, 137.7),
        ("静岡県", 34.6, 35.5, 137.5, 139.2),
        ("愛知県", 34.6, 35.4, 136.7, 137.8),
        ("三重県", 33.7, 35.1, 135.8, 137.0),
        ("滋賀県", 34.8, 35.6, 135.8, 136.5),
        ("京都府", 34.8, 35.8, 135.0, 136.1),
        ("大阪府", 34.3, 34.9, 135.1, 135.8),
        ("兵庫県", 34.2, 35.7, 134.3, 135.5),
        ("奈良県", 34.0, 34.8, 135.5, 136.2),
        ("和歌山県", 33.4, 34.4, 135.0, 136.0),
        ("鳥取県", 35.0, 35.6, 133.2, 134.5),
        ("島根県", 34.3, 35.6, 131.7, 133.4),
        ("岡山県", 34.4, 35.3, 133.4, 134.4),
        ("広島県", 34.0, 35.0, 132.0, 133.5),
        ("山口県", 33.7, 34.8, 130.8, 132.2),
        ("徳島県", 33.5, 34.3, 133.5, 134.8),
        ("香川県", 34.0, 34.5, 133.5, 134.5),
        ("愛媛県", 33.0, 34.2, 132.0, 133.7),
        ("高知県", 32.7, 33.9, 132.5, 134.3),
        ("福岡県", 33.0, 34.0, 130.0, 131.2),
        ("佐賀県", 33.0, 33.5, 129.7, 130.5),
        ("長崎県", 32.5, 34.5, 128.5, 130.2),
        ("熊本県", 32.0, 33.3, 130.0, 131.3),
        ("大分県", 32.8, 33.7, 131.0, 132.1),
        ("宮崎県", 31.3, 32.8, 130.7, 131.9),
        ("鹿児島県", 27.0, 32.0, 128.5, 131.5),
        ("沖縄県", 24.0, 27.5, 122.5, 131.5),
    ]

    for pref, lat_min, lat_max, lon_min, lon_max in prefectures_coords:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            if pref in arrival_times:
                return arrival_times[pref]

    return national_avg


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Task 7: Safe Haven Integration + P(escape) Engine")
    print("=" * 60)

    # Step 1: Load and merge havens
    print("\n[1] Loading safe haven data...")
    havens = load_havens()

    # Save ALL_HAVENS.json
    out_path = BASE / "data/safe_haven/ALL_HAVENS.json"
    with open(out_path, "w") as f:
        json.dump(havens, f, ensure_ascii=False)
    print(f"\n  Saved ALL_HAVENS.json ({len(havens)} items, {out_path.stat().st_size / 1024 / 1024:.1f} MB)")

    # Step 2: Load arrival times
    print("\n[2] Loading arrival times...")
    arrival_times, national_avg = load_arrival_times()

    # Step 3: Build spatial index
    print("\n[3] Building spatial index...")
    spatial_idx, bucket_sz = build_spatial_index(havens)

    # Step 4: Test with 5 locations
    print("\n[4] Testing P(escape) with 5 locations...")
    test_cases = [
        ("新宿駅 (midnight)", 35.6895, 139.6917, 0),
        ("新宿駅 (noon)", 35.6895, 139.6917, 12),
        ("神戸市郊外 (22:00)", 34.6913, 135.1956, 22),
        ("札幌市 (2:00)", 43.0618, 141.3545, 2),
        ("富士山麓 (23:00)", 35.3, 138.5, 23),
    ]

    for name, lat, lon, hour in test_cases:
        result = calc_p_escape(lat, lon, hour, spatial_idx, bucket_sz, arrival_times, national_avg)
        print(f"\n  {name} (lat={lat}, lon={lon}, hour={hour:02d}:00)")
        print(f"    P(escape)       = {result['p_escape']:.4f}")
        print(f"    distance_score  = {result['distance_score']:.4f}")
        print(f"    density_score   = {result['density_score']:.4f}")
        print(f"    proximity_score = {result['proximity_score']:.4f}")
        print(f"    arrival_score   = {result['arrival_score']:.4f}")
        print(f"    night_penalty   = {result['night_penalty']:.2f}")
        print(f"    havens <=500m   = {result['haven_count_500m']}")
        print(f"    havens <=2km    = {result['haven_count_2km']}")
        print(f"    nearest         = {result['nearest_haven_dist']}km ({result['nearest_haven_type']})")

    # ═══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("Task 8: Grid Expected Harm Integration")
    print("=" * 60)

    # Step 1: Load grid
    print("\n[1] Loading grid_risk.json...")
    with open(BASE / "dashboard/data/grid_risk.json") as f:
        grid = json.load(f)
    print(f"  {len(grid)} cells loaded")

    # Step 2-4: Calculate P(escape) and Expected Harm for each cell
    print("\n[2-4] Calculating P(escape) and Expected Harm for all cells...")
    current_hour = 14  # Use 14:00 (2 PM) as default "current hour"
    t0 = time.time()

    for i, cell in enumerate(grid):
        lat = cell["center"][1]
        lon = cell["center"][0]

        # Get prefecture-specific arrival time
        pref_arrival = get_prefecture_arrival(lat, lon, arrival_times, national_avg)

        result = calc_p_escape(lat, lon, current_hour, spatial_idx, bucket_sz, arrival_times, pref_arrival)

        # Override arrival_score with prefecture-specific
        a_score = arrival_score(pref_arrival)
        # Recalculate p_escape with correct arrival score
        np_val = night_penalty(current_hour)
        p_esc = (result["distance_score"] * 0.35 +
                 result["density_score"] * 0.25 +
                 result["proximity_score"] * 0.20 +
                 a_score * 0.20) * np_val

        # Expected Harm = risk_score * (avg_severity/5) * (1 - P(escape))
        risk = cell.get("risk_score", 0)
        severity = cell.get("severity_score", 0.5)
        expected_harm = risk * (severity / 5.0) * (1.0 - p_esc)

        cell["p_escape"] = round(p_esc, 4)
        cell["expected_harm"] = round(expected_harm, 6)
        cell["haven_count_500m"] = result["haven_count_500m"]
        cell["haven_count_2km"] = result["haven_count_2km"]
        cell["nearest_haven_dist"] = result["nearest_haven_dist"]
        cell["nearest_haven_type"] = result["nearest_haven_type"]

        if (i + 1) % 1000 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (len(grid) - i - 1) / rate
            print(f"  [{i+1:>6}/{len(grid)}] {rate:.0f} cells/sec, ETA {eta:.0f}s")

    elapsed = time.time() - t0
    print(f"\n  Done in {elapsed:.1f}s ({len(grid)/elapsed:.0f} cells/sec)")

    # Step 5: Save updated grid_risk.json
    print("\n[5] Saving updated grid_risk.json...")
    for dest in [BASE / "dashboard/data/grid_risk.json", BASE / "docs/data/grid_risk.json"]:
        with open(dest, "w") as f:
            json.dump(grid, f, ensure_ascii=False)
        print(f"  -> {dest} ({dest.stat().st_size / 1024 / 1024:.1f} MB)")

    # Step 6: Top 20 Expected Harm hotspots
    print("\n[6] Saving hotspots_expected_harm.json (top 20)...")
    sorted_harm = sorted(grid, key=lambda c: c.get("expected_harm", 0), reverse=True)
    top20_harm = sorted_harm[:20]
    hotspots = []
    for c in top20_harm:
        hotspots.append({
            "cell_id": c["cell_id"],
            "center": c["center"],
            "risk_score": c["risk_score"],
            "severity_score": c["severity_score"],
            "p_escape": c["p_escape"],
            "expected_harm": c["expected_harm"],
            "haven_count_500m": c["haven_count_500m"],
            "haven_count_2km": c["haven_count_2km"],
            "nearest_haven_dist": c["nearest_haven_dist"],
            "nearest_haven_type": c["nearest_haven_type"],
        })
    with open(BASE / "dashboard/data/hotspots_expected_harm.json", "w") as f:
        json.dump(hotspots, f, ensure_ascii=False, indent=2)
    print(f"  Saved {len(hotspots)} hotspots")

    # Step 7: Top 20 lowest P(escape) cells with risk >= 0.2
    print("\n[7] Saving escape_deficit.json (top 20 lowest P(escape), risk >= 0.2)...")
    risky = [c for c in grid if c.get("risk_score", 0) >= 0.2]
    sorted_escape = sorted(risky, key=lambda c: c.get("p_escape", 1.0))
    top20_escape = sorted_escape[:20]
    deficit = []
    for c in top20_escape:
        deficit.append({
            "cell_id": c["cell_id"],
            "center": c["center"],
            "risk_score": c["risk_score"],
            "severity_score": c["severity_score"],
            "p_escape": c["p_escape"],
            "expected_harm": c["expected_harm"],
            "haven_count_500m": c["haven_count_500m"],
            "haven_count_2km": c["haven_count_2km"],
            "nearest_haven_dist": c["nearest_haven_dist"],
            "nearest_haven_type": c["nearest_haven_type"],
        })
    with open(BASE / "dashboard/data/escape_deficit.json", "w") as f:
        json.dump(deficit, f, ensure_ascii=False, indent=2)
    print(f"  Saved {len(deficit)} escape deficit cells")

    # ─── Summary ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("TOP 5 EXPECTED HARM HOTSPOTS")
    print("=" * 60)
    for i, h in enumerate(hotspots[:5]):
        print(f"  #{i+1} {h['cell_id']}")
        print(f"     center=({h['center'][1]:.4f}, {h['center'][0]:.4f})")
        print(f"     risk={h['risk_score']:.3f}  severity={h['severity_score']:.3f}  P(escape)={h['p_escape']:.4f}")
        print(f"     Expected Harm = {h['expected_harm']:.6f}")
        print(f"     havens: {h['haven_count_500m']} within 500m, {h['haven_count_2km']} within 2km")

    print("\n" + "=" * 60)
    print("TOP 5 ESCAPE DEFICIT AREAS (lowest P(escape), risk >= 0.2)")
    print("=" * 60)
    for i, d in enumerate(deficit[:5]):
        print(f"  #{i+1} {d['cell_id']}")
        print(f"     center=({d['center'][1]:.4f}, {d['center'][0]:.4f})")
        print(f"     risk={d['risk_score']:.3f}  P(escape)={d['p_escape']:.4f}")
        print(f"     Expected Harm = {d['expected_harm']:.6f}")
        print(f"     nearest haven: {d['nearest_haven_dist']}km ({d['nearest_haven_type']})")

    print("\n[DONE]")


if __name__ == "__main__":
    main()
