"""
全犯罪データ統合スクリプト
- 22都道府県CSV正規化データ (crime_national.json) → 市区町村重心でジオコーディング
- 東京都ジオコーディング済み (crime_all.json)
- 合成イベント (synthetic_events.json) → 24未取得県
- 交通事故 (traffic_collision.json)
- 地震 (disaster_quake.json)
→ 統合してダッシュボードデータ再生成
"""
import json, os, time, re, math
from pathlib import Path
from collections import defaultdict
from datetime import datetime

BASE = Path("/Users/reikumaki/Library/CloudStorage/GoogleDrive-teddykmk@gmail.com/マイドライブ/piracy_detector/claude_code/risk_space")
os.chdir(BASE)

# =====================================================================
# Step 1: 市区町村→座標マッピング（国土地理院APIバッチ）
# =====================================================================
print("=" * 60)
print("Step 1: 市区町村重心座標マッピング構築")
print("=" * 60)

# First, collect unique city names from the normalized data
with open("data/normalized/crime_national.json", encoding="utf-8") as f:
    crime_national = json.load(f)
print(f"  22都道府県正規化データ: {len(crime_national):,}件")

# Collect unique prefecture+city combinations
city_set = set()
for e in crime_national:
    admin = e.get("admin", {})
    pref = admin.get("prefecture", "")
    city = admin.get("city", "")
    if pref and city:
        city_set.add((pref, city))

print(f"  ユニーク市区町村: {len(city_set)}件")

# Try to load existing geocoded city centroids
centroid_cache_path = Path("data/crime/national/city_centroids.json")
city_coords = {}
if centroid_cache_path.exists():
    with open(centroid_cache_path, encoding="utf-8") as f:
        city_coords = json.load(f)
    print(f"  キャッシュ済み: {len(city_coords)}市区町村")

# Prefecture centroids as fallback
pref_centroids_path = Path("data/crime/national/pref_centroids.json")
pref_coords = {}
if pref_centroids_path.exists():
    with open(pref_centroids_path, encoding="utf-8") as f:
        pref_data = json.load(f)
    for p in pref_data:
        pref_coords[p["prefecture"]] = (p["lat"], p["lon"])
    print(f"  都道府県重心: {len(pref_coords)}件")

# Geocode missing cities via 国土地理院 API
import requests
headers = {"User-Agent": "Mozilla/5.0"}

missing_cities = [(p, c) for p, c in city_set if f"{p}_{c}" not in city_coords]
print(f"  未ジオコーディング: {len(missing_cities)}市区町村")

if missing_cities:
    print(f"  国土地理院API で市区町村ジオコーディング中...")
    success = 0
    failed = 0

    for i, (pref, city) in enumerate(missing_cities):
        key = f"{pref}_{city}"
        query = f"{pref}{city}"
        try:
            r = requests.get(
                "https://msearch.gsi.go.jp/address-search/AddressSearch",
                params={"q": query},
                headers=headers,
                timeout=10,
            )
            if r.status_code == 200:
                results = r.json()
                if results:
                    coords = results[0]["geometry"]["coordinates"]
                    city_coords[key] = {"lat": coords[1], "lon": coords[0]}
                    success += 1
                else:
                    failed += 1
            else:
                failed += 1
        except:
            failed += 1

        if (i + 1) % 50 == 0:
            print(f"    進捗: {i+1}/{len(missing_cities)} (成功: {success}, 失敗: {failed})")
            # Save progress
            with open(centroid_cache_path, "w", encoding="utf-8") as f:
                json.dump(city_coords, f, ensure_ascii=False)

        time.sleep(0.5)  # Rate limit

    print(f"  ジオコーディング完了: 成功 {success} / 失敗 {failed}")
    with open(centroid_cache_path, "w", encoding="utf-8") as f:
        json.dump(city_coords, f, ensure_ascii=False)

# =====================================================================
# Step 2: 座標をアサイン
# =====================================================================
print("\n" + "=" * 60)
print("Step 2: 22都道府県犯罪データに座標アサイン")
print("=" * 60)

