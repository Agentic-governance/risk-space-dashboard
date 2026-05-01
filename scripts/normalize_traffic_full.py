#!/usr/bin/env python3
"""
Normalize ALL traffic accident records from NPA open data CSVs.
Processes 2019-2024 data into the risk_space standard schema.
"""

import csv
import json
import os
import sys
import uuid
import urllib.request
import urllib.error
from datetime import datetime

BASE_DIR = "/Users/reikumaki/Library/CloudStorage/GoogleDrive-teddykmk@gmail.com/マイドライブ/piracy_detector/claude_code/risk_space"
DATA_DIR = os.path.join(BASE_DIR, "data")
TRAFFIC_DIR = os.path.join(DATA_DIR, "traffic")
NORM_DIR = os.path.join(DATA_DIR, "normalized")

# Prefecture code to name mapping
PREF_CODES = {
    "01": "北海道", "02": "青森県", "03": "岩手県", "04": "宮城県", "05": "秋田県",
    "06": "山形県", "07": "福島県", "08": "茨城県", "09": "栃木県", "10": "群馬県",
    "11": "埼玉県", "12": "千葉県", "13": "東京都", "14": "神奈川県", "15": "新潟県",
    "16": "富山県", "17": "石川県", "18": "福井県", "19": "山梨県", "20": "長野県",
    "21": "岐阜県", "22": "静岡県", "23": "愛知県", "24": "三重県", "25": "滋賀県",
    "26": "京都府", "27": "大阪府", "28": "兵庫県", "29": "奈良県", "30": "和歌山県",
    "31": "鳥取県", "32": "島根県", "33": "岡山県", "34": "広島県", "35": "山口県",
    "36": "徳島県", "37": "香川県", "38": "愛媛県", "39": "高知県", "40": "福岡県",
    "41": "佐賀県", "42": "長崎県", "43": "熊本県", "44": "大分県", "45": "宮崎県",
    "46": "鹿児島県", "47": "沖縄県"
}

# Weather code mapping
WEATHER_CODES = {
    "1": "晴", "2": "曇", "3": "雨", "4": "霧", "5": "雪"
}

# Accident content mapping
ACCIDENT_CONTENT = {
    "1": "collision_fatal",    # 死亡事故
    "2": "collision_injury",   # 負傷事故
}

# Day of week mapping
DOW_MAP = {
    "1": "日", "2": "月", "3": "火", "4": "水", "5": "木", "6": "金", "7": "土"
}


def dms1000_to_decimal(val):
    """Convert DMS*1000 format to decimal degrees."""
    try:
        val = int(val)
        if val == 0:
            return None
        deg = val // 10000000
        min_part = (val % 10000000) // 100000
        sec_frac = (val % 100000) / 1000.0
        return deg + min_part / 60.0 + sec_frac / 3600.0
    except (ValueError, TypeError):
        return None


def severity_from_content(content_code, deaths, injuries):
    """Determine severity 1-5 from accident content."""
    deaths = int(deaths) if deaths and deaths.strip() else 0
    injuries = int(injuries) if injuries and injuries.strip() else 0
    if deaths > 0:
        return 5
    if injuries >= 3:
        return 4
    if injuries >= 1:
        return 2
    return 1


