#!/usr/bin/env python3
import json
import math
import shutil
from pathlib import Path

import numpy as np
from tqdm import tqdm

JAPAN_BOUNDS = {
    "lat_min": 24.0,
    "lat_max": 45.7,
    "lon_min": 122.5,
    "lon_max": 154.0,
}

GRID_RES_LAT = 0.009
GRID_RES_LON = 0.011
HAVEN_INDEX_RES = 0.05
CLOUDY_WET_LIFT = 27.073

PREF_BASELINE_RISK = {
    "北海道": 0.18,
    "青森県": 0.10,
    "岩手県": 0.09,
    "宮城県": 0.14,
    "秋田県": 0.08,
    "山形県": 0.08,
    "福島県": 0.11,
    "茨城県": 0.16,
    "栃木県": 0.15,
    "群馬県": 0.15,
    "埼玉県": 0.20,
    "千葉県": 0.20,
    "東京都": 0.28,
    "神奈川県": 0.22,
    "新潟県": 0.10,
    "富山県": 0.09,
    "石川県": 0.11,
    "福井県": 0.08,
    "山梨県": 0.11,
    "長野県": 0.10,
    "岐阜県": 0.13,
    "静岡県": 0.15,
    "愛知県": 0.24,
    "三重県": 0.13,
    "滋賀県": 0.13,
    "京都府": 0.18,
    "大阪府": 0.32,
    "兵庫県": 0.19,
    "奈良県": 0.12,
    "和歌山県": 0.12,
    "鳥取県": 0.08,
    "島根県": 0.07,
    "岡山県": 0.14,
    "広島県": 0.15,
    "山口県": 0.11,
    "徳島県": 0.09,
    "香川県": 0.11,
    "愛媛県": 0.11,
    "高知県": 0.10,
    "福岡県": 0.22,
    "佐賀県": 0.10,
    "長崎県": 0.11,
    "熊本県": 0.12,
    "大分県": 0.10,
    "宮崎県": 0.10,
    "鹿児島県": 0.11,
    "沖縄県": 0.17,
    "default": 0.13,
}

PREF_BOUNDS = {
    "北海道": (41.3, 141.0, 45.7, 145.8),
    "青森県": (40.2, 139.5, 41.6, 142.0),
    "岩手県": (38.7, 140.5, 40.5, 142.1),
    "宮城県": (37.7, 140.2, 39.0, 141.7),
    "秋田県": (38.8, 139.5, 40.7, 141.0),
    "山形県": (37.7, 139.3, 39.0, 140.7),
    "福島県": (36.7, 139.2, 37.9, 141.0),
    "茨城県": (35.7, 139.7, 36.8, 140.9),
    "栃木県": (36.2, 139.3, 37.1, 140.3),
    "群馬県": (36.0, 138.4, 37.0, 139.6),
    "埼玉県": (35.7, 138.7, 36.3, 139.9),
    "千葉県": (35.0, 139.7, 36.1, 140.9),
    "東京都": (35.5, 138.9, 35.9, 139.9),
    "神奈川県": (35.1, 138.9, 35.7, 139.8),
    "新潟県": (36.7, 137.5, 38.6, 139.8),
    "富山県": (36.3, 136.8, 36.9, 137.7),
    "石川県": (36.0, 136.1, 37.9, 137.4),
    "福井県": (35.4, 135.5, 36.3, 136.8),
    "山梨県": (35.2, 138.0, 35.9, 139.0),
    "長野県": (35.2, 137.1, 37.0, 138.9),
    "岐阜県": (35.1, 136.0, 36.5, 137.9),
    "静岡県": (34.6, 137.5, 35.7, 139.2),
    "愛知県": (34.5, 136.7, 35.4, 137.7),
    "三重県": (33.7, 135.8, 35.2, 136.9),
    "滋賀県": (34.8, 135.7, 35.7, 136.4),
    "京都府": (34.7, 134.9, 35.8, 136.0),
    "大阪府": (34.3, 135.1, 35.1, 135.7),
    "兵庫県": (34.2, 134.3, 35.7, 135.5),
    "奈良県": (33.9, 135.6, 34.8, 136.3),
    "和歌山県": (33.4, 135.0, 34.3, 136.0),
    "鳥取県": (35.0, 133.1, 35.6, 134.5),
    "島根県": (34.3, 131.6, 35.5, 133.4),
    "岡山県": (34.4, 133.3, 35.3, 134.6),
    "広島県": (34.0, 132.0, 35.1, 133.5),
    "山口県": (33.7, 130.9, 34.7, 132.3),
    "徳島県": (33.5, 133.8, 34.3, 134.8),
    "香川県": (34.1, 133.5, 34.5, 134.5),
    "愛媛県": (32.9, 132.1, 34.0, 133.7),
    "高知県": (32.7, 132.6, 33.9, 134.3),
    "福岡県": (33.0, 130.0, 34.3, 131.2),
    "佐賀県": (33.1, 129.6, 33.6, 130.4),
    "長崎県": (32.6, 128.5, 33.7, 130.1),
    "熊本県": (32.0, 130.0, 33.2, 131.5),
    "大分県": (32.8, 130.8, 33.9, 132.0),
    "宮崎県": (31.4, 130.6, 33.0, 131.9),
    "鹿児島県": (30.0, 129.4, 32.3, 131.3),
    "沖縄県": (24.0, 122.9, 27.1, 131.3),
}

