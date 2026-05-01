import json, ijson
from pathlib import Path
from collections import defaultdict
from itertools import combinations

Path('data/analysis/victim_pathway').mkdir(parents=True, exist_ok=True)

events = []
for fname in ['data/normalized/crime_all.json','data/normalized/crime_national.json']:
    p = Path(fname)
    if p.exists():
        print(f'Loading {fname}...')
        with open(p, 'rb') as f:
            for ev in ijson.items(f, 'item'):
                if ev.get('geometry') and ev.get('occurred_at'):
                    try: h = int(ev['occurred_at'][11:13])
                    except: h = 12
                    events.append({
                        'lat': ev['geometry']['coordinates'][1],
                        'lon': ev['geometry']['coordinates'][0],
                        'hour': h,
                        'severity': ev.get('severity', 1),
                        'subtype': ev.get('subtype',''),
                        'haven_count_500m': ev.get('properties',{}).get('haven_count_500m', 5),
                    })
        print(f'  total: {len(events):,}')

# ガッコムも追加
gaccom_path = Path('data/realtime/fushinsha_7days/gaccom_full.json')
if gaccom_path.exists():
    with open(gaccom_path, encoding='utf-8') as f:
        gdata = json.load(f)
    for inc in gdata.get('incidents',[]):
        if inc.get('lat') and inc.get('lng'):
            import re
            hour = 12
            desc = str(inc.get('description',''))
            m = re.search(r'午後(\d+)時', desc)
            if m: hour = int(m.group(1)) + 12
            m2 = re.search(r'午前(\d+)時', desc)
            if m2: hour = int(m2.group(1))
            sev_map = {'不審者':2,'声かけ':2,'ちかん':4,'のぞき':3,'盗撮':3,'暴行・暴力':5,'凶器・武器':5,'強盗・脅迫':5,'住居侵入':4,'子ども被害':3,'迷惑行為':2}
            events.append({
                'lat': float(inc['lat']), 'lon': float(inc['lng']),
                'hour': hour,
                'severity': sev_map.get(inc.get('kind_name',''), 2),
                'subtype': inc.get('kind_name',''),
                'haven_count_500m': 5,
            })
    print(f'  + gaccom: total {len(events):,}')

if not events:
    print('データなし'); exit()

target_profiles = {
    '子供（未成年全般）': lambda e: any(kw in e.get('subtype','') for kw in ['child','approach','声かけ','子ども被害','school']),
    '女性（夜間）': lambda e: any(kw in e.get('subtype','') for kw in ['sexual','groping','voyeurism','ちかん','盗撮','のぞき','痴漢']) and (e.get('hour',12) >= 20 or e.get('hour',12) < 6),
    '高齢者': lambda e: 'elderly' in e.get('subtype','') or e.get('subtype','') in ['強盗・脅迫','住居侵入'],
}

conditions = {
    '深夜（22-6時）': lambda e: e.get('hour',12) >= 22 or e.get('hour',12) < 6,
    '夕方下校帯（14-18時）': lambda e: 14 <= e.get('hour',12) < 18,
    '夜間（18-22時）': lambda e: 18 <= e.get('hour',12) < 22,
    '通勤帯（6-9時）': lambda e: 6 <= e.get('hour',12) < 9,
    '高重篤度（sev>=4）': lambda e: e.get('severity',1) >= 4,
}

results = {}
for pname, pfunc in target_profiles.items():
    target = [e for e in events if pfunc(e)]
    if not target:
        print(f'{pname}: 該当なし'); continue
    
    serious_threshold = 4
    baseline = sum(1 for e in target if e.get('severity',1) >= serious_threshold) / max(len(target),1)
    
    single_risks = {}
    for cname, cfunc in conditions.items():
        cevents = [e for e in target if cfunc(e)]
        if not cevents: continue
        serious = sum(1 for e in cevents if e.get('severity',1) >= serious_threshold)
        p = serious / len(cevents)
        single_risks[cname] = {'p_serious': round(p,4), 'baseline': round(baseline,4), 'lift': round(p/max(baseline,0.001),3), 'n': len(cevents)}
    
    compound_risks = {}
    for r in [2,3]:
        for combo in combinations(list(conditions.items()), r):
            cnames = [c[0] for c in combo]
            cfuncs = [c[1] for c in combo]
            cevents = [e for e in target if all(f(e) for f in cfuncs)]
            if len(cevents) < 3: continue
            serious = sum(1 for e in cevents if e.get('severity',1) >= serious_threshold)
            p = serious / len(cevents)
            key = ' + '.join(cnames)
            compound_risks[key] = {'p_serious': round(p,4), 'baseline': round(baseline,4), 'lift': round(p/max(baseline,0.001),3), 'n': len(cevents)}
    
    sorted_compound = sorted(compound_risks.items(), key=lambda x: -x[1]['lift'])
    results[pname] = {'total_events': len(target), 'single_conditions': single_risks, 'compound_risks': dict(sorted_compound[:20])}
    
    print(f'\n=== {pname} ({len(target)}件) ===')
    print('単独条件:')
    for c, r in sorted(single_risks.items(), key=lambda x: -x[1]['lift']):
        print(f'  {c}: P={r["p_serious"]:.3f} lift={r["lift"]:.2f}x n={r["n"]}')
    print('複合条件Top5:')
    for c, r in sorted_compound[:5]:
        print(f'  {c}: P={r["p_serious"]:.3f} lift={r["lift"]:.2f}x n={r["n"]}')

with open('data/analysis/victim_pathway/pathway_analysis.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print('\n被害者経路分析完了')
