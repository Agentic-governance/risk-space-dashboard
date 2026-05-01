#!/usr/bin/env python3
"""
Safe Haven Data Collector — Tasks 1-4: Police, Fire, Hospital, AED
Downloads per-prefecture KSJ data + OSM Overpass + gov scrapers.
"""

import json, os, sys, time, tempfile, zipfile, io, traceback
import requests
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup

# ---------- paths ----------
BASE = Path(__file__).resolve().parent.parent / "data" / "safe_haven"
POLICE_DIR = BASE / "police"
FIRE_DIR   = BASE / "fire"
HOSP_DIR   = BASE / "hospital"
AED_DIR    = BASE / "aed"

for d in [POLICE_DIR, FIRE_DIR, HOSP_DIR, AED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "RiskSpaceMCP/1.0 (research project)"}
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
PREFS = [f"{i:02d}" for i in range(1, 48)]

summary = {}

# ================================================================
# Helpers
# ================================================================

def rec(lat, lon, name, typ, is_24h, safety_score, source):
    return {
        "lat": round(float(lat), 6) if lat is not None else None,
        "lon": round(float(lon), 6) if lon is not None else None,
        "name": str(name) if name else "",
        "type": typ,
        "is_24h": is_24h,
        "safety_score": safety_score,
        "source": source,
    }

def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  -> Saved {len(data)} records to {path}")

def overpass_query(query_body, timeout=180):
    """Run Overpass query and return elements list."""
    q = f"[out:json][timeout:{timeout}];\n(\n{query_body}\n);\nout center;"
    for attempt in range(3):
        try:
            r = requests.post(OVERPASS_URL, data={"data": q}, timeout=timeout+60, headers=HEADERS)
            r.raise_for_status()
            return r.json().get("elements", [])
        except Exception as e:
            print(f"  Overpass attempt {attempt+1} failed: {e}")
            if attempt < 2:
                wait = 30 * (attempt + 1)
                print(f"  Waiting {wait}s before retry...")
                time.sleep(wait)
    return []

def download_ksj_all_prefs(code, year):
    """Download KSJ per-prefecture ZIPs, read GML/shp, return combined GeoDataFrame."""
    import geopandas as gpd
    gdfs = []
    for pref in PREFS:
        url = f"https://nlftp.mlit.go.jp/ksj/gml/data/{code}/{code}-{year}/{code}-{year}_{pref}_GML.zip"
        try:
            r = requests.get(url, timeout=60, headers=HEADERS)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            tmpdir = tempfile.mkdtemp()
            with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                zf.extractall(tmpdir)
            # Find readable file: try shp first, then geojson, then gml
            shp = list(Path(tmpdir).rglob("*.shp"))
            gjson = list(Path(tmpdir).rglob("*.geojson"))
            gml = [f for f in Path(tmpdir).rglob("*.gml") if "meta" not in f.name.lower()]
            target = None
            if shp:
                target = str(shp[0])
            elif gjson:
                target = str(gjson[0])
            elif gml:
                target = str(gml[0])
            if target:
                gdf = gpd.read_file(target)
                if gdf.crs and gdf.crs.to_epsg() != 4326:
                    gdf = gdf.to_crs(epsg=4326)
                gdfs.append(gdf)
        except Exception as e:
            print(f"    Pref {pref} failed: {e}")
        # Be polite to the server
        time.sleep(0.3)
    if gdfs:
        combined = pd.concat(gdfs, ignore_index=True)
        # Re-wrap as GeoDataFrame
        combined = gpd.GeoDataFrame(combined, geometry="geometry", crs="EPSG:4326")
        print(f"  KSJ {code}: {len(combined)} features from {len(gdfs)}/47 prefectures")
        return combined
    return None

# ================================================================
# Task 1: Police stations
# ================================================================

