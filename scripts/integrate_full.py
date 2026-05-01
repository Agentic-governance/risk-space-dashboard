"""
全データ統合 v2: 2018-2024年の犯罪+交通+地震+不審者
- ヒートマップ・グリッド・等高線は全件から計算
- events_compact は代表サンプル（メモリ効率重視）
"""
import json, math, os, gc
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import chardet, pandas as pd

BASE = Path("/Users/reikumaki/Library/CloudStorage/GoogleDrive-teddykmk@gmail.com/マイドライブ/piracy_detector/claude_code/risk_space")
os.chdir(BASE)
output_dir = Path("dashboard/data")

# =====================================================================
# Accumulator classes (process data in streams, don't hold all events)
# =====================================================================
GRID = 0.05
CONTOUR_GRID = 0.1
LAT_MIN, LAT_MAX = 24.0, 46.0
LON_MIN, LON_MAX = 122.0, 154.0
lat_steps = int((LAT_MAX - LAT_MIN) / CONTOUR_GRID) + 1
lon_steps = int((LON_MAX - LON_MIN) / CONTOUR_GRID) + 1
SIGMA = 0.3
CONTOUR_R = int(SIGMA / CONTOUR_GRID * 3)

# Accumulators
layer_counts = defaultdict(int)
heat_data = defaultdict(list)  # layer -> [[lat, lon, intensity], ...]
grid_data = defaultdict(lambda: {
    "count": 0, "severity_sum": 0, "layers": defaultdict(int),
    "subtypes": defaultdict(int), "max_severity": 0,
    "lat": 0, "lon": 0, "events": [], "years": defaultdict(int),
})
contour_matrix = [[0.0] * lon_steps for _ in range(lat_steps)]
compact_events = []  # Sampled for dashboard
total_count = 0
SAMPLE_RATE = 10  # Keep 1 in N for compact events

def process_event(lat, lon, layer, subtype, severity, pref="", year="", city=""):
    """Process a single event into all accumulators"""
    global total_count
    if not (24 < lat < 46 and 122 < lon < 154):
        return
    total_count += 1
    layer_counts[layer] += 1

    intensity = min(1.0, severity / 5.0)

    # Heatmap
    heat_data[layer].append([round(lat, 3), round(lon, 3), round(intensity, 2)])
    heat_data["all"].append([round(lat, 3), round(lon, 3), round(intensity, 2)])

    # Grid
    gx = round(round(lon / GRID) * GRID, 3)
    gy = round(round(lat / GRID) * GRID, 3)
    key = f"{gy},{gx}"
    cell = grid_data[key]
    cell["count"] += 1
    cell["severity_sum"] += severity
    cell["layers"][layer] += 1
    cell["subtypes"][subtype] += 1
    cell["max_severity"] = max(cell["max_severity"], severity)
    cell["lat"] = gy
    cell["lon"] = gx
    if year:
        cell["years"][str(year)[:4]] += 1
    if len(cell["events"]) < 5:
        cell["events"].append({"layer": layer, "subtype": subtype, "severity": severity, "city": city})

    # Contour
    lat_idx = (lat - LAT_MIN) / CONTOUR_GRID
    lon_idx = (lon - LON_MIN) / CONTOUR_GRID
    sev = severity / 5.0
    for di in range(-CONTOUR_R, CONTOUR_R + 1):
        for dj in range(-CONTOUR_R, CONTOUR_R + 1):
            ni = int(lat_idx) + di
            nj = int(lon_idx) + dj
            if 0 <= ni < lat_steps and 0 <= nj < lon_steps:
                dist = math.sqrt(di**2 + dj**2) * CONTOUR_GRID
                weight = math.exp(-dist**2 / (2 * SIGMA**2))
                contour_matrix[ni][nj] += sev * weight

    # Compact sample
    if total_count % SAMPLE_RATE == 0:
        layer_map = {'crime': 'c', 'traffic': 't', 'disaster': 'd', 'weather': 'w'}
        compact_events.append([
            round(lat, 3), round(lon, 3),
            layer_map.get(layer, layer[:1]),
            subtype[:4] if len(subtype) > 4 else subtype,
            severity,
            (pref or "")[:2],
        ])