def process_csv(filepath, encoding='cp932'):
    """Generator that yields normalized records from a CSV file."""
    with open(filepath, 'r', encoding=encoding, errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # Build source_id
                pref = row.get('都道府県コード', '').strip()
                police = row.get('警察署等コード', '').strip()
                ticket = row.get('本票番号', '').strip()
                source_id = f"{pref}-{police}-{ticket}"

                # Coordinates
                lat_raw = row.get('地点　緯度（北緯）', '').strip()
                lon_raw = row.get('地点　経度（東経）', '').strip()
                lat = dms1000_to_decimal(lat_raw) if lat_raw else None
                lon = dms1000_to_decimal(lon_raw) if lon_raw else None

                # Date/time
                year = row.get('発生日時　　年', '').strip()
                month = row.get('発生日時　　月', '').strip().zfill(2)
                day = row.get('発生日時　　日', '').strip().zfill(2)
                hour = row.get('発生日時　　時', '').strip().zfill(2)
                minute = row.get('発生日時　　分', '').strip().zfill(2)

                try:
                    occurred_at = f"{year}-{month}-{day}T{hour}:{minute}:00+09:00"
                    # Validate
                    datetime.fromisoformat(occurred_at)
                except (ValueError, TypeError):
                    occurred_at = None

                # Accident type
                content_code = row.get('事故内容', '').strip()
                subtype = ACCIDENT_CONTENT.get(content_code, f"collision_{content_code}")

                # Severity
                deaths = row.get('死者数', '0').strip()
                injuries = row.get('負傷者数', '0').strip()
                sev = severity_from_content(content_code, deaths, injuries)

                # Prefecture
                pref_code = pref.zfill(2)
                pref_name = PREF_CODES.get(pref_code)

                # City code
                city_code = row.get('市区町村コード', '').strip()

                # Weather
                weather_code = row.get('天候', '').strip()
                weather = WEATHER_CODES.get(weather_code)

                # Day of week
                dow_code = row.get('曜日(発生年月日)', '').strip()
                dow = DOW_MAP.get(dow_code)

                # Geometry
                if lat and lon and 20 < lat < 50 and 120 < lon < 155:
                    geometry = {
                        "type": "Point",
                        "coordinates": [round(lon, 6), round(lat, 6)]
                    }
                    geocoded = True
                else:
                    geometry = None
                    geocoded = False

                record = {
                    "id": str(uuid.uuid4()),
                    "source_id": source_id,
                    "layer": "traffic",
                    "subtype": subtype,
                    "geometry": geometry,
                    "admin": {
                        "prefecture": pref_name,
                        "prefecture_code": pref_code,
                        "city": None,
                        "city_code": city_code,
                        "town": None
                    },
                    "spatial_resolution": "point" if geocoded else "unknown",
                    "occurred_at": occurred_at,
                    "published_at": None,
                    "time_resolution": "minute",
                    "realtime": False,
                    "severity": sev,
                    "risk_score": None,
                    "source": {
                        "org": "警察庁",
                        "url": "https://www.npa.go.jp/publications/statistics/koutsuu/opendata/",
                        "license": "政府標準利用規約",
                        "fee": False,
                        "update_freq": "yearly",
                        "missing_rate": 0.02,
                        "geocoded": geocoded
                    },
                    "raw": {
                        "deaths": int(deaths) if deaths else 0,
                        "injuries": int(injuries) if injuries else 0,
                        "weather": weather,
                        "day_of_week": dow,
                        "road_shape": row.get('道路形状', '').strip(),
                        "road_surface": row.get('路面状態', '').strip(),
                        "accident_type_code": row.get('事故類型', '').strip(),
                        "age_a": row.get('年齢（当事者A）', '').strip(),
                        "age_b": row.get('年齢（当事者B）', '').strip(),
                        "party_type_a": row.get('当事者種別（当事者A）', '').strip(),
                        "party_type_b": row.get('当事者種別（当事者B）', '').strip(),
                    }
                }

                yield record

            except Exception as e:
                print(f"  [WARN] Skipping row: {e}", file=sys.stderr)
                continue


def download_csv(year):
    """Try to download CSV for a given year."""
    url = f"https://www.npa.go.jp/publications/statistics/koutsuu/opendata/{year}/honhyo_{year}.csv"
    dest = os.path.join(TRAFFIC_DIR, f"honhyo_{year}.csv")

    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        print(f"  Already exists: {dest} ({os.path.getsize(dest) / 1024 / 1024:.1f} MB)")
        return dest

    # Also check _full variant
    dest_full = os.path.join(TRAFFIC_DIR, f"honhyo_{year}_full.csv")
    if os.path.exists(dest_full) and os.path.getsize(dest_full) > 1000:
        print(f"  Already exists: {dest_full} ({os.path.getsize(dest_full) / 1024 / 1024:.1f} MB)")
        return dest_full

    print(f"  Downloading {url} ...")
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; risk_space_research/1.0)'
        })
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
            with open(dest, 'wb') as out:
                out.write(data)
            print(f"  Downloaded: {len(data) / 1024 / 1024:.1f} MB")
            return dest
    except urllib.error.HTTPError as e:
        print(f"  HTTP Error {e.code} for {year}")
        return None
    except Exception as e:
        print(f"  Failed: {e}")
        return None


def main():
    os.makedirs(NORM_DIR, exist_ok=True)

    # Collect CSV files per year
    year_files = {}

    # 2024 already exists
    full_2024 = os.path.join(TRAFFIC_DIR, "honhyo_2024_full.csv")
    if os.path.exists(full_2024):
        year_files[2024] = full_2024
        print(f"2024: Using existing {full_2024}")

    # Try downloading 2019-2023
    for year in range(2019, 2024):
        print(f"\n--- Year {year} ---")
        path = download_csv(year)
        if path:
            year_files[year] = path

    # Process all years
    output_path = os.path.join(NORM_DIR, "traffic_collision_full.json")
    total_count = 0
    year_counts = {}

    print(f"\n=== Processing all CSVs -> {output_path} ===")

    with open(output_path, 'w', encoding='utf-8') as outf:
        outf.write('[\n')
        first = True

        for year in sorted(year_files.keys()):
            filepath = year_files[year]
            print(f"\nProcessing {year}: {filepath}")

            # Auto-detect encoding
            try:
                import chardet
                with open(filepath, 'rb') as rf:
                    raw = rf.read(10000)
                    det = chardet.detect(raw)
                    enc = det['encoding']
                    if enc and enc.upper() in ('SHIFT_JIS', 'SHIFT-JIS', 'SJIS'):
                        enc = 'cp932'
                    elif not enc:
                        enc = 'cp932'
                print(f"  Encoding: {enc}")
            except ImportError:
                enc = 'cp932'

            count = 0
            for record in process_csv(filepath, encoding=enc):
                if not first:
                    outf.write(',\n')
                json.dump(record, outf, ensure_ascii=False)
                first = False
                count += 1
                if count % 50000 == 0:
                    print(f"  ... {count} records processed")

            year_counts[year] = count
            total_count += count
            print(f"  Year {year}: {count:,} records")

        outf.write('\n]')

    print(f"\n{'='*50}")
    print(f"SUMMARY")
    print(f"{'='*50}")
    for year in sorted(year_counts.keys()):
        print(f"  {year}: {year_counts[year]:>10,} records")
    print(f"  {'─'*30}")
    print(f"  Total: {total_count:>10,} records")
    print(f"\nOutput: {output_path}")
    print(f"Size: {os.path.getsize(output_path) / 1024 / 1024:.1f} MB")


if __name__ == '__main__':
    main()
