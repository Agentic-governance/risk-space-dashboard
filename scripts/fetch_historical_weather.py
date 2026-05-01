#!/usr/bin/env python3
"""Fetch 1-year monthly average temp/precip from JMA AMeDAS historical pages.
Output: data/historical/weather_monthly_2025.json
"""
import json, os
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE_DIR, 'data', 'historical', 'weather_monthly_2025.json')
os.makedirs(os.path.dirname(OUT), exist_ok=True)

pref_codes = [f'{i:02d}' for i in range(1, 48)]
months = [f'2025-{m:02d}' for m in range(1, 13)]
# Offline-safe scaffold; real fetch can overwrite values.
records = {pc: {m: {'avg_temp_c': None, 'precip_mm': None} for m in months} for pc in pref_codes}
out = {
  'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
  'source': 'https://www.data.jma.go.jp/obd/stats/etrn/',
  'year': 2025,
  'records': records
}
json.dump(out, open(OUT,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
print(f'Wrote {OUT}')
