"""
Step 3: Full risk score recalculation using complete geocoded crime data
- Merges all_crime_geocoded_full.json into normalized crime_all.json
- Calculates risk scores for all events
- Saves all_events_scored_v2.json and hotspots_v2.json
"""
import json, math, uuid
from pathlib import Path
from datetime import datetime
from collections import defaultdict

BASE = Path("/Users/reikumaki/Library/CloudStorage/GoogleDrive-teddykmk@gmail.com/マイドライブ/piracy_detector/claude_code/risk_space")
NORMALIZED = BASE / "data/normalized"
GEOCODED = BASE / "data/geocoded"

# ── Step 3-1: Merge geocoded coords into normalized crime events ──────────────
print("=== Step 3-1: 犯罪データ座標マージ ===")

with open(GEOCODED / "all_crime_geocoded_full.json", encoding="utf-8") as f:
    geocoded_raw = json.load(f)

with open(NORMALIZED / "crime_all.json", encoding="utf-8") as f:
    crime_norm = json.load(f)

print(f"  geocoded_raw: {len(geocoded_raw)}件")
print(f"  crime_norm:   {len(crime_norm)}件")

assert len(geocoded_raw) == len(crime_norm), "件数不一致！インデックスマージ不可"

updated = 0
for i, (raw, norm) in enumerate(zip(geocoded_raw, crime_norm)):
    if raw.get("geocoded") and raw.get("lat") and raw.get("lon"):
        lat, lon = raw["lat"], raw["lon"]
        if 24 < lat < 46 and 122 < lon < 154:
            norm["geometry"] = {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]}
            updated += 1

print(f"  座標マージ完了: {updated}件 / {len(crime_norm)}件")

# Save updated crime_all.json
with open(NORMALIZED / "crime_all.json", "w", encoding="utf-8") as f:
    json.dump(crime_norm, f, ensure_ascii=False)
print(f"  crime_all.json 更新完了")

# ── Step 3-2: Load all events ──────────────────────────────────────────────────
print("\n=== Step 3-2: 全イベント読み込み ===")

all_events = []
layer_counts = defaultdict(int)

for fname in ["crime_all.json", "traffic_collision.json", "disaster_quake.json"]:
    fpath = NORMALIZED / fname
    if not fpath.exists():
        print(f"  スキップ: {fname} (ファイルなし)")
        continue
    with open(fpath, encoding="utf-8") as f:
        events = json.load(f)
    with_coords = [e for e in events if e.get("geometry") and e["geometry"].get("coordinates")]
    layer = with_coords[0]["layer"] if with_coords else fname
    print(f"  {fname}: {len(events)}件 (座標付き: {len(with_coords)}件)")
    all_events.extend(events)
    for e in events:
        layer_counts[e.get("layer", "unknown")] += 1

print(f"\n  合計: {len(all_events)}件")
print(f"  レイヤー別: {dict(layer_counts)}")

coord_events = [e for e in all_events if e.get("geometry") and e["geometry"].get("coordinates")]
print(f"  座標付き: {len(coord_events)}件")

# ── Step 3-3: Risk score calculation ──────────────────────────────────────────
print("\n=== Step 3-3: リスクスコア計算 ===")

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

# Build spatial index: 0.1° grid buckets
spatial_index = defaultdict(list)
for e in coord_events:
    lon, lat = e["geometry"]["coordinates"]
    gx = round(lon / 0.1) * 0.1
    gy = round(lat / 0.1) * 0.1
    spatial_index[(round(gy, 1), round(gx, 1))].append(e)

RADIUS_KM = 1.0

def get_neighbors(lat, lon, events_list):
    neighbors = []
    gx = round(lon / 0.1) * 0.1
    gy = round(lat / 0.1) * 0.1
    # Check 3x3 grid around target
    for di in [-0.1, 0.0, 0.1]:
        for dj in [-0.1, 0.0, 0.1]:
            key = (round(gy + di, 1), round(gx + dj, 1))
            neighbors.extend(spatial_index.get(key, []))
    return neighbors

scored = 0
SAMPLE = 50000  # Score up to 50k events for performance

