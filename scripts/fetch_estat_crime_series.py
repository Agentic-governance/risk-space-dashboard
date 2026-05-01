#!/usr/bin/env python3
"""Fetch monthly crime series (2019-2025) from public NPA/e-Stat pages.
Output: data/historical/crime_monthly_series.json
"""
import json, os, re, urllib.request, urllib.error
from datetime import datetime, timezone
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE_DIR, 'data', 'historical', 'crime_monthly_series.json')
os.makedirs(os.path.dirname(OUT), exist_ok=True)

URLS = [
    'https://www.npa.go.jp/publications/statistics/sousa/statistics.html',
    'https://www.npa.go.jp/publications/statistics/crime_statistics.html',
]

month_re = re.compile(r'(20(?:19|20|21|22|23|24|25))\D{0,4}(1[0-2]|0?[1-9])\D{0,3}(\d{1,7})')

series = defaultdict(lambda: defaultdict(int))
errors = []
for url in URLS:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'risk-space/1.0'})
        with urllib.request.urlopen(req, timeout=30) as r:
            txt = r.read().decode('utf-8', errors='ignore')
        for y, m, v in month_re.findall(txt):
            series['全国'][f"{int(y):04d}-{int(m):02d}"] += int(v)
    except Exception as e:
        errors.append(f'{url}: {e}')

# ensure full month keys exist
for y in range(2019, 2026):
    for m in range(1, 13):
        k = f'{y:04d}-{m:02d}'
        _ = series['全国'][k]

out = {
    'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'period': '2019-01 to 2025-12',
    'source_urls': URLS,
    'errors': errors,
    'series': {p: dict(sorted(v.items())) for p, v in series.items()},
}
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f'Wrote {OUT}')
