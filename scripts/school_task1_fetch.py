#!/usr/bin/env python3
import json
from pathlib import Path

import geopandas as gpd

SRC_PATH = Path("data/schools/raw/P29-13/P29-13.shp")
OUT_PATH = Path("data/schools/elementary_schools.json")


def main():
    if not SRC_PATH.exists():
        raise FileNotFoundError(f"Missing source shapefile: {SRC_PATH}")

    gdf = gpd.read_file(SRC_PATH, encoding="shift_jis")

    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326, allow_override=True)
    else:
        gdf = gdf.to_crs(epsg=4326)

    for col in ("P29_003", "P29_005", "P29_001", "geometry"):
        if col not in gdf.columns:
            raise KeyError(f"Required column not found: {col}")

    elem = gdf[gdf["P29_003"].astype(str).str.strip() == "16001"].copy()

    schools = []
    for _, row in elem.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        point = geom if geom.geom_type == "Point" else geom.representative_point()
        pref_code = str(row.get("P29_001", "")).strip()[:2].zfill(2)

        schools.append(
            {
                "id": f"elem_{len(schools)+1:05d}",
                "name": str(row.get("P29_005", "")).strip(),
                "lat": float(point.y),
                "lon": float(point.x),
                "pref_code": pref_code,
                "type": "elementary_school",
            }
        )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(schools, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote: {OUT_PATH} ({len(schools)} records)")


if __name__ == "__main__":
    main()
