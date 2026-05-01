#!/usr/bin/env python3
"""Explore police archive/backnumber pages from source_map and backfill events.
Output: data/historical/police_archives.json
"""
import json, os, re, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, 'data', 'realtime', 'source_map.json')
OUT = os.path.join(BASE, 'data', 'historical', 'police_archives.json')
os.makedirs(os.path.dirname(OUT), exist_ok=True)

src = json.load(open(SRC, encoding='utf-8'))
prefs = src.get('prefectures', {})
archive = {}
errors = []
keywords = ['archive', 'backnumber', 'news', 'kakoka', 'osirase', 'fushinsha']

for code, p in prefs.items():
    pref_name = p.get('prefecture', code)
    urls = [s.get('url') for s in p.get('sources', []) if s.get('type') == 'police']
    found = []
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={'User-Agent': 'risk-space/1.0'})
            html = urllib.request.urlopen(req, timeout=20).read().decode('utf-8', errors='ignore')
            links = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
            for l in links:
                full = urllib.parse.urljoin(u, l)
                if any(k in full.lower() for k in keywords):
                    found.append(full)
        except Exception as e:
            errors.append(f'{pref_name} {u}: {e}')
    archive[pref_name] = sorted(set(found))[:50]

out = {
  'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
  'source_map': SRC,
  'prefectures': archive,
  'errors': errors,
}
json.dump(out, open(OUT,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
print(f'Wrote {OUT}')