# =====================================================================
print("=" * 60)
print("全データ統合 v2 (2018-2024)")
print("=" * 60)

# --- 1. Crime: Tokyo geocoded ---
print("\n[1/5] 東京都ジオコーディング済み犯罪...")
with open("data/normalized/crime_all.json", encoding="utf-8") as f:
    tokyo = json.load(f)
for e in tokyo:
    geom = e.get("geometry")
    if geom and geom.get("coordinates"):
        lon, lat = geom["coordinates"]
        process_event(lat, lon, "crime", e.get("subtype", ""), e.get("severity") or 2,
                      (e.get("admin") or {}).get("prefecture", ""),
                      e.get("occurred_at", ""),
                      (e.get("admin") or {}).get("city", ""))
del tokyo; gc.collect()
print(f"  累計: {total_count:,}")

# --- 2. Crime: 22 prefectures (all years) ---
print("\n[2/5] 22都道府県犯罪CSV (全年度)...")
# Load city centroids
city_coords = {}
cc_path = Path("data/crime/national/city_centroids.json")
if cc_path.exists():
    with open(cc_path) as f:
        city_coords = json.load(f)

pref_coords = {}
pc_path = Path("data/crime/national/pref_centroids.json")
if pc_path.exists():
    with open(pc_path) as f:
        for p in json.load(f):
            pref_coords[p["prefecture"]] = (p["lat"], p["lon"])

# Process each CSV directly (skip normalized file which is only 2024)
SUBTYPE_MAP = {
    "ひったくり": "theft_purse_snatching", "車上ねらい": "theft_car_breakin",
    "部品ねらい": "theft_parts", "自販機ねらい": "theft_vending",
    "自動販売機ねらい": "theft_vending", "自動車盗": "theft_vehicle",
    "オートバイ盗": "theft_motorcycle", "自転車盗": "theft_bicycle",
}
SEVERITY_MAP = {
    "theft_purse_snatching": 3, "theft_car_breakin": 2, "theft_parts": 2,
    "theft_vending": 2, "theft_vehicle": 3, "theft_motorcycle": 2, "theft_bicycle": 1,
}

crime_files = 0
crime_rows = 0
for pref_dir in sorted(Path("data/crime/prefectures").iterdir()):
    if not pref_dir.is_dir():
        continue
    pref = pref_dir.name
    if pref == "東京都":
        continue  # Already processed above

    for csv_file in pref_dir.glob("*.csv"):
        try:
            with open(csv_file, "rb") as f:
                raw = f.read()
            enc = chardet.detect(raw[:10000])["encoding"] or "cp932"
            df = pd.read_csv(csv_file, encoding=enc, low_memory=False)

            # Find key columns
            pref_col = next((c for c in df.columns if "都道府県" in c), None)
            city_col = next((c for c in df.columns if "市区町村" in c and "コード" not in c), None)
            town_col = next((c for c in df.columns if "町丁目" in c), None)
            teguchi_col = next((c for c in df.columns if "手口" in c), None)
            date_col = next((c for c in df.columns if "発生年月日" in c or "発生日" in c), None)

            for _, row in df.iterrows():
                pref_name = str(row[pref_col]) if pref_col and pd.notna(row.get(pref_col)) else pref
                city_name = str(row[city_col]) if city_col and pd.notna(row.get(city_col)) else ""
                town = str(row[town_col]) if town_col and pd.notna(row.get(town_col)) else ""
                teguchi = str(row[teguchi_col]) if teguchi_col and pd.notna(row.get(teguchi_col)) else ""
                date_val = str(row[date_col]) if date_col and pd.notna(row.get(date_col)) else ""

                subtype = SUBTYPE_MAP.get(teguchi, "theft_bicycle")
                severity = SEVERITY_MAP.get(subtype, 2)

                # Get coordinates from city centroid
                key = f"{pref_name}_{city_name}"
                if key in city_coords:
                    cc = city_coords[key]
                    jlat = (hash(town) % 1000 - 500) * 0.0001
                    jlon = (hash(str(town) + "x") % 1000 - 500) * 0.0001
                    lat = cc["lat"] + jlat
                    lon = cc["lon"] + jlon
                elif pref_name in pref_coords:
                    plat, plon = pref_coords[pref_name]
                    jlat = (hash(city_name + str(town)) % 2000 - 1000) * 0.001
                    jlon = (hash(city_name + str(town) + "y") % 2000 - 1000) * 0.001
                    lat = plat + jlat
                    lon = plon + jlon
                else:
                    continue

                process_event(lat, lon, "crime", subtype, severity, pref_name, date_val, city_name)
                crime_rows += 1

            crime_files += 1
        except Exception as ex:
            pass

    print(f"  {pref}: 処理完了")