assigned = 0
pref_fallback = 0
no_coords = 0

for e in crime_national:
    admin = e.get("admin", {})
    pref = admin.get("prefecture", "")
    city = admin.get("city", "")
    town = admin.get("town", "")

    town = town or ""
    key = f"{pref}_{city}"
    if key in city_coords:
        cc = city_coords[key]
        # Add small jitter based on town name hash for spatial spread
        jitter_lat = (hash(town) % 1000 - 500) * 0.0001
        jitter_lon = (hash(town + "x") % 1000 - 500) * 0.0001
        e["geometry"] = {
            "type": "Point",
            "coordinates": [
                round(cc["lon"] + jitter_lon, 6),
                round(cc["lat"] + jitter_lat, 6),
            ]
        }
        assigned += 1
    elif pref in pref_coords:
        lat, lon = pref_coords[pref]
        city = city or ""
        jitter_lat = (hash(city + town) % 2000 - 1000) * 0.001
        jitter_lon = (hash(city + town + "y") % 2000 - 1000) * 0.001
        e["geometry"] = {
            "type": "Point",
            "coordinates": [round(lon + jitter_lon, 6), round(lat + jitter_lat, 6)]
        }
        pref_fallback += 1
    else:
        no_coords += 1

print(f"  市区町村座標: {assigned:,}件")
print(f"  都道府県重心fallback: {pref_fallback:,}件")
print(f"  座標なし: {no_coords:,}件")

# =====================================================================
# Step 3: 全データ統合
# =====================================================================
print("\n" + "=" * 60)
print("Step 3: 全データ統合")
print("=" * 60)

all_events = []

# 3-1: Tokyo geocoded (already in normalized)
with open("data/normalized/crime_all.json", encoding="utf-8") as f:
    tokyo_crime = json.load(f)
tokyo_with_coords = [e for e in tokyo_crime if e.get("geometry") and e["geometry"].get("coordinates")]
print(f"  東京都（ジオコーディング済み）: {len(tokyo_with_coords):,}件")
all_events.extend(tokyo_with_coords)

# 3-2: 22 prefectures (excluding Tokyo which is already included)
national_with_coords = [e for e in crime_national
                        if e.get("geometry") and e["geometry"].get("coordinates")
                        and e.get("admin", {}).get("prefecture") != "東京都"]
print(f"  22都道府県（座標付き）: {len(national_with_coords):,}件")
all_events.extend(national_with_coords)

# 3-3: Synthetic events for missing prefectures
synth_path = Path("data/crime/national/synthetic_events.json")
synth_events = []
if synth_path.exists():
    with open(synth_path, encoding="utf-8") as f:
        synth_raw = json.load(f)
    for e in synth_raw:
        if e.get("lat") and e.get("lon"):
            lat, lon = e["lat"], e["lon"]
            if 24 < lat < 46 and 122 < lon < 154:
                synth_events.append({
                    "id": e.get("event_id", ""),
                    "layer": "crime",
                    "subtype": e.get("subtype", "crime_other"),
                    "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                    "admin": {
                        "prefecture": e.get("prefecture", ""),
                        "city": e.get("city", ""),
                    },
                    "occurred_at": e.get("date", ""),
                    "severity": e.get("severity", 2),
                    "risk_score": None,
                    "source": {"org": "e-Stat合成", "synthetic": True},
                })
    print(f"  合成イベント: {len(synth_events):,}件")
    all_events.extend(synth_events)

# 3-4: Traffic accidents
traffic_path = Path("data/normalized/traffic_collision.json")
if traffic_path.exists():
    with open(traffic_path, encoding="utf-8") as f:
        traffic = json.load(f)
    traffic_with_coords = [e for e in traffic if e.get("geometry") and e["geometry"].get("coordinates")]
    print(f"  交通事故: {len(traffic_with_coords):,}件")
    all_events.extend(traffic_with_coords)

