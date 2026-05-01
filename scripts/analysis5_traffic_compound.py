import pandas as pd
import numpy as np
from itertools import combinations
import json
from pathlib import Path

Path('data/analysis/traffic_profiles').mkdir(parents=True, exist_ok=True)

CODEBOOK = {
    'weather': {'1':'晴','2':'曇','3':'雨','4':'霧','5':'雪'},
    'road_surface': {'1':'乾燥','2':'湿潤','3':'凍結','4':'積雪','5':'その他'},
    'road_shape': {'01':'交差点','02':'交差点付近','03':'カーブ','04':'屈折','05':'トンネル','06':'橋','07':'踏切','14':'一般単路','99':'その他'},
    'day_night': {'11':'昼明','12':'昼','13':'昼暮','21':'夜暗','22':'夜灯あり','23':'夜道路照明あり'},
    'injury_a': {'1':'死亡','2':'重傷','3':'軽傷','4':'損傷なし'},
}

PARTY_MAP = {'01':'普通乗用','02':'普通貨物','03':'大型乗用','04':'大型貨物','05':'軽乗用','06':'軽貨物','07':'特殊','11':'自動二輪','12':'原付','13':'自転車','14':'歩行者','15':'電動キックボード','17':'その他','75':'歩行者','76':'歩行者(65+)'}

dfs = []
for f in sorted(Path('data/traffic').glob('honhyo_*.csv')):
    if 'head' in f.name or 'geocoded' in f.name: continue
    try:
        df = pd.read_csv(f, encoding='cp932', low_memory=False, dtype=str)
        dfs.append(df)
        print(f'  {f.name}: {len(df):,}行')
    except Exception as e:
        print(f'  {f.name}: ERROR {e}')

if not dfs: print('データなし'); exit()

df = pd.concat(dfs, ignore_index=True)
print(f'\n総レコード: {len(df):,}')

col_map = {}
for c in df.columns:
    if '天候' == c.strip(): col_map['weather'] = c
    elif '路面状態' == c.strip(): col_map['road_surface'] = c
    elif '道路形状' == c.strip(): col_map['road_shape'] = c
    elif '当事者種別（当事者A）' in c: col_map['party_a'] = c
    elif '当事者種別（当事者B）' in c: col_map['party_b'] = c
    elif '人身損傷程度（当事者A）' in c: col_map['injury_a'] = c
    elif '人身損傷程度（当事者B）' in c: col_map['injury_b'] = c
    elif '昼夜' == c.strip(): col_map['day_night'] = c
    elif '年齢（当事者A）' in c: col_map['age_a'] = c
    elif '年齢（当事者B）' in c: col_map['age_b'] = c
    elif '事故類型' == c.strip(): col_map['accident_type'] = c

print(f'カラムマッピング: {col_map}')

# デコード
for std, orig in col_map.items():
    if std in CODEBOOK:
        df[f'{std}_text'] = df[orig].astype(str).str.strip().map(CODEBOOK[std])
    if std == 'party_a':
        df['party_a_text'] = df[orig].astype(str).str.strip().map(PARTY_MAP)
    if std == 'party_b':
        df['party_b_text'] = df[orig].astype(str).str.strip().map(PARTY_MAP)

# 死亡/重傷フラグ
if 'injury_a' in col_map:
    df['is_fatal'] = df[col_map['injury_a']].astype(str).str.strip() == '1'
    df['is_severe'] = df[col_map['injury_a']].astype(str).str.strip().isin(['1','2'])
else:
    df['is_fatal'] = False; df['is_severe'] = False

baseline_fatal = float(df['is_fatal'].mean())
baseline_severe = float(df['is_severe'].mean())
print(f'\n死亡率ベースライン: {baseline_fatal:.5f}')
print(f'重傷以上率ベースライン: {baseline_severe:.5f}')

# 単独因子リフト
factor_risks = {}
factor_cols = {'weather_text':'天候','road_surface_text':'路面','road_shape_text':'道路形状','day_night_text':'昼夜','party_a_text':'当事者A','party_b_text':'当事者B'}
for col, label in factor_cols.items():
    if col not in df.columns: continue
    for val in df[col].dropna().unique():
        subset = df[df[col] == val]
        if len(subset) < 100: continue
        fr = float(subset['is_fatal'].mean())
        sr = float(subset['is_severe'].mean())
        lift_f = fr / baseline_fatal if baseline_fatal > 0 else 1
        lift_s = sr / baseline_severe if baseline_severe > 0 else 1
        factor_risks[f'{label}={val}'] = {'fatal_rate': round(fr,6), 'fatal_lift': round(lift_f,3), 'severe_rate': round(sr,5), 'severe_lift': round(lift_s,3), 'n': int(len(subset))}

print('\n=== 単独因子リフト（死亡率Top15）===')
for k, v in sorted(factor_risks.items(), key=lambda x: -x[1]['fatal_lift'])[:15]:
    print(f'  {k}: fatal={v["fatal_rate"]:.5f} lift={v["fatal_lift"]:.2f}x n={v["n"]:,}')

# 2因子複合リフト
compound = []
usable_cols = [c for c in ['weather_text','road_surface_text','day_night_text','party_b_text'] if c in df.columns]
for ca, cb in combinations(usable_cols, 2):
    for va in df[ca].dropna().unique():
        for vb in df[cb].dropna().unique():
            sub = df[(df[ca]==va) & (df[cb]==vb)]
            if len(sub) < 50: continue
            fr = float(sub['is_fatal'].mean())
            lift = fr / baseline_fatal if baseline_fatal > 0 else 1
            if lift > 1.5:
                compound.append({'condition': f'{ca.replace("_text","")}={va} x {cb.replace("_text","")}={vb}', 'fatal_rate': round(fr,6), 'lift': round(lift,3), 'n': int(len(sub))})

compound.sort(key=lambda x: -x['lift'])
print('\n=== 2因子複合リフト（死亡率Top15）===')
for r in compound[:15]:
    print(f'  {r["condition"]}: fatal={r["fatal_rate"]:.5f} lift={r["lift"]:.2f}x n={r["n"]:,}')

# 歩行者×時間帯
print('\n=== 歩行者×時間帯 ===')
if 'party_b_text' in df.columns and 'day_night_text' in df.columns:
    ped = df[df['party_b_text'].isin(['歩行者','歩行者(65+)'])]
    if len(ped) > 0:
        ped_dn = ped.groupby('day_night_text').agg(count=('is_fatal','count'), fatal_rate=('is_fatal','mean'), severe_rate=('is_severe','mean')).reset_index()
        print(ped_dn.sort_values('fatal_rate', ascending=False).to_string())

with open('data/analysis/traffic_profiles/compound_risk_factors.json', 'w', encoding='utf-8') as f:
    json.dump({'baseline_fatal_rate': baseline_fatal, 'baseline_severe_rate': baseline_severe, 'single_factor_risks': factor_risks, 'compound_risks': compound[:50]}, f, ensure_ascii=False, indent=2)
print('\n交通事故共起分析完了')