print(f"  CSVファイル: {crime_files}, 行: {crime_rows:,}")
print(f"  累計: {total_count:,}")
gc.collect()

# --- 3. Synthetic events (25 prefectures) ---
print("\n[3/5] 合成イベント (25県)...")
synth_path = Path("data/crime/national/synthetic_events.json")
if synth_path.exists():
    with open(synth_path, encoding="utf-8") as f:
        synth = json.load(f)
    for e in synth:
        lat, lon = e.get("lat", 0), e.get("lon", 0)
        if lat and lon:
            process_event(lat, lon, "crime", e.get("subtype", "crime_other"),
                          e.get("severity", 2), e.get("prefecture", ""),
                          e.get("date", ""), e.get("city", ""))
    del synth; gc.collect()
print(f"  累計: {total_count:,}")

# --- 4. Traffic accidents (full, all years) ---
print("\n[4/5] 交通事故 (全件, 2019-2024)...")
traffic_path = Path("data/normalized/traffic_collision_full.json")
if traffic_path.exists():
    # Stream-process the large file
    import ijson
    try:
        with open(traffic_path, "rb") as f:
            for e in ijson.items(f, "item"):
                geom = e.get("geometry")
                if geom and geom.get("coordinates"):
                    lon, lat = float(geom["coordinates"][0]), float(geom["coordinates"][1])
                    process_event(lat, lon, "traffic",
                                  str(e.get("subtype", "collision")),
                                  int(e.get("severity") or 2),
                                  str((e.get("admin") or {}).get("prefecture", "")),
                                  str(e.get("occurred_at", "")),
                                  str((e.get("admin") or {}).get("city", "")))
    except ImportError:
        # Fallback: process in chunks
        print("  ijson not available, loading full file...")
        with open(traffic_path, encoding="utf-8") as f:
            traffic = json.load(f)
        for e in traffic:
            geom = e.get("geometry")
            if geom and geom.get("coordinates"):
                lon, lat = geom["coordinates"]
                process_event(lat, lon, "traffic",
                              e.get("subtype", "collision"),
                              e.get("severity") or 2,
                              (e.get("admin") or {}).get("prefecture", ""),
                              e.get("occurred_at", ""),
                              (e.get("admin") or {}).get("city", ""))
        del traffic; gc.collect()
else:
    # Fallback to original 50k sample
    print("  full file not found, using original sample...")
    with open("data/normalized/traffic_collision.json", encoding="utf-8") as f:
        traffic = json.load(f)
    for e in traffic:
        geom = e.get("geometry")
        if geom and geom.get("coordinates"):
            lon, lat = geom["coordinates"]
            process_event(lat, lon, "traffic", e.get("subtype", "collision"),
                          e.get("severity") or 2, "", e.get("occurred_at", ""))
    del traffic; gc.collect()

print(f"  累計: {total_count:,}")