# 3-5: Disaster (earthquake)
disaster_path = Path("data/normalized/disaster_quake.json")
if disaster_path.exists():
    with open(disaster_path, encoding="utf-8") as f:
        disaster = json.load(f)
    disaster_with_coords = [e for e in disaster if e.get("geometry") and e["geometry"].get("coordinates")]
    print(f"  地震: {len(disaster_with_coords):,}件")
    all_events.extend(disaster_with_coords)

print(f"\n  ★ 統合イベント総数: {len(all_events):,}件")

# =====================================================================
# Step 4: ダッシュボードデータ再生成
# =====================================================================
print("\n" + "=" * 60)
print("Step 4: ダッシュボードデータ再生成")
print("=" * 60)

output_dir = Path("dashboard/data")
output_dir.mkdir(parents=True, exist_ok=True)

# Build events for dashboard (slim version)
dash_events = []
for e in all_events:
    geom = e.get("geometry")
    if not geom or not geom.get("coordinates"):
        continue
    lon, lat = geom["coordinates"]
    if not (24 < lat < 46 and 122 < lon < 154):
        continue
    dash_events.append({
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "layer": e.get("layer", "unknown"),
        "subtype": e.get("subtype", ""),
        "severity": e.get("severity") or 2,
        "risk_score": e.get("risk_score") or 0,
        "occurred_at": (e.get("occurred_at") or "")[:10],
        "pref": (e.get("admin") or {}).get("prefecture", ""),
        "city": (e.get("admin") or {}).get("city", ""),
        "source_org": (e.get("source") or {}).get("org", ""),
        "raw": {},
    })

print(f"  ダッシュボード用イベント: {len(dash_events):,}件")

with open(output_dir / "events.json", "w", encoding="utf-8") as f:
    json.dump(dash_events, f, ensure_ascii=False)

# Layer counts
layer_counts = defaultdict(int)
for e in dash_events:
    layer_counts[e["layer"]] += 1
print(f"  レイヤー別: {dict(layer_counts)}")

# Heatmap data
for layer in ["crime", "traffic", "disaster", "weather"]:
    pts = [[e["lat"], e["lon"], min(1.0, e["severity"] / 5.0)]
           for e in dash_events if e["layer"] == layer]
    with open(output_dir / f"heat_{layer}.json", "w", encoding="utf-8") as f:
        json.dump(pts, f)
    print(f"  heat_{layer}: {len(pts):,}点")

all_pts = [[e["lat"], e["lon"],
            min(1.0, e["risk_score"] if e["risk_score"] > 0 else e["severity"] / 5.0)]
           for e in dash_events]
with open(output_dir / "heat_all.json", "w", encoding="utf-8") as f:
    json.dump(all_pts, f)
print(f"  heat_all: {len(all_pts):,}点")

# Grid risk data
GRID = 0.05
grid_data = defaultdict(lambda: {
    "count": 0, "severity_sum": 0, "layers": defaultdict(int),
    "subtypes": defaultdict(int), "max_severity": 0,
    "lat": 0, "lon": 0, "events": []
})

for e in dash_events:
    gx = round(round(e["lon"] / GRID) * GRID, 3)
    gy = round(round(e["lat"] / GRID) * GRID, 3)
    key = f"{gy},{gx}"
    cell = grid_data[key]
    cell["count"] += 1
    cell["severity_sum"] += e["severity"]
    cell["layers"][e["layer"]] += 1
    cell["subtypes"][e["subtype"]] += 1
    cell["max_severity"] = max(cell["max_severity"], e["severity"])
    cell["lat"] = gy
    cell["lon"] = gx
    if len(cell["events"]) < 5:
        cell["events"].append({
            "layer": e["layer"], "subtype": e["subtype"],
            "severity": e["severity"], "occurred_at": e["occurred_at"],
            "city": e["city"],
        })

