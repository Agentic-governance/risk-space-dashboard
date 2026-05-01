#!/usr/bin/env python3
"""
fetch_historical_traffic.py — NPA Historical Traffic Accident Data Fetcher
===========================================================================
Downloads and aggregates historical traffic accident CSV data from the
National Police Agency (警察庁) open data portal for years 2020-2024.

Primary source:
  NPA Open Data: https://www.npa.go.jp/publications/statistics/koutsuu/opendata/
  - 本票 (honhyo): main accident record CSV
  - 補充票 (hojuhyo): supplementary record CSV

e-Stat alternative (requires ESTAT_APP_ID env var):
  https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData

Output:
  data/historical/traffic_accidents_2020_2024.json

Usage:
    python scripts/fetch_historical_traffic.py [--years 2020 2021 2022 2023 2024]
    ESTAT_APP_ID=xxx python scripts/fetch_historical_traffic.py  # enable e-Stat fallback
"""

import csv
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from io import StringIO
from typing import Dict, List, Optional, Tuple

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "data", "historical")
OUT_PATH = os.path.join(OUT_DIR, "traffic_accidents_2020_2024.json")
CACHE_DIR = os.path.join(OUT_DIR, "cache")

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

# ── Constants ──────────────────────────────────────────────────────────────
TARGET_YEARS = [2020, 2021, 2022, 2023, 2024]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en;q=0.9",
}

# SSL context — many Japanese govt sites have cert issues
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# Prefecture code → name mapping (都道府県コード JIS X 0401)
PREF_CODE_MAP = {
    "01": "北海道", "02": "青森県", "03": "岩手県", "04": "宮城県",
    "05": "秋田県", "06": "山形県", "07": "福島県", "08": "茨城県",
    "09": "栃木県", "10": "群馬県", "11": "埼玉県", "12": "千葉県",
    "13": "東京都", "14": "神奈川県", "15": "新潟県", "16": "富山県",
    "17": "石川県", "18": "福井県", "19": "山梨県", "20": "長野県",
    "21": "岐阜県", "22": "静岡県", "23": "愛知県", "24": "三重県",
    "25": "滋賀県", "26": "京都府", "27": "大阪府", "28": "兵庫県",
    "29": "奈良県", "30": "和歌山県", "31": "鳥取県", "32": "島根県",
    "33": "岡山県", "34": "広島県", "35": "山口県", "36": "徳島県",
    "37": "香川県", "38": "愛媛県", "39": "高知県", "40": "福岡県",
    "41": "佐賀県", "42": "長崎県", "43": "熊本県", "44": "大分県",
    "45": "宮崎県", "46": "鹿児島県", "47": "沖縄県",
}

# Accident type code mapping (事故類型コード)
ACCIDENT_TYPE_MAP = {
    "1": "人対車両", "2": "車両相互", "3": "車両単独",
    "11": "横断中", "12": "横断中以外の通行中", "13": "路上遊戯中等",
    "14": "路上作業中等", "15": "その他",
    "21": "追突", "22": "正面衝突", "23": "路外逸脱",
    "24": "出会い頭衝突", "25": "追越し・追抜き時", "26": "すれ違い時",
    "27": "左折時", "28": "右折時", "29": "その他交差点",
    "31": "工作物衝突", "32": "転落", "33": "転覆",
    "34": "路外逸脱", "35": "その他",
}

# URL patterns to try (NPA has changed URL format across years)
NPA_URL_PATTERNS = [
    # Pattern 1: current standard (2022+)
    "https://www.npa.go.jp/publications/statistics/koutsuu/opendata/{year}/honhyo_{year}.csv",
    # Pattern 2: older style
    "https://www.npa.go.jp/publications/statistics/koutsuu/opendata/{year}/honpyo_{year}.csv",
    # Pattern 3: zip archive
    "https://www.npa.go.jp/publications/statistics/koutsuu/opendata/{year}/honhyo_{year}.zip",
    # Pattern 4: index-based discovery
    "https://www.npa.go.jp/publications/statistics/koutsuu/opendata/{year}/",
]

# e-Stat stats IDs for traffic accident data
ESTAT_STATS_IDS = [
    "0003287847",  # 交通事故統計 (primary)
    "0003224087",  # 交通事故発生状況
]

# ── HTTP helpers ───────────────────────────────────────────────────────────

