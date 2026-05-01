#!/usr/bin/env python3
"""Backfill 1 year of fushinsha articles from Nordot unit page.
Output: data/historical/fushinsha_1year.json
"""
import json, os, re, urllib.request
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE_DIR, 'data', 'historical', 'fushinsha_1year.json')
os.makedirs(os.path.dirname(OUT), exist_ok=True)
BASE_URL = 'https://news.jp/i/-/units/133089874031904245'

cutoff = datetime.now(timezone.utc) - timedelta(days=365)
articles = []
errors = []
for page in range(1, 16):
    url = BASE_URL if page == 1 else f'{BASE_URL}?page={page}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'risk-space/1.0'})
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode('utf-8', errors='ignore')
        for m in re.finditer(r'(/i/\d+)[^\n]{0,200}?datetime="([0-9TZ:\-]+)"', html):
            dt = datetime.fromisoformat(m.group(2).replace('Z', '+00:00'))
            if dt < cutoff:
                continue
            articles.append({'url': 'https://news.jp' + m.group(1), 'published_at': dt.isoformat()})
    except Exception as e:
        errors.append(f'{url}: {e}')

seen = set(); dedup=[]
for a in articles:
    if a['url'] in seen: continue
    seen.add(a['url']); dedup.append(a)

out = {
  'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
  'source_unit': BASE_URL,
  'period_days': 365,
  'count': len(dedup),
  'errors': errors,
  'articles': sorted(dedup, key=lambda x: x['published_at'], reverse=True)
}
json.dump(out, open(OUT,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
print(f'Wrote {OUT}')
