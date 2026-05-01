#!/usr/bin/env python3
"""Validate historical JSONs.
exit 0=OK, exit 1=problem
"""
import json, os, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
H = BASE / 'data' / 'historical'
jsons = sorted(H.glob('*.json'))
problems = []

for p in jsons:
    try:
        d = json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:
        problems.append(f'{p.name}: invalid json ({e})')
        continue
    if isinstance(d, dict) and 'period' in d and isinstance(d['period'], str):
        pass
    if isinstance(d, dict) and 'series' in d:
        for pref, s in d['series'].items():
            months = [k for k in s.keys() if len(k)==7 and k[4]=='-']
            if len(months) < 12:
                problems.append(f'{p.name}:{pref} coverage<12m')

if problems:
    print('NG')
    for x in problems[:100]:
        print('-', x)
    sys.exit(1)
print(f'OK: {len(jsons)} files checked')
sys.exit(0)