grid_list = []
for key, cell in grid_data.items():
    if cell["count"] < 2:
        continue
    density_score = min(1.0, cell["count"] / 50.0)
    severity_score = cell["severity_sum"] / max(1, cell["count"]) / 5.0
    risk_score = round(density_score * 0.6 + severity_score * 0.4, 4)
    grid_list.append({
        "lat": cell["lat"], "lon": cell["lon"],
        "count": cell["count"], "risk_score": risk_score,
        "avg_severity": round(cell["severity_sum"] / max(1, cell["count"]), 2),
        "max_severity": cell["max_severity"],
        "layers": dict(cell["layers"]),
        "subtypes": dict(sorted(cell["subtypes"].items(), key=lambda x: -x[1])[:5]),
        "events": cell["events"],
    })

grid_list.sort(key=lambda x: -x["risk_score"])
with open(output_dir / "grid_risk.json", "w", encoding="utf-8") as f:
    json.dump(grid_list, f, ensure_ascii=False)
print(f"  グリッドデータ: {len(grid_list)}セル")

# Contour matrix
CONTOUR_GRID = 0.1
LAT_MIN, LAT_MAX = 24.0, 46.0
LON_MIN, LON_MAX = 122.0, 154.0
lat_steps = int((LAT_MAX - LAT_MIN) / CONTOUR_GRID) + 1
lon_steps = int((LON_MAX - LON_MIN) / CONTOUR_GRID) + 1
matrix = [[0.0] * lon_steps for _ in range(lat_steps)]
SIGMA = 0.3

print(f"  等高線マトリクス計算中 ({lat_steps}x{lon_steps})...")

for e in dash_events:
    sev = e["severity"] / 5.0
    lat_idx = (e["lat"] - LAT_MIN) / CONTOUR_GRID
    lon_idx = (e["lon"] - LON_MIN) / CONTOUR_GRID
    r = int(SIGMA / CONTOUR_GRID * 3)
    for di in range(-r, r + 1):
        for dj in range(-r, r + 1):
            ni = int(lat_idx) + di
            nj = int(lon_idx) + dj
            if 0 <= ni < lat_steps and 0 <= nj < lon_steps:
                dist = math.sqrt(di**2 + dj**2) * CONTOUR_GRID
                weight = math.exp(-dist**2 / (2 * SIGMA**2))
                matrix[ni][nj] += sev * weight

max_val = max(max(row) for row in matrix) or 1.0
for i in range(lat_steps):
    for j in range(lon_steps):
        matrix[i][j] = round(min(1.0, matrix[i][j] / max_val), 4)

contour_data = {
    "lat_min": LAT_MIN, "lat_max": LAT_MAX,
    "lon_min": LON_MIN, "lon_max": LON_MAX,
    "lat_steps": lat_steps, "lon_steps": lon_steps,
    "grid": CONTOUR_GRID,
    "matrix": matrix,
}
with open(output_dir / "contour_matrix.json", "w", encoding="utf-8") as f:
    json.dump(contour_data, f)
print(f"  等高線マトリクス: {lat_steps}x{lon_steps}")

# Summary
summary = {
    "total": len(dash_events),
    "layers": dict(layer_counts),
    "grid_cells": len(grid_list),
    "data_sources": {
        "tokyo_geocoded": len(tokyo_with_coords),
        "prefectures_22": len(national_with_coords),
        "synthetic_25_pref": len(synth_events),
        "traffic": len(traffic_with_coords) if traffic_path.exists() else 0,
        "disaster": len(disaster_with_coords) if disaster_path.exists() else 0,
    },
    "generated_at": datetime.now().isoformat(),
}
with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print(f"\n{'=' * 60}")
print(f"★ 統合完了")
print(f"{'=' * 60}")
print(f"  総イベント: {len(dash_events):,}")
print(f"  犯罪: {layer_counts.get('crime', 0):,}")
print(f"  交通: {layer_counts.get('traffic', 0):,}")
print(f"  災害: {layer_counts.get('disaster', 0):,}")
print(f"  グリッド: {len(grid_list)}セル")
print(f"  完了: {datetime.now().isoformat()}")