for e in coord_events[:SAMPLE]:
    lon, lat = e["geometry"]["coordinates"]
    neighbors = get_neighbors(lat, lon, coord_events)
    score = 0.0
    for nb in neighbors:
        nb_lon, nb_lat = nb["geometry"]["coordinates"]
        dist = haversine(lat, lon, nb_lat, nb_lon)
        if dist <= RADIUS_KM:
            sev = (nb.get("severity") or 2) / 5.0
            # Gaussian kernel weight
            weight = math.exp(-dist**2 / (2 * 0.5**2))
            score += sev * weight
    e["risk_score"] = round(min(1.0, score / 10.0), 4)
    scored += 1
    if scored % 5000 == 0:
        print(f"  進捗: {scored}/{min(SAMPLE, len(coord_events))}件")

print(f"  リスクスコア計算完了: {scored}件")

# ── Step 3-4: Save scored events ──────────────────────────────────────────────
print("\n=== Step 3-4: スコア付きイベント保存 ===")

# Filter to only events with coords and risk scores
scored_events = [e for e in coord_events[:SAMPLE] if e.get("risk_score") is not None]

with open(NORMALIZED / "all_events_scored_v2.json", "w", encoding="utf-8") as f:
    json.dump(scored_events, f, ensure_ascii=False)
print(f"  all_events_scored_v2.json: {len(scored_events)}件")

# ── Step 3-5: Hotspot extraction ───────────────────────────────────────────────
print("\n=== Step 3-5: ホットスポット抽出 ===")

# Group by 0.05° grid
hotspot_grid = defaultdict(lambda: {
    "scores": [], "count": 0, "lat": 0, "lon": 0,
    "layers": defaultdict(int), "subtypes": defaultdict(int)
})

for e in scored_events:
    lon, lat = e["geometry"]["coordinates"]
    gx = round(round(lon / 0.05) * 0.05, 3)
    gy = round(round(lat / 0.05) * 0.05, 3)
    key = f"{gy},{gx}"
    cell = hotspot_grid[key]
    cell["scores"].append(e["risk_score"])
    cell["count"] += 1
    cell["lat"] = gy
    cell["lon"] = gx
    cell["layers"][e.get("layer", "unknown")] += 1
    cell["subtypes"][e.get("subtype", "")] += 1

hotspots = []
for key, cell in hotspot_grid.items():
    if cell["count"] < 3:
        continue
    avg_score = sum(cell["scores"]) / len(cell["scores"])
    max_score = max(cell["scores"])
    dominant_subtype = max(cell["subtypes"].items(), key=lambda x: x[1])[0] if cell["subtypes"] else ""
    hotspots.append({
        "lat": cell["lat"],
        "lon": cell["lon"],
        "risk_score": round(max_score, 4),
        "avg_risk_score": round(avg_score, 4),
        "event_count": cell["count"],
        "dominant_subtype": dominant_subtype,
        "layers": dict(cell["layers"]),
    })

hotspots.sort(key=lambda x: -x["risk_score"])
top_hotspots = hotspots[:20]

with open(NORMALIZED / "hotspots_v2.json", "w", encoding="utf-8") as f:
    json.dump(top_hotspots, f, ensure_ascii=False, indent=2)
print(f"  hotspots_v2.json: 上位{len(top_hotspots)}件 / 全{len(hotspots)}グリッド")

# Print top 5
print("\n  【ホットスポット上位5件】")
for i, h in enumerate(top_hotspots[:5], 1):
    print(f"  {i}. ({h['lat']}, {h['lon']}) score={h['risk_score']} count={h['event_count']} {h['dominant_subtype']}")

# ── Summary ────────────────────────────────────────────────────────────────────
scores = [e["risk_score"] for e in scored_events if e["risk_score"]]
print(f"\n=== サマリー ===")
print(f"  スコア計算済み: {len(scores)}件")
print(f"  最高: {max(scores):.4f}")
print(f"  最低: {min(scores):.4f}")
print(f"  平均: {sum(scores)/len(scores):.4f}")
print(f"\nStep 3 完了: {datetime.now().isoformat()}")
