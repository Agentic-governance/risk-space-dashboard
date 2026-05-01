import json, math
from pathlib import Path
from datetime import datetime
from collections import defaultdict

output_dir = Path("dashboard/data")
output_dir.mkdir(parents=True, exist_ok=True)

def load_all_events():
    events = []
    for f in Path("data/normalized").glob("*.json"):
        if "hotspot" in f.name or "scored" in f.name:
            continue
        try:
            with open(f, encoding="utf-8") as fp:
                raw = json.load(fp)
            for e in raw:
                geom = e.get("geometry")
                if not geom or not geom.get("coordinates"):
                    continue
                lon, lat = geom["coordinates"]
                if not (24 < lat < 46 and 122 < lon < 154):
                    continue
                events.append({
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
        except Exception as ex:
            print(f"スキップ: {f.name} - {ex}")
    return events

events = load_all_events()
print(f"総イベント数: {len(events)}")

# Also load scored events for risk_score
scored_path = Path("data/normalized/all_events_scored.json")
if scored_path.exists():
    try:
        with open(scored_path, encoding="utf-8") as fp:
            scored = json.load(fp)
        score_map = {}
        for e in scored:
            if e.get("geometry") and e.get("risk_score"):
                coords = e["geometry"]["coordinates"]
                key = f"{round(coords[1],5)},{round(coords[0],5)}"
                score_map[key] = e["risk_score"]
        applied = 0
        for e in events:
            key = f"{e['lat']},{e['lon']}"
            if key in score_map:
                e["risk_score"] = score_map[key]
                applied += 1
        print(f"リスクスコア適用: {applied}件")
    except Exception as ex:
        print(f"スコア読み込みスキップ: {ex}")

with open(output_dir / "events.json", "w", encoding="utf-8") as f:
    json.dump(events, f, ensure_ascii=False)

layer_counts = {}
for e in events:
    layer_counts[e["layer"]] = layer_counts.get(e["layer"], 0) + 1
print(f"レイヤー別: {layer_counts}")

for layer in ["crime", "traffic", "disaster", "weather"]:
    pts = [[e["lat"], e["lon"], min(1.0, e["severity"] / 5.0)]
           for e in events if e["layer"] == layer]
    with open(output_dir / f"heat_{layer}.json", "w", encoding="utf-8") as f:
        json.dump(pts, f)
    print(f"  {layer}: {len(pts)}点")

all_pts = [[e["lat"], e["lon"],
            min(1.0, e["risk_score"] if e["risk_score"] > 0 else e["severity"] / 5.0)]
           for e in events]
with open(output_dir / "heat_all.json", "w", encoding="utf-8") as f:
    json.dump(all_pts, f)
print(f"  全体: {len(all_pts)}点")

# ========================================
# 新機能A: エリア別リスク集計（解説パネル用）
# ========================================
GRID = 0.05

grid_data = defaultdict(lambda: {
    "count": 0, "severity_sum": 0, "layers": defaultdict(int),
    "subtypes": defaultdict(int), "max_severity": 0,
    "lat": 0, "lon": 0, "events": []
})

for e in events:
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
            "layer": e["layer"],
            "subtype": e["subtype"],
            "severity": e["severity"],
            "occurred_at": e["occurred_at"],
            "city": e["city"],
        })

for key, cell in grid_data.items():
    density_score = min(1.0, cell["count"] / 50.0)
    severity_score = cell["severity_sum"] / max(1, cell["count"]) / 5.0
    cell["risk_score"] = round(density_score * 0.6 + severity_score * 0.4, 4)
    cell["avg_severity"] = round(cell["severity_sum"] / max(1, cell["count"]), 2)

grid_list = []
for key, cell in grid_data.items():
    if cell["count"] < 2:
        continue
    grid_list.append({
        "lat": cell["lat"],
        "lon": cell["lon"],
        "count": cell["count"],
        "risk_score": cell["risk_score"],
        "avg_severity": cell["avg_severity"],
        "max_severity": cell["max_severity"],
        "layers": dict(cell["layers"]),
        "subtypes": dict(sorted(cell["subtypes"].items(), key=lambda x: -x[1])[:5]),
        "events": cell["events"],
    })

grid_list.sort(key=lambda x: -x["risk_score"])
with open(output_dir / "grid_risk.json", "w", encoding="utf-8") as f:
    json.dump(grid_list, f, ensure_ascii=False)
print(f"グリッドデータ: {len(grid_list)}セル生成")

# ========================================
# 新機能B: 等高線用グリッドデータ
# ========================================
CONTOUR_GRID = 0.1
LAT_MIN, LAT_MAX = 24.0, 46.0
LON_MIN, LON_MAX = 122.0, 154.0

lat_steps = int((LAT_MAX - LAT_MIN) / CONTOUR_GRID) + 1
lon_steps = int((LON_MAX - LON_MIN) / CONTOUR_GRID) + 1

matrix = [[0.0] * lon_steps for _ in range(lat_steps)]

SIGMA = 0.3

for e in events:
    sev = e["severity"] / 5.0
    lat_idx = (e["lat"] - LAT_MIN) / CONTOUR_GRID
    lon_idx = (e["lon"] - LON_MIN) / CONTOUR_GRID

    r = int(SIGMA / CONTOUR_GRID * 3)
    for di in range(-r, r+1):
        for dj in range(-r, r+1):
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
print(f"等高線マトリクス: {lat_steps}x{lon_steps}")

# サマリー
summary = {
    "total": len(events),
    "layers": layer_counts,
    "grid_cells": len(grid_list),
    "generated_at": datetime.now().isoformat(),
}
with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print("全データ前処理完了")