ROOT = Path(__file__).resolve().parent.parent
HAVENS_PATH = ROOT / "data/safe_haven/ALL_HAVENS.json"
EXISTING_GRID_PATH = ROOT / "dashboard/data/grid_risk.json"
NATIONAL_GRID_PATH = ROOT / "dashboard/data/grid_risk_national.json"
BACKUP_GRID_PATH = ROOT / "dashboard/data/grid_risk_urban_only.bak.json"
BACKGROUND_MERGED_PATH = ROOT / "data/grid/background/background_grid_new_cells.json"


def haven_bucket_key(lat, lon):
    return (int(math.floor(lat / HAVEN_INDEX_RES)), int(math.floor(lon / HAVEN_INDEX_RES)))


def coord_key(lat, lon):
    lat_q = round(round(float(lat) / GRID_RES_LAT) * GRID_RES_LAT, 6)
    lon_q = round(round(float(lon) / GRID_RES_LON) * GRID_RES_LON, 6)
    return (lat_q, lon_q)


def build_haven_index(havens):
    idx = {}
    for h in havens:
        if not h.get("is_24h", False):
            continue
        lat = h.get("lat")
        lon = h.get("lon")
        if lat is None or lon is None:
            continue
        k = haven_bucket_key(float(lat), float(lon))
        idx[k] = idx.get(k, 0) + 1
    return idx


def get_haven_count(lat, lon, haven_idx):
    bi, bj = haven_bucket_key(lat, lon)
    total = 0
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            total += haven_idx.get((bi + di, bj + dj), 0)
    return int(total)


def get_pref_for_coord(lat, lon, lat_candidates=None):
    candidates = lat_candidates if lat_candidates is not None else PREF_BOUNDS.items()
    for pref, (lat_min, lon_min, lat_max, lon_max) in candidates:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return pref
    return None


def calc_p_escape_background(lat, lon, pref, haven_idx):
    del pref
    haven_count = get_haven_count(lat, lon, haven_idx)
    density_score = min(1.0, haven_count / 5.0)
    distance_score = 0.85 if haven_count >= 3 else (0.50 if haven_count >= 1 else 0.15)
    arrival_score = 0.3 if haven_count == 0 else 0.6
    p_escape = distance_score * 0.35 + density_score * 0.25 + arrival_score * 0.40
    return round(min(1.0, p_escape), 4)


