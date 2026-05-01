import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
import json, ijson
from pathlib import Path

Path('data/analysis/modus').mkdir(parents=True, exist_ok=True)

events = []
for fname in ['data/normalized/crime_all.json', 'data/normalized/crime_national.json']:
    p = Path(fname)
    if p.exists():
        print(f'Loading {fname}...')
        with open(p, 'rb') as f:
            for i, ev in enumerate(ijson.items(f, 'item')):
                if ev.get('geometry') and ev.get('occurred_at'):
                    events.append({
                        'lat': ev['geometry']['coordinates'][1],
                        'lon': ev['geometry']['coordinates'][0],
                        'occurred_at': ev.get('occurred_at', ''),
                        'severity': ev.get('severity', 1),
                        'subtype': ev.get('subtype', ''),
                    })
                if i >= 80000:
                    break
        print(f'  loaded {len(events):,}')

print(f'クラスタリング対象: {len(events):,}件')
if len(events) < 100:
    print('データ不足')
    exit()

records = []
for ev in events:
    try:
        h = int(ev['occurred_at'][11:13])
    except Exception:
        h = 12
    hour_sin = np.sin(2 * np.pi * h / 24)
    hour_cos = np.cos(2 * np.pi * h / 24)
    sub = ev.get('subtype', '')
    is_child = 1 if any(kw in sub for kw in ['child', 'school', 'approach']) else 0
    is_female = 1 if any(kw in sub for kw in ['female', 'sexual', 'groping', 'voyeurism']) else 0
    is_elderly = 1 if 'elderly' in sub else 0
    is_property = 1 if any(kw in sub for kw in ['theft', 'burglary', 'car_parts']) else 0
    is_person = 1 if ev.get('severity', 1) >= 4 else 0
    records.append({
        'lat': ev['lat'], 'lon': ev['lon'],
        'hour_sin': hour_sin, 'hour_cos': hour_cos,
        'severity': ev.get('severity', 1),
        'is_child': is_child, 'is_female': is_female,
        'is_elderly': is_elderly, 'is_property': is_property, 'is_person': is_person,
    })

df = pd.DataFrame(records)
X = StandardScaler().fit_transform(df)
pca = PCA(n_components=5)
X_pca = pca.fit_transform(X)
print(f'PCA累積説明分散: {pca.explained_variance_ratio_.cumsum()[-1]:.3f}')

best_k, best_score = 5, -1
for k in range(4, 10):
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(X_pca)
    score = silhouette_score(X_pca, labels, sample_size=min(10000, len(X_pca)))
    print(f'  k={k}: silhouette={score:.3f}')
    if score > best_score:
        best_score = score
        best_k = k

print(f'\n最適k={best_k}')
km_final = KMeans(n_clusters=best_k, random_state=42, n_init=10)
df['cluster'] = km_final.fit_predict(X_pca)

profiles = []
for c in range(best_k):
    cd = df[df['cluster'] == c]
    p = {
        'cluster_id': c, 'size': int(len(cd)),
        'peak_hour': int(np.arctan2(cd['hour_sin'].mean(), cd['hour_cos'].mean()) / (2 * np.pi) * 24 % 24),
        'avg_severity': round(float(cd['severity'].mean()), 2),
        'child_ratio': round(float(cd['is_child'].mean()), 3),
        'female_ratio': round(float(cd['is_female'].mean()), 3),
        'elderly_ratio': round(float(cd['is_elderly'].mean()), 3),
        'property_ratio': round(float(cd['is_property'].mean()), 3),
        'person_crime_ratio': round(float(cd['is_person'].mean()), 3),
        'lat_center': round(float(cd['lat'].mean()), 4),
        'lon_center': round(float(cd['lon'].mean()), 4),
    }
    if p['child_ratio'] > 0.3:
        p['archetype'] = '子供ターゲット型'
    elif p['female_ratio'] > 0.4 and p['peak_hour'] >= 20:
        p['archetype'] = '女性深夜型'
    elif p['property_ratio'] > 0.5:
        p['archetype'] = '財物犯型'
    elif p['avg_severity'] >= 5:
        p['archetype'] = '重篤人身型'
    elif p['peak_hour'] < 6 or p['peak_hour'] >= 22:
        p['archetype'] = '深夜型'
    else:
        p['archetype'] = f'混合型（ピーク{p["peak_hour"]}時）'
    profiles.append(p)
    print(f'\nクラスター{c} [{p["archetype"]}] {len(cd)}件')
    print(f'  ピーク: {p["peak_hour"]}時, 重篤度: {p["avg_severity"]}, 子供: {p["child_ratio"]*100:.1f}%, 女性: {p["female_ratio"]*100:.1f}%')

with open('data/analysis/modus/cluster_profiles.json', 'w', encoding='utf-8') as f:
    json.dump(profiles, f, ensure_ascii=False, indent=2)
print('\nクラスタープロファイル保存完了')