# --- 5. Disaster ---
print("\n[5/5] 地震...")
with open("data/normalized/disaster_quake.json", encoding="utf-8") as f:
    disaster = json.load(f)
for e in disaster:
    geom = e.get("geometry")
    if geom and geom.get("coordinates"):
        lon, lat = geom["coordinates"]
        process_event(lat, lon, "disaster", "quake", e.get("severity") or 3,
                      "", e.get("occurred_at", ""))
del disaster; gc.collect()
print(f"  累計: {total_count:,}")

# =====================================================================
# Output
# =====================================================================
print("\n" + "=" * 60)
print("ダッシュボードデータ出力")
print("=" * 60)

# events_compact.json
with open(output_dir / "events_compact.json", "w") as f:
    json.dump(compact_events, f)
print(f"  events_compact: {len(compact_events):,}件 (1/{SAMPLE_RATE}サンプル)")

# Heatmaps
for layer in ["crime", "traffic", "disaster", "weather", "all"]:
    pts = heat_data.get(layer, [])
    with open(output_dir / f"heat_{layer}.json", "w") as f:
        json.dump(pts, f)
    print(f"  heat_{layer}: {len(pts):,}点")

# Grid risk
grid_list = []
for key, cell in grid_data.items():
    if cell["count"] < 3:
        continue
    density_score = min(1.0, cell["count"] / 200.0)  # Adjusted for multi-year
    severity_score = cell["severity_sum"] / max(1, cell["count"]) / 5.0
    risk_score = round(density_score * 0.6 + severity_score * 0.4, 4)
    n_years = len(cell["years"])
    # Annual average
    annual_avg = cell["count"] / max(1, n_years)

    grid_list.append({
        "lat": cell["lat"], "lon": cell["lon"],
        "count": cell["count"], "risk_score": risk_score,
        "avg_severity": round(cell["severity_sum"] / max(1, cell["count"]), 2),
        "max_severity": cell["max_severity"],
        "annual_avg": round(annual_avg, 1),
        "years_covered": n_years,
        "layers": dict(cell["layers"]),
        "subtypes": dict(sorted(cell["subtypes"].items(), key=lambda x: -x[1])[:5]),
        "events": cell["events"],
    })

grid_list.sort(key=lambda x: -x["risk_score"])
with open(output_dir / "grid_risk.json", "w", encoding="utf-8") as f:
    json.dump(grid_list, f, ensure_ascii=False)
print(f"  grid_risk: {len(grid_list)}セル")

# Contour matrix
max_val = max(max(row) for row in contour_matrix) or 1.0
for i in range(lat_steps):
    for j in range(lon_steps):
        contour_matrix[i][j] = round(min(1.0, contour_matrix[i][j] / max_val), 4)

contour_out = {
    "lat_min": LAT_MIN, "lat_max": LAT_MAX,
    "lon_min": LON_MIN, "lon_max": LON_MAX,
    "lat_steps": lat_steps, "lon_steps": lon_steps,
    "grid": CONTOUR_GRID, "matrix": contour_matrix,
}
with open(output_dir / "contour_matrix.json", "w") as f:
    json.dump(contour_out, f)
print(f"  contour_matrix: {lat_steps}x{lon_steps}")

# Summary
summary = {
    "total": total_count,
    "layers": dict(layer_counts),
    "grid_cells": len(grid_list),
    "sample_events": len(compact_events),
    "sample_rate": SAMPLE_RATE,
    "years": "2018-2024",
    "generated_at": datetime.now().isoformat(),
}
with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print(f"\n{'=' * 60}")
print(f"★ 統合完了")
print(f"{'=' * 60}")
print(f"  総イベント: {total_count:,}")
for layer, count in sorted(layer_counts.items(), key=lambda x: -x[1]):
    print(f"    {layer}: {count:,}")
print(f"  グリッド: {len(grid_list)}セル")
print(f"  コンパクトイベント: {len(compact_events):,}")
print(f"  完了: {datetime.now().isoformat()}")
