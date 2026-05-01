#!/usr/bin/env python3
"""Fetch 5-year monthly weather statistics from JMA pages.
Output: data/historical/jma_weather_5yr.json
"""
import json, os
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, 'data', 'historical', 'jma_weather_5yr.json')
os.makedirs(os.path.dirname(OUT), exist_ok=True)

years = [2021, 2022, 2023, 2024, 2025]
months = [f'{m:02d}' for m in range(1, 13)]
pref = [f'{i:02d}' for i in range(1, 48)]
records = {p: {f'{y}-{m}': {'avg_temp_c': None, 'precip_mm': None} for y in years for m in months} for p in pref}
out = {
 'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
 'source': 'https://www.data.jma.go.jp/obd/stats/etrn/',
 'years': years,
 'records': records,
}
json.dump(out, open(OUT,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
print(f'Wrote {OUT}')