def fetch_bytes(url: str, retries: int = 3, timeout: int = 60) -> Optional[bytes]:
    """Fetch raw bytes from URL with exponential-backoff retry. Returns None on 404."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
                data = resp.read()
                print(f"  [OK] {url} ({len(data):,} bytes)")
                return data
        except urllib.error.HTTPError as e:
            print(f"  [HTTP {e.code}] {url}", file=sys.stderr)
            if e.code == 404:
                return None  # don't retry 404
            if attempt < retries - 1:
                wait = 2 ** attempt
                print(f"  [RETRY] waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
        except urllib.error.URLError as e:
            print(f"  [URLError] {url}: {e}", file=sys.stderr)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
        except Exception as e:
            print(f"  [ERROR] {url}: {e}", file=sys.stderr)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None


def is_html(data: bytes) -> bool:
    """Return True if the response looks like HTML rather than CSV."""
    try:
        sniff = data[:500].decode("utf-8", errors="ignore").lower()
    except Exception:
        sniff = ""
    return "<html" in sniff or "<!doctype" in sniff or "<head" in sniff


def decode_csv(data: bytes) -> Optional[str]:
    """Try multiple encodings to decode CSV bytes. Returns decoded string or None."""
    for enc in ("shift_jis", "cp932", "utf-8-sig", "utf-8", "euc-jp"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    print("  [WARN] Could not decode CSV with any known encoding", file=sys.stderr)
    return None

# ── NPA index scraper ─────────────────────────────────────────────────────

def discover_csv_urls_from_index(year: int) -> list[str]:
    """
    Scrape the NPA open data index page for a given year to discover
    actual CSV download links. Returns a list of candidate URLs.
    """
    index_url = f"https://www.npa.go.jp/publications/statistics/koutsuu/opendata/{year}/"
    data = fetch_bytes(index_url, retries=2, timeout=20)
    if not data or is_html(data) is False:
        # If not HTML, it may be a directory listing (Apache)
        pass
    if not data:
        # Try the parent page
        data = fetch_bytes(
            "https://www.npa.go.jp/publications/statistics/koutsuu/opendata/index.html",
            retries=2, timeout=20,
        )

    if not data:
        return []

    text = data.decode("utf-8", errors="ignore")
    # Find href links ending in .csv or .zip containing the year
    pattern = rf'href="([^"]*{year}[^"]*\.(?:csv|zip))"'
    found = re.findall(pattern, text, re.IGNORECASE)
    urls = []
    for href in found:
        if href.startswith("http"):
            urls.append(href)
        elif href.startswith("/"):
            urls.append(f"https://www.npa.go.jp{href}")
        else:
            urls.append(f"https://www.npa.go.jp/publications/statistics/koutsuu/opendata/{year}/{href}")
    return list(dict.fromkeys(urls))  # deduplicate, preserve order


# ── CSV parsing ───────────────────────────────────────────────────────────

# Known column name variants across NPA CSV versions
FIELD_ALIASES = {
    "pref_code": ["都道府県コード", "都道府県CD", "prefcode", "都道府県"],
    "city_code": ["市区町村コード", "市区町村CD", "citycode"],
    "accident_type": ["事故類型コード", "事故類型", "事故の類型"],
    "fatalities": ["死者数", "死亡者数", "死者"],
    "injuries": ["負傷者数", "負傷者", "けが人数"],
    "year": ["発生年", "年"],
    "month": ["発生月", "月"],
    "day": ["発生日", "日"],
    "hour": ["発生時", "時"],
    "lat": ["緯度", "lat", "latitude"],
    "lon": ["経度", "lon", "longitude", "lng"],
    "road_route": ["路線コード", "路線", "道路"],
    "weather": ["天候", "天候コード"],
    "surface_condition": ["路面状態", "路面状態コード"],
}


def resolve_column(headers: List[str], aliases: List[str]) -> Optional[str]:
    """Find the first header that matches any alias (case-insensitive)."""
    headers_lower = [h.strip().lower() for h in headers]
    for alias in aliases:
        alias_lower = alias.lower()
        if alias_lower in headers_lower:
            return headers[headers_lower.index(alias_lower)]
    return None


def parse_honhyo_csv(text: str, year: int) -> list[dict]:
    """
    Parse NPA 本票 CSV text into a list of accident record dicts.
    Handles column name variations between years.

    Returns list of records with normalized fields.
    """
    reader = csv.DictReader(StringIO(text))
    headers = reader.fieldnames or []
    if not headers:
        print(f"  [WARN] No headers found in CSV for {year}", file=sys.stderr)
        return []

    print(f"  Columns ({len(headers)}): {headers[:10]}{'...' if len(headers) > 10 else ''}")

    # Resolve column names
    col = {field: resolve_column(list(headers), aliases)
           for field, aliases in FIELD_ALIASES.items()}

    records = []
    skipped = 0
    for row_num, row in enumerate(reader, start=2):
        try:
            # Date construction
            yr = int(row.get(col["year"], year) or year)
            mo = row.get(col["month"], "")
            da = row.get(col["day"], "")
            hr = row.get(col["hour"], "0")

            # Normalise month/day
            try:
                mo_int = int(mo) if mo else 0
                da_int = int(da) if da else 0
            except ValueError:
                mo_int, da_int = 0, 0

            date_str = (
                f"{yr:04d}-{mo_int:02d}-{da_int:02d}"
                if mo_int and da_int
                else f"{yr:04d}-00-00"
            )

            # Prefecture
            pref_raw = row.get(col["pref_code"], "") if col["pref_code"] else ""
            pref_code = str(pref_raw).strip().zfill(2)[:2] if pref_raw else ""
            pref_name = PREF_CODE_MAP.get(pref_code, pref_raw)

            # City code
            city_code = str(row.get(col["city_code"], "") or "").strip()

            # Accident type
            acc_type_code = str(row.get(col["accident_type"], "") or "").strip()
            acc_type_name = ACCIDENT_TYPE_MAP.get(acc_type_code, acc_type_code)

            # Casualties
            def safe_int(val: str) -> int:
                try:
                    return max(0, int(str(val).strip() or "0"))
                except (ValueError, TypeError):
                    return 0

            fatalities = safe_int(row.get(col["fatalities"], 0) if col["fatalities"] else 0)
            injuries = safe_int(row.get(col["injuries"], 0) if col["injuries"] else 0)

            # Coordinates (may not be present in all years)
            lat, lon = None, None
            if col["lat"] and col["lon"]:
                try:
                    lat_raw = str(row.get(col["lat"], "")).strip()
                    lon_raw = str(row.get(col["lon"], "")).strip()
                    if lat_raw and lon_raw:
                        lat = float(lat_raw)
                        lon = float(lon_raw)
                        # Sanity-check: Japan bounding box
                        if not (20.0 <= lat <= 46.0 and 122.0 <= lon <= 154.0):
                            lat, lon = None, None
                except (ValueError, TypeError):
                    pass

            records.append({
                "date": date_str,
                "year": yr,
                "month": mo_int,
                "prefecture_code": pref_code,
                "prefecture": pref_name,
                "city_code": city_code,
                "accident_type_code": acc_type_code,
                "accident_type": acc_type_name,
                "fatalities": fatalities,
                "injuries": injuries,
                "lat": lat,
                "lon": lon,
            })
        except Exception as e:
            skipped += 1
            if skipped <= 5:
                print(f"  [WARN] Row {row_num} parse error: {e}", file=sys.stderr)

    print(f"  Parsed {len(records):,} records (skipped {skipped})")
    return records


# ── Aggregation ───────────────────────────────────────────────────────────

def aggregate(records: list[dict]) -> dict:
    """
    Aggregate raw records by prefecture+month.
    Returns dict structured for JSON output.
    """
    # By prefecture+month
    by_pref_month: dict[str, dict] = defaultdict(lambda: {
        "accidents": 0, "fatalities": 0, "injuries": 0,
    })
    # By prefecture+year
    by_pref_year: dict[str, dict] = defaultdict(lambda: {
        "accidents": 0, "fatalities": 0, "injuries": 0,
    })
    # By accident type
    by_type: dict[str, dict] = defaultdict(lambda: {
        "accidents": 0, "fatalities": 0, "injuries": 0,
    })
    # By year (national totals)
    by_year: dict[str, dict] = defaultdict(lambda: {
        "accidents": 0, "fatalities": 0, "injuries": 0,
    })

    total_accidents = 0
    total_fatalities = 0
    total_injuries = 0

    for r in records:
        pref = r["prefecture"] or "不明"
        year = r["year"]
        month = r["month"]
        acc_type = r["accident_type"] or "不明"
        fat = r["fatalities"]
        inj = r["injuries"]

        key_pm = f"{pref}|{year:04d}-{month:02d}"
        key_py = f"{pref}|{year:04d}"
        key_y = str(year)

        by_pref_month[key_pm]["accidents"] += 1
        by_pref_month[key_pm]["fatalities"] += fat
        by_pref_month[key_pm]["injuries"] += inj

        by_pref_year[key_py]["accidents"] += 1
        by_pref_year[key_py]["fatalities"] += fat
        by_pref_year[key_py]["injuries"] += inj

        by_type[acc_type]["accidents"] += 1
        by_type[acc_type]["fatalities"] += fat
        by_type[acc_type]["injuries"] += inj

        by_year[key_y]["accidents"] += 1
        by_year[key_y]["fatalities"] += fat
        by_year[key_y]["injuries"] += inj

        total_accidents += 1
        total_fatalities += fat
        total_injuries += inj

    # Convert defaultdicts to plain dicts and reshape
    pref_month_list = []
    for key, vals in sorted(by_pref_month.items()):
        pref, ym = key.split("|", 1)
        y, m = ym.split("-")
        pref_month_list.append({
            "prefecture": pref,
            "year": int(y),
            "month": int(m),
            **vals,
        })

    pref_year_list = []
    for key, vals in sorted(by_pref_year.items()):
        pref, y = key.split("|", 1)
        pref_year_list.append({"prefecture": pref, "year": int(y), **vals})

    by_year_flat = {k: v for k, v in sorted(by_year.items())}

    return {
        "totals": {
            "accidents": total_accidents,
            "fatalities": total_fatalities,
            "injuries": total_injuries,
        },
        "by_year": by_year_flat,
        "by_prefecture_month": pref_month_list,
        "by_prefecture_year": pref_year_list,
        "by_accident_type": dict(sorted(by_type.items(), key=lambda x: -x[1]["accidents"])),
    }


# ── NPA download ──────────────────────────────────────────────────────────

def download_npa_year(year: int) -> list[dict]:
    """
    Try all known URL patterns for a given year.
    Returns parsed records list (may be empty on failure).
    """
    # Check cache first
    cache_path = os.path.join(CACHE_DIR, f"honhyo_{year}.csv")
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 1000:
        print(f"  [CACHE] Loading {cache_path}")
        with open(cache_path, "rb") as f:
            cached = f.read()
        text = decode_csv(cached)
        if text:
            return parse_honhyo_csv(text, year)

    # Try static URL patterns
    for pattern in NPA_URL_PATTERNS[:-1]:  # last one is the index
        url = pattern.format(year=year)
        print(f"  Trying: {url}")
        data = fetch_bytes(url)
        if data and not is_html(data) and len(data) > 1000:
            # Save to cache
            with open(cache_path, "wb") as f:
                f.write(data)
            text = decode_csv(data)
            if text:
                return parse_honhyo_csv(text, year)
        time.sleep(1)

    # Try index page discovery
    print(f"  Trying index discovery for {year}...")
    discovered = discover_csv_urls_from_index(year)
    for url in discovered:
        if "honhyo" in url.lower() or "honpyo" in url.lower() or "本票" in url:
            print(f"  Discovered URL: {url}")
            data = fetch_bytes(url)
            if data and not is_html(data) and len(data) > 1000:
                with open(cache_path, "wb") as f:
                    f.write(data)
                text = decode_csv(data)
                if text:
                    return parse_honhyo_csv(text, year)
            time.sleep(1)

    print(f"  [FAIL] Could not download data for {year}", file=sys.stderr)
    return []


# ── e-Stat fallback ───────────────────────────────────────────────────────

def fetch_estat_traffic(app_id: str) -> list[dict]:
    """
    Fetch traffic accident statistics from e-Stat API.
    Returns a flat list of records (prefecture × year level).
    Requires ESTAT_APP_ID environment variable.
    """
    print("\n[e-Stat] Fetching traffic accident data via API...")
    records = []

    for stats_id in ESTAT_STATS_IDS:
        params = urllib.parse.urlencode({
            "appId": app_id,
            "statsDataId": stats_id,
            "lang": "J",
            "metaGetFlg": "Y",
            "cntGetFlg": "N",
            "explanationGetFlg": "Y",
            "annotationGetFlg": "Y",
            "sectionHeaderFlg": "1",
            "replaceSpChars": "0",
        })
        url = f"https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData?{params}"
        print(f"  Trying stats ID: {stats_id}")

        data = fetch_bytes(url, retries=2, timeout=30)
        if not data:
            continue

        try:
            payload = json.loads(data.decode("utf-8"))
        except json.JSONDecodeError as e:
            print(f"  [WARN] e-Stat JSON parse error: {e}", file=sys.stderr)
            continue

        # Navigate e-Stat response structure
        # GET_STATS_DATA > STATISTICAL_DATA > DATA_INF > VALUE
        try:
            stat_data = payload["GET_STATS_DATA"]["STATISTICAL_DATA"]
            class_info = stat_data["CLASS_INF"]["CLASS_OBJ"]
            data_inf = stat_data["DATA_INF"]["VALUE"]
        except (KeyError, TypeError) as e:
            print(f"  [WARN] e-Stat response structure unexpected: {e}", file=sys.stderr)
            continue

        # Build code→label maps from CLASS_OBJ
        code_maps: dict[str, dict[str, str]] = {}
        if isinstance(class_info, dict):
            class_info = [class_info]
        for cls in class_info:
            obj_id = cls.get("@id", "")
            classes = cls.get("CLASS", [])
            if isinstance(classes, dict):
                classes = [classes]
            code_maps[obj_id] = {c["@code"]: c["@name"] for c in classes}

        # Parse VALUE rows
        if isinstance(data_inf, dict):
            data_inf = [data_inf]

        for val in data_inf:
            try:
                count = int(str(val.get("$", "0")).replace(",", "") or "0")
                # Try to extract prefecture and time dimension codes
                pref_code = val.get("@area", val.get("@cat01", ""))
                time_code = val.get("@time", val.get("@cat02", ""))
                # Resolve labels
                pref_name = code_maps.get("area", {}).get(pref_code, pref_code)
                # time_code often like "2022000000" → year = first 4 digits
                year_str = time_code[:4] if len(time_code) >= 4 else ""
                try:
                    year_int = int(year_str)
                except ValueError:
                    year_int = 0

                if year_int < 2015 or year_int > 2025:
                    continue

                records.append({
                    "date": f"{year_int:04d}-00-00",
                    "year": year_int,
                    "month": 0,
                    "prefecture_code": pref_code,
                    "prefecture": pref_name,
                    "city_code": "",
                    "accident_type_code": "",
                    "accident_type": val.get("@cat01", ""),
                    "fatalities": 0,  # e-Stat provides aggregate counts, not individual fatalities
                    "injuries": 0,
                    "lat": None,
                    "lon": None,
                    "_estat_count": count,
                })
            except Exception:
                continue

        print(f"  e-Stat records for {stats_id}: {len(records)}")
        if records:
            break  # stop at first successful stats ID
        time.sleep(1)

    return records


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fetch NPA historical traffic accident data")
    parser.add_argument(
        "--years", nargs="+", type=int, default=TARGET_YEARS,
        help="Years to fetch (default: 2020-2024)",
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Ignore cached CSV files and re-download",
    )
    parser.add_argument(
        "--estat-only", action="store_true",
        help="Use only e-Stat API (requires ESTAT_APP_ID env var)",
    )
    args = parser.parse_args()

    if args.no_cache:
        # Clear cache for requested years
        for year in args.years:
            cache_path = os.path.join(CACHE_DIR, f"honhyo_{year}.csv")
            if os.path.exists(cache_path):
                os.remove(cache_path)
                print(f"[CACHE] Cleared {cache_path}")

    now_utc = datetime.now(timezone.utc)
    print("=" * 60)
    print("fetch_historical_traffic.py — NPA Traffic Accident Fetcher")
    print(f"  Target years: {args.years}")
    print(f"  Run at: {now_utc.isoformat(timespec='seconds')}")
    print(f"  Output: {OUT_PATH}")
    print("=" * 60)

    estat_app_id = os.environ.get("ESTAT_APP_ID", "")
    all_records: list[dict] = []
    source_stats: dict[str, dict] = {}
    failed_years: list[int] = []

    if args.estat_only:
        if not estat_app_id:
            print("[ERROR] --estat-only requires ESTAT_APP_ID env var", file=sys.stderr)
            sys.exit(1)
        all_records = fetch_estat_traffic(estat_app_id)
        source_stats["estat"] = {"records": len(all_records)}
    else:
        # Primary: NPA open data CSVs
        for year in sorted(args.years):
            print(f"\n[NPA] Fetching year {year}...")
            records = download_npa_year(year)
            if records:
                all_records.extend(records)
                source_stats[f"npa_{year}"] = {
                    "records": len(records),
                    "fatalities": sum(r["fatalities"] for r in records),
                    "injuries": sum(r["injuries"] for r in records),
                }
                print(f"  Year {year}: {len(records):,} records")
            else:
                failed_years.append(year)
                source_stats[f"npa_{year}"] = {"records": 0, "status": "failed"}
            time.sleep(2)  # be polite to NPA servers

        # e-Stat fallback for failed years
        if failed_years and estat_app_id:
            print(f"\n[e-Stat] Fallback for failed years: {failed_years}")
            estat_records = fetch_estat_traffic(estat_app_id)
            # Filter to only failed years
            estat_filtered = [r for r in estat_records if r["year"] in failed_years]
            if estat_filtered:
                all_records.extend(estat_filtered)
                source_stats["estat_fallback"] = {
                    "records": len(estat_filtered),
                    "years": failed_years,
                }
                failed_years = [y for y in failed_years
                                if not any(r["year"] == y for r in estat_filtered)]
        elif failed_years and not estat_app_id:
            print(
                f"\n[INFO] {len(failed_years)} year(s) failed to download: {failed_years}",
                file=sys.stderr,
            )
            print(
                "  Set ESTAT_APP_ID env var to enable e-Stat API fallback.",
                file=sys.stderr,
            )

    if not all_records:
        print("\n[ERROR] No records collected. Exiting without writing output.", file=sys.stderr)
        print("  Possible causes:", file=sys.stderr)
        print("  1. NPA has changed URL structure. Check:", file=sys.stderr)
        print("     https://www.npa.go.jp/publications/statistics/koutsuu/opendata/", file=sys.stderr)
        print("  2. Network connectivity issue.", file=sys.stderr)
        print("  3. Set ESTAT_APP_ID and retry (e-Stat fallback).", file=sys.stderr)
        sys.exit(1)

    print(f"\n[AGG] Aggregating {len(all_records):,} total records...")
    agg = aggregate(all_records)

    output = {
        "metadata": {
            "description": (
                "Historical traffic accident statistics for Japan (2020-2024). "
                "Primary source: National Police Agency (警察庁) Open Data. "
                "Aggregated by prefecture and month."
            ),
            "primary_source": "https://www.npa.go.jp/publications/statistics/koutsuu/opendata/",
            "alternative_source": "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData",
            "fetched_at": now_utc.isoformat(timespec="seconds"),
            "years_requested": sorted(args.years),
            "years_failed": sorted(failed_years),
            "total_records": len(all_records),
            "source_breakdown": source_stats,
            "notes": [
                "本票 (honhyo) = main accident record CSV from NPA open data.",
                "URL pattern: https://www.npa.go.jp/publications/statistics/koutsuu/opendata/{year}/honhyo_{year}.csv",
                "Encoding: Shift-JIS (cp932). Lat/lon available in 2022+ data.",
                "Fatality count = 死者数 (deaths within 24h of accident).",
                "e-Stat API requires ESTAT_APP_ID environment variable.",
                "Cache stored in data/historical/cache/ to avoid re-downloading.",
            ],
        },
        "summary": agg["totals"],
        "by_year": agg["by_year"],
        "by_prefecture_year": agg["by_prefecture_year"],
        "by_prefecture_month": agg["by_prefecture_month"],
        "by_accident_type": agg["by_accident_type"],
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[DONE] Written to {OUT_PATH}")
    print(f"  Total records : {len(all_records):,}")
    print(f"  Total accidents: {agg['totals']['accidents']:,}")
    print(f"  Total fatalities: {agg['totals']['fatalities']:,}")
    print(f"  Total injuries : {agg['totals']['injuries']:,}")
    print(f"  Failed years   : {sorted(failed_years) if failed_years else 'none'}")
    print(f"  Pref×month rows: {len(agg['by_prefecture_month']):,}")
    print(f"  Output size    : {os.path.getsize(OUT_PATH):,} bytes")


if __name__ == "__main__":
    main()
