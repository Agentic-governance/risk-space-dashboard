import pandas as pd
import numpy as np
from scipy.stats import spearmanr
import json, ijson
from pathlib import Path
from datetime import datetime, timedelta

Path('data/analysis/escalation').mkdir(parents=True, exist_ok=True)

SEVERITY_SCORE = {'不審者':1,'声かけ':2,'つきまとい':3,'盗撮':3,'ちかん':4,'痴漢':4,'わいせつ':5,'ひったくり':4,'暴行':6,'傷害':7,'強盗':8,'強制性交':9,
'suspicious_person_approach':2,'suspicious_person_stalking':3,'sexual_crime_voyeurism':3,'sexual_crime_groping':4,'sexual_crime':5,'theft_purse_snatching':4,'theft_bicycle':1,'theft_car_parts':2,'theft_burglary':4,'assault':6,'robbery':7,'weapons':6,'collision_fatal':8,'collision_injury':4}

def get_severity(crime_text):
    for kw, score in sorted(SEVERITY_SCORE.items(), key=lambda x: -x[1]):
        if kw in str(crime_text): return score
    return 1

# データ読み込み
events_list = []
for fname in ['data/normalized/crime_all.json','data/normalized/crime_national.json']:
    p = Path(fname)
    if p.exists():
        print(f'Loading {fname}...')
        with open(p, 'rb') as f:
            for ev in ijson.items(f, 'item'):
                if ev.get('geometry') and ev.get('occurred_at'):
                    events_list.append({
                        'lat': ev['geometry']['coordinates'][1],
                        'lon': ev['geometry']['coordinates'][0],
                        'occurred_at': ev.get('occurred_at',''),
                        'crime_type': ev.get('subtype',''),
                        'severity': get_severity(ev.get('subtype','')),
                    })
        print(f'  loaded {len(events_list):,} events so far')

# ガッコムデータも追加
gaccom_path = Path('data/realtime/fushinsha_7days/gaccom_full.json')
if gaccom_path.exists():
    with open(gaccom_path, encoding='utf-8') as f:
        gdata = json.load(f)
    for inc in gdata.get('incidents',[]):
        if inc.get('lat') and inc.get('lng') and inc.get('date'):
            events_list.append({
                'lat': float(inc['lat']),
                'lon': float(inc['lng']),
                'occurred_at': inc.get('date',''),
                'crime_type': inc.get('kind_name',''),
                'severity': get_severity(inc.get('kind_name','')),
            })
    print(f'  + gaccom: total {len(events_list):,}')

if not events_list:
    print('データなし'); exit()

df = pd.DataFrame(events_list)
df['grid_lat'] = (df['lat'] / 0.01).round() * 0.01
df['grid_lon'] = (df['lon'] / 0.01).round() * 0.01
df['grid_id'] = df['grid_lat'].astype(str) + '_' + df['grid_lon'].astype(str)
df['dt'] = pd.to_datetime(df['occurred_at'], errors='coerce')
df = df.dropna(subset=['dt']).sort_values('dt')
print(f'有効イベント: {len(df):,}, ユニークグリッド: {df["grid_id"].nunique():,}')

escalation_alerts = []
for grid_id, group in df.groupby('grid_id'):
    if len(group) < 5: continue
    group = group.sort_values('dt')
    n = len(group)
    corr, pvalue = spearmanr(np.arange(n), group['severity'].values)
    if corr > 0.3 and pvalue < 0.15:
        recent = group[group['dt'] >= group['dt'].max() - timedelta(days=30)]
        early = group[group['dt'] <= group['dt'].min() + timedelta(days=30)]
        if len(early) == 0: continue
        escalation_alerts.append({
            'grid_id': grid_id,
            'lat': float(group['grid_lat'].iloc[0]),
            'lon': float(group['grid_lon'].iloc[0]),
            'event_count': len(group),
            'period_days': (group['dt'].max() - group['dt'].min()).days,
            'spearman_corr': round(float(corr), 3),
            'p_value': round(float(pvalue), 4),
            'early_severity_avg': round(float(early['severity'].mean()), 2),
            'recent_severity_avg': round(float(recent['severity'].mean()), 2) if len(recent) > 0 else None,
            'severity_increase': round(float((recent['severity'].mean() - early['severity'].mean()) / max(early['severity'].mean(), 0.01)), 3) if len(recent) > 0 else 0,
            'crime_sequence': group['crime_type'].tolist()[-10:],
            'is_escalating': True,
        })

escalation_alerts.sort(key=lambda x: -x['spearman_corr'])
print(f'\nエスカレーション検出: {len(escalation_alerts)}地点')
for a in escalation_alerts[:10]:
    print(f'  ({a["lat"]:.3f},{a["lon"]:.3f}) corr={a["spearman_corr"]} sev:{a["early_severity_avg"]}→{a["recent_severity_avg"]} seq:{" → ".join(a["crime_sequence"][-5:])}')

with open('data/analysis/escalation/escalation_alerts.json', 'w', encoding='utf-8') as f:
    json.dump(escalation_alerts, f, ensure_ascii=False, indent=2)
print(f'保存完了: {len(escalation_alerts)}件')
