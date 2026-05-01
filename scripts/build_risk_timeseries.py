#!/usr/bin/env python3
"""Build pref x month risk score timeseries from integrated profile.
Output: docs/data/risk_timeseries.json
"""
import json, os
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INP = os.path.join(BASE, 'docs', 'data', 'integrated_risk_profile.json')
OUT = os.path.join(BASE, 'docs', 'data', 'risk_timeseries.json')

d = json.load(open(INP, encoding='utf-8'))
pref = d.get('prefectures', {})
months = [f'2025-{m:02d}' for m in range(1, 13)]
result = {}
for name, v in pref.items():
    base = float(v.get('composite_risk_score', 0))
    ts = v.get('timeseries', {})
    if ts:
        result[name] = ts
    else:
        result[name] = {m: round(base, 4) for m in months}

out = {
  'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
  'months': months,
  'prefectures': result,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(out, open(OUT,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
print(f'Wrote {OUT}')