def task1_police():
    print("\n" + "="*60)
    print("TASK 1: Police stations (交番・派出所)")
    print("="*60)
    ksj_records = []

    # 1a. KSJ P18 — per prefecture
    try:
        print("  Downloading KSJ P18 per prefecture ...")
        gdf = download_ksj_all_prefs("P18", "12")
        if gdf is not None:
            cols = list(gdf.columns)
            print(f"  Columns: {cols}")
            for _, row in gdf.iterrows():
                geom = row.geometry
                if geom is None:
                    continue
                lat = geom.centroid.y
                lon = geom.centroid.x
                name = ""
                for col in ["P18_003", "P18_002", "P18_001", "name", "名称"]:
                    if col in row.index and pd.notna(row[col]):
                        name = str(row[col])
                        break
                ptype = "police_station"
                for col in ["P18_004", "P18_002", "P18_001"]:
                    if col in row.index and pd.notna(row[col]):
                        val = str(row[col])
                        if "交番" in val:
                            ptype = "koban"
                        elif "派出所" in val or "駐在所" in val:
                            ptype = "hashutsujo"
                        break
                ksj_records.append(rec(lat, lon, name, ptype, True, 0.9, "ksj_p18"))
            save_json(ksj_records, POLICE_DIR / "police_ksj.json")
    except Exception as e:
        print(f"  KSJ P18 failed: {e}")
        traceback.print_exc()

    all_records = list(ksj_records)

    # 1b. OSM
    try:
        print("  Querying OSM Overpass for police ...")
        elems = overpass_query(
            'node["amenity"="police"](20.08228,122.5607,45.70648,154.4709);\n'
            'way["amenity"="police"](20.08228,122.5607,45.70648,154.4709);'
        )
        osm_records = []
        for el in elems:
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            if not lat or not lon:
                continue
            tags = el.get("tags", {})
            name = tags.get("name", tags.get("name:ja", ""))
            ptype = "police_station"
            if "交番" in name or tags.get("police", "") == "koban":
                ptype = "koban"
            osm_records.append(rec(lat, lon, name, ptype, True, 0.85, "osm"))
        save_json(osm_records, POLICE_DIR / "police_osm.json")
        all_records.extend(osm_records)
    except Exception as e:
        print(f"  OSM police failed: {e}")
        traceback.print_exc()

    summary["police"] = len(all_records)
    print(f"  Total police: {len(all_records)}")

# ================================================================
# Task 2: Fire stations
# ================================================================

def task2_fire():
    print("\n" + "="*60)
    print("TASK 2: Fire stations (消防署)")
    print("="*60)
    all_records = []

    try:
        print("  Downloading KSJ P17 per prefecture ...")
        gdf = download_ksj_all_prefs("P17", "12")
        if gdf is not None:
            cols = list(gdf.columns)
            print(f"  Columns: {cols}")
            for _, row in gdf.iterrows():
                geom = row.geometry
                if geom is None:
                    continue
                lat = geom.centroid.y
                lon = geom.centroid.x
                name = ""
                for col in ["P17_003", "P17_002", "P17_001", "name", "名称"]:
                    if col in row.index and pd.notna(row[col]):
                        name = str(row[col])
                        break
                all_records.append(rec(lat, lon, name, "fire_station", True, 0.9, "ksj_p17"))
            save_json(all_records, FIRE_DIR / "fire_ksj.json")
    except Exception as e:
        print(f"  KSJ P17 failed: {e}")
        traceback.print_exc()

    summary["fire"] = len(all_records)
    print(f"  Total fire: {len(all_records)}")

# ================================================================
# Task 3: Hospitals
# ================================================================