def main():
    if not HAVENS_PATH.exists():
        raise FileNotFoundError(f"Missing safe haven data: {HAVENS_PATH}")
    if not EXISTING_GRID_PATH.exists():
        raise FileNotFoundError(f"Missing existing grid data: {EXISTING_GRID_PATH}")

    havens = json.loads(HAVENS_PATH.read_text(encoding="utf-8"))
    haven_idx = build_haven_index(havens)

    existing_grid = json.loads(EXISTING_GRID_PATH.read_text(encoding="utf-8"))
    existing_keys = {
        coord_key(c.get("lat"), c.get("lon"))
        for c in existing_grid
        if c.get("lat") is not None and c.get("lon") is not None
    }

    lats = np.arange(JAPAN_BOUNDS["lat_min"], JAPAN_BOUNDS["lat_max"], GRID_RES_LAT, dtype=np.float32)
    lons = np.arange(JAPAN_BOUNDS["lon_min"], JAPAN_BOUNDS["lon_max"], GRID_RES_LON, dtype=np.float32)

    new_background_cells = []
    generated_land_cells = 0

    pref_items = list(PREF_BOUNDS.items())

    for lat in tqdm(lats, desc="Building background grid", total=len(lats)):
        lat_f = float(lat)
        lat_candidates = [
            (pref, b)
            for pref, b in pref_items
            if b[0] <= lat_f <= b[2]
        ]
        if not lat_candidates:
            continue

        for lon in lons:
            lon_f = float(lon)
            pref = get_pref_for_coord(lat_f, lon_f, lat_candidates=lat_candidates)
            if pref is None:
                continue

            generated_land_cells += 1

            ck = coord_key(lat_f, lon_f)
            if ck in existing_keys:
                continue

            base_risk = float(PREF_BASELINE_RISK.get(pref, PREF_BASELINE_RISK["default"]))
            haven_count = get_haven_count(lat_f, lon_f, haven_idx)
            p_escape = calc_p_escape_background(lat_f, lon_f, pref, haven_idx)
            child_dynamic_risk = min(1.0, base_risk * CLOUDY_WET_LIFT)
            child_p_escape = p_escape * 0.7
            eh_child = child_dynamic_risk * 0.5 * (1 - child_p_escape)
            eh = min(1.0, base_risk * 0.5 * (1 - p_escape))

            new_background_cells.append(
                {
                    "lat": round(lat_f, 6),
                    "lon": round(lon_f, 6),
                    "resolution": "background_1km",
                    "pref": pref,
                    "risk_score": round(base_risk, 4),
                    "p_escape": round(float(p_escape), 4),
                    "expected_harm": round(float(eh), 4),
                    "expected_harm_child_cloudy_wet": round(float(eh_child), 4),
                    "haven_count_500m": int(haven_count),
                    "is_background": True,
                }
            )

    full_grid = existing_grid + new_background_cells

    BACKGROUND_MERGED_PATH.parent.mkdir(parents=True, exist_ok=True)
    BACKGROUND_MERGED_PATH.write_text(
        json.dumps(new_background_cells, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    NATIONAL_GRID_PATH.write_text(
        json.dumps(full_grid, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    if EXISTING_GRID_PATH.exists():
        shutil.copyfile(EXISTING_GRID_PATH, BACKUP_GRID_PATH)
    shutil.copyfile(NATIONAL_GRID_PATH, EXISTING_GRID_PATH)

    print(f"existing_cells={len(existing_grid)}")
    print(f"generated_land_cells={generated_land_cells}")
    print(f"new_background_cells={len(new_background_cells)}")
    print(f"full_grid_cells={len(full_grid)}")
    print(f"saved_background_new={BACKGROUND_MERGED_PATH}")
    print(f"saved_national={NATIONAL_GRID_PATH}")
    print(f"backup_original={BACKUP_GRID_PATH}")


if __name__ == "__main__":
    main()
