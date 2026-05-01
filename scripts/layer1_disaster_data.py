#!/usr/bin/env python3
"""Layer 1: Disaster shelter database builder and nearest-shelter search."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import geopandas as gpd
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
SHELTER_RAW_DIR = BASE_DIR / "data" / "disaster" / "shelter_raw"
SHELTER_JSON_PATH = BASE_DIR / "data" / "disaster" / "shelter_sites.json"
SHELTER_STATS_PATH = BASE_DIR / "data" / "disaster" / "shelter_stats.json"

EARTH_RADIUS_M = 6_371_000
_ELEVATION_CACHE: Dict[str, float] = {}
_ELEVATION_API_AVAILABLE: Optional[bool] = None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_M * c


def _as_bool_flag(value: Any) -> bool:
    try:
        if value is None:
            return False
        return int(float(value)) == 1
    except (TypeError, ValueError):
        text = str(value).strip()
        return text in {"1", "true", "True"}


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_capacity(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        cap = int(float(value))
        return cap if cap > 0 else None
    except (TypeError, ValueError):
        return None


def get_elevation(lat: float, lon: float) -> float:
    """Get elevation (meters) from GSI API. Returns 0.0 on any failure."""
    global _ELEVATION_API_AVAILABLE

    if _ELEVATION_API_AVAILABLE is False:
        return 0.0

    url = (
        "https://cyberjapandata2.gsi.go.jp/general/dem/scripts/getelevation.php"
        f"?lon={lon}&lat={lat}&outtype=JSON"
    )
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        payload = resp.json()
        elev = float(payload.get("elevation", 0.0) or 0.0)
        _ELEVATION_API_AVAILABLE = True
        return elev
    except Exception:
        _ELEVATION_API_AVAILABLE = False
        return 0.0


def _read_pref_shelter(pref_code: str) -> gpd.GeoDataFrame:
    # rglob handles both flat and nested GML subdirectory layouts
    candidates = list((SHELTER_RAW_DIR / f"P20-12_{pref_code}").rglob(f"P20-12_{pref_code}.shp"))
    if not candidates:
        raise FileNotFoundError(f"P20-12_{pref_code}.shp not found under {SHELTER_RAW_DIR}")
    shp_path = candidates[0]

    try:
        gdf = gpd.read_file(shp_path, encoding="shift_jis")
    except Exception:
        gdf = gpd.read_file(shp_path)

    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326, allow_override=True)
    else:
        gdf = gdf.to_crs(epsg=4326)
    return gdf


def build_shelter_database() -> Dict[str, Any]:
    shelters: List[Dict[str, Any]] = []
    pref_counts: Dict[str, int] = {f"{i:02d}": 0 for i in range(1, 48)}
    disaster_counts = {
        "earthquake": 0,
        "volcano": 0,
        "tsunami": 0,
        "nuclear": 0,
        "flood_wind": 0,
    }
    missing_pref_shp: List[str] = []

    serial = 1
    for i in range(1, 48):
        pref_code = f"{i:02d}"
        try:
            gdf = _read_pref_shelter(pref_code)
        except FileNotFoundError:
            missing_pref_shp.append(pref_code)
            continue

        for _, row in gdf.iterrows():
            geom = row.get("geometry")
            if geom is None or geom.is_empty:
                continue

            point = geom if geom.geom_type == "Point" else geom.representative_point()
            city_code = _safe_text(row.get("P20_001"))

            item = {
                "id": f"shelter_{serial:06d}",
                "name": _safe_text(row.get("P20_002")),
                "address": _safe_text(row.get("P20_003")),
                "city_code": city_code,
                "pref_code": city_code[:2].zfill(2),
                "lat": float(point.y),
                "lon": float(point.x),
                "facility_type": _safe_text(row.get("P20_004")),
                "capacity": _safe_capacity(row.get("P20_006")),
                "disaster_types": {
                    "earthquake": _as_bool_flag(row.get("P20_007")),
                    "volcano": _as_bool_flag(row.get("P20_008")),
                    "tsunami": _as_bool_flag(row.get("P20_009")),
                    "nuclear": _as_bool_flag(row.get("P20_010")),
                    "flood_wind": _as_bool_flag(row.get("P20_012")),
                },
            }
            shelters.append(item)
            pref_counts[item["pref_code"]] = pref_counts.get(item["pref_code"], 0) + 1
            for d_type, enabled in item["disaster_types"].items():
                if enabled:
                    disaster_counts[d_type] += 1
            serial += 1

    SHELTER_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    SHELTER_JSON_PATH.write_text(
        json.dumps(shelters, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    stats = {
        "total_count": len(shelters),
        "pref_counts": pref_counts,
        "disaster_type_counts": disaster_counts,
        "missing_pref_shp": missing_pref_shp,
    }
    SHELTER_STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    return stats


def load_shelters() -> List[Dict[str, Any]]:
    if not SHELTER_JSON_PATH.exists():
        build_shelter_database()
    return json.loads(SHELTER_JSON_PATH.read_text(encoding="utf-8"))


def find_nearest_evacuation(
    lat: float, lon: float, disaster_type: str, max_results: int = 3
) -> List[Dict[str, Any]]:
    shelters = load_shelters()

    if disaster_type not in {"earthquake", "volcano", "tsunami", "nuclear", "flood_wind", "flood"}:
        return []
    filter_key = "flood_wind" if disaster_type == "flood" else disaster_type

    candidates: List[Dict[str, Any]] = []
    for shelter in shelters:
        flags = shelter.get("disaster_types", {})
        if not bool(flags.get(filter_key, False)):
            continue

        dist = haversine_m(lat, lon, shelter["lat"], shelter["lon"])
        candidate = {
            **shelter,
            "_dist_m": dist,
            "_score": dist,
        }
        candidates.append(candidate)

    if not candidates:
        return []

    if disaster_type == "tsunami":
        # Avoid mass API calls; evaluate elevation-weighted score only on nearby pool.
        candidates.sort(key=lambda x: x["_dist_m"])
        pool_size = min(len(candidates), max(max_results * 30, 100))
        eval_pool = candidates[:pool_size]
        for c in eval_pool:
            cache_key = f"{c['lat']:.6f},{c['lon']:.6f}"
            elev = _ELEVATION_CACHE.get(cache_key)
            if elev is None:
                elev = get_elevation(c["lat"], c["lon"])
                _ELEVATION_CACHE[cache_key] = elev
            c["elevation_m"] = elev
            c["_score"] = c["_dist_m"] if elev <= 0 else (c["_dist_m"] * 0.7 - elev * 50)
        eval_pool.sort(key=lambda x: (x["_score"], x["_dist_m"]))
        return eval_pool[:max_results]

    candidates.sort(key=lambda x: x["_dist_m"])
    return candidates[:max_results]


def _print_top3_pref(pref_counts: Dict[str, int]) -> None:
    top3 = sorted(pref_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    print("県別トップ3:", "/".join([f"{k}:{v}" for k, v in top3]))


def _run_main_tests() -> None:
    print("[Layer1] Building shelter database...")
    stats = build_shelter_database()
    print(f"総施設数: {stats['total_count']}")
    _print_top3_pref(stats["pref_counts"])
    print("災害種別対応:", stats["disaster_type_counts"])
    if stats.get("missing_pref_shp"):
        print("欠損SHP:", stats["missing_pref_shp"])

    print("\n[Layer1] Elevation API test (3 cities)")
    city_points = [
        ("Tokyo", 35.6812, 139.7671),
        ("Osaka", 34.6937, 135.5023),
        ("Sendai", 38.2682, 140.8694),
    ]
    for name, c_lat, c_lon in city_points:
        try:
            elev = get_elevation(c_lat, c_lon)
            print(f"{name}: {elev:.1f}m")
        except Exception as exc:
            print(f"{name}: 取得失敗 ({exc})")

    print("\n[Layer1] nearest shelters from Tokyo Station")
    eq = find_nearest_evacuation(35.6812, 139.7671, "earthquake", 3)
    tsu = find_nearest_evacuation(35.6812, 139.7671, "tsunami", 3)
    print("earthquake:", [x.get("name", "") for x in eq])
    print("tsunami:", [x.get("name", "") for x in tsu])


if __name__ == "__main__":
    _run_main_tests()