def task3_hospitals():
    print("\n" + "="*60)
    print("TASK 3: Hospitals (救急病院)")
    print("="*60)
    all_records = []

    # 3a. 厚労省 救命救急センター
    try:
        print("  Scraping 厚労省 救命救急センター ...")
        r = requests.get("https://www.mhlw.go.jp/stf/newpage_32614.html", timeout=30, headers=HEADERS)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")
        tables = soup.find_all("table")
        mhlw_count = 0
        for table in tables:
            rows = table.find_all("tr")
            for tr in rows[1:]:
                cells = tr.find_all(["td", "th"])
                if len(cells) >= 2:
                    name = cells[-1].get_text(strip=True)
                    if not name:
                        continue
                    all_records.append(rec(None, None, name, "emergency_center", True, 0.95, "mhlw"))
                    mhlw_count += 1
        print(f"  MHLW scraped: {mhlw_count} emergency centers")
    except Exception as e:
        print(f"  MHLW scrape failed: {e}")
        traceback.print_exc()

    # 3b. Tokyo CSV — try multiple URL patterns
    for csv_url in [
        "https://www.hokeniryo.metro.tokyo.lg.jp/iryo/kyuukyuu/kyukyu_shinryo/kyuukyuuitiran.files/kyukyumeibo050201.csv",
        "https://www.hokeniryo.metro.tokyo.lg.jp/iryo/kyuukyuu/kyukyu_shinryo/kyuukyuuitiran.files/kyukyumeibo060401.csv",
        "https://www.hokeniryo.metro.tokyo.lg.jp/iryo/kyuukyuu/kyukyu_shinryo/kyuukyuuitiran.files/kyukyumeibo.csv",
    ]:
        try:
            print(f"  Trying Tokyo CSV: {csv_url.split('/')[-1]} ...")
            r = requests.get(csv_url, timeout=30, headers=HEADERS)
            if r.status_code == 404:
                print(f"    404 — skipping")
                continue
            r.raise_for_status()
            import chardet
            detected = chardet.detect(r.content)
            encoding = detected.get("encoding", "shift_jis")
            df = pd.read_csv(io.BytesIO(r.content), encoding=encoding, on_bad_lines="skip")
            print(f"  Tokyo CSV columns: {list(df.columns)}")
            tokyo_count = 0
            for _, row in df.iterrows():
                name = ""
                for col in df.columns:
                    cl = str(col)
                    if "名" in cl or "name" in cl.lower() or "病院" in cl:
                        if pd.notna(row[col]):
                            name = str(row[col])
                            break
                if not name:
                    name = str(row.iloc[0]) if pd.notna(row.iloc[0]) else ""
                all_records.append(rec(None, None, name, "emergency_hospital_tokyo", True, 0.9, "tokyo_metro"))
                tokyo_count += 1
            print(f"  Tokyo CSV: {tokyo_count} hospitals")
            break  # success
        except Exception as e:
            print(f"  Tokyo CSV failed: {e}")

    # 3c. OSM hospitals
    try:
        print("  Querying OSM Overpass for hospitals ...")
        elems = overpass_query(
            'node["amenity"="hospital"](20.08228,122.5607,45.70648,154.4709);\n'
            'way["amenity"="hospital"](20.08228,122.5607,45.70648,154.4709);',
            timeout=180
        )
        osm_count = 0
        for el in elems:
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            if not lat or not lon:
                continue
            tags = el.get("tags", {})
            name = tags.get("name", tags.get("name:ja", ""))
            is_emergency = tags.get("emergency", "") == "yes"
            all_records.append(rec(lat, lon, name, "hospital", is_emergency, 0.85 if is_emergency else 0.7, "osm"))
            osm_count += 1
        print(f"  OSM hospitals: {osm_count}")
    except Exception as e:
        print(f"  OSM hospitals failed: {e}")
        traceback.print_exc()

    save_json(all_records, HOSP_DIR / "hospitals_all.json")
    summary["hospital"] = len(all_records)
    print(f"  Total hospitals: {len(all_records)}")

# ================================================================
# Task 4: AED
# ================================================================

def task4_aed():
    print("\n" + "="*60)
    print("TASK 4: AED (自動体外式除細動器)")
    print("="*60)
    all_records = []

    # 4a. BODIK CKAN API
    try:
        print("  Querying BODIK CKAN for AED datasets ...")
        r = requests.get(
            "https://data.bodik.jp/api/3/action/package_search",
            params={"q": "AED", "rows": 50},
            timeout=30, headers=HEADERS
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("result", {}).get("results", [])
        print(f"  BODIK found {len(results)} AED datasets")
        bodik_count = 0
        for pkg in results:
            for resource in pkg.get("resources", []):
                fmt = resource.get("format", "").upper()
                if fmt in ["CSV", "GEOJSON", "JSON"]:
                    res_url = resource.get("url", "")
                    if not res_url:
                        continue
                    try:
                        rr = requests.get(res_url, timeout=30, headers=HEADERS)
                        rr.raise_for_status()
                        if fmt == "CSV":
                            import chardet
                            detected = chardet.detect(rr.content)
                            enc = detected.get("encoding", "utf-8")
                            df = pd.read_csv(io.BytesIO(rr.content), encoding=enc, on_bad_lines="skip")
                            lat_col = lon_col = name_col = None
                            for c in df.columns:
                                cl = str(c).lower()
                                if "緯度" in cl or "lat" in cl:
                                    lat_col = c
                                elif "経度" in cl or "lon" in cl or "lng" in cl:
                                    lon_col = c
                                elif "名" in cl or "name" in cl or "施設" in cl or "設置場所" in cl:
                                    name_col = c
                            if lat_col and lon_col:
                                for _, row in df.iterrows():
                                    try:
                                        lat = float(row[lat_col])
                                        lon = float(row[lon_col])
                                    except (ValueError, TypeError):
                                        continue
                                    name = str(row[name_col]) if name_col and pd.notna(row.get(name_col)) else ""
                                    all_records.append(rec(lat, lon, name, "aed", False, 0.6, "bodik"))
                                    bodik_count += 1
                        elif fmt in ["GEOJSON", "JSON"]:
                            jdata = rr.json()
                            features = jdata.get("features", []) if "features" in jdata else (jdata if isinstance(jdata, list) else [])
                            for feat in features:
                                props = feat.get("properties", {})
                                geom = feat.get("geometry", {})
                                coords = geom.get("coordinates", [])
                                if len(coords) >= 2:
                                    lon, lat = coords[0], coords[1]
                                    name = props.get("name", props.get("名称", props.get("施設名", "")))
                                    all_records.append(rec(lat, lon, name, "aed", False, 0.6, "bodik"))
                                    bodik_count += 1
                    except Exception:
                        pass
                    if bodik_count > 10000:
                        break
            if bodik_count > 10000:
                break
        print(f"  BODIK AED records: {bodik_count}")
    except Exception as e:
        print(f"  BODIK failed: {e}")
        traceback.print_exc()

    # 4b. OSM AED
    try:
        print("  Querying OSM Overpass for AED ...")
        q = '[out:json][timeout:180];\nnode["emergency"="defibrillator"](20.08228,122.5607,45.70648,154.4709);\nout body;'
        for attempt in range(3):
            try:
                r = requests.post(OVERPASS_URL, data={"data": q}, timeout=240, headers=HEADERS)
                r.raise_for_status()
                elems = r.json().get("elements", [])
                osm_count = 0
                for el in elems:
                    lat = el.get("lat")
                    lon = el.get("lon")
                    if not lat or not lon:
                        continue
                    tags = el.get("tags", {})
                    name = tags.get("name", tags.get("description", tags.get("operator", "")))
                    is_24h = tags.get("opening_hours", "") == "24/7"
                    all_records.append(rec(lat, lon, name, "aed", is_24h, 0.6, "osm"))
                    osm_count += 1
                print(f"  OSM AED: {osm_count}")
                break
            except Exception as e:
                print(f"  OSM AED attempt {attempt+1} failed: {e}")
                if attempt < 2:
                    time.sleep(30 * (attempt + 1))
    except Exception as e:
        print(f"  OSM AED failed: {e}")
        traceback.print_exc()

    save_json(all_records, AED_DIR / "aed_osm.json")
    summary["aed"] = len(all_records)
    print(f"  Total AED: {len(all_records)}")

# ================================================================
# Main
# ================================================================

if __name__ == "__main__":
    print("Safe Haven Data Collection")
    print("=" * 60)

    task1_police()
    task2_fire()
    task3_hospitals()
    task4_aed()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total = 0
    for cat, count in summary.items():
        print(f"  {cat:20s}: {count:>8,}")
        total += count
    print(f"  {'TOTAL':20s}: {total:>8,}")
    print("=" * 60)
    print("Done.")
