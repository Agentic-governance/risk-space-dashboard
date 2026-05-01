import pandas as pd
import numpy as np
from mlxtend.frequent_patterns import apriori, association_rules
from mlxtend.preprocessing import TransactionEncoder
import json, csv, re
from pathlib import Path
from collections import defaultdict

Path('data/analysis/cooccurrence').mkdir(parents=True, exist_ok=True)

def load_all_crime_events():
    events = []
    crime_dir = Path('data/crime/prefectures')
    encs = ['utf-8-sig','utf-8','cp932','shift_jis','euc_jp']
    file_count = 0
    for csv_file in sorted(crime_dir.rglob('*.csv')):
        for enc in encs:
            try:
                with open(csv_file, 'r', encoding=enc, newline='') as f:
                    reader = csv.DictReader(f)
                    if not reader.fieldnames: break
                    cols = reader.fieldnames
                    time_cols = [c for c in cols if any(kw in c for kw in ['時','発生時'])]
                    crime_cols = [c for c in cols if any(kw in c for kw in ['罪名','手口','種別'])]
                    place_cols = [c for c in cols if any(kw in c for kw in ['発生場所','場所'])]
                    age_cols = [c for c in cols if '年齢' in c]
                    gender_cols = [c for c in cols if '性別' in c]
                    lock_cols = [c for c in cols if '施錠' in c]
                    for row in reader:
                        conditions = []
                        for tc in time_cols:
                            val = str(row.get(tc,''))
                            try:
                                h = int(re.search(r'(\d+)', val).group(1))
                                if 0 <= h < 6: conditions.append('深夜帯_0-6時')
                                elif 6 <= h < 9: conditions.append('通勤帯_6-9時')
                                elif 9 <= h < 14: conditions.append('昼間_9-14時')
                                elif 14 <= h < 18: conditions.append('下校帯_14-18時')
                                elif 18 <= h < 22: conditions.append('夜間_18-22時')
                                else: conditions.append('深夜帯_22-24時')
                            except: pass
                            break
                        for cc in crime_cols:
                            val = str(row.get(cc,'')).strip()
                            if val and val != 'nan': conditions.append(f'罪種_{val[:10]}')
                            break
                        for pc in place_cols:
                            val = str(row.get(pc,''))
                            for pkw in ['路上','公園','駐車場','駅','学校','住宅','店舗','共同住宅','道路上','コンビニ']:
                                if pkw in val: conditions.append(f'場所_{pkw}'); break
                            break
                        for ac in age_cols:
                            val = str(row.get(ac,''))
                            try:
                                age = int(re.search(r'(\d+)', val).group(1))
                                if age < 13: conditions.append('被害者_小学生以下')
                                elif age < 18: conditions.append('被害者_未成年')
                                elif age < 30: conditions.append('被害者_20代')
                                elif age < 65: conditions.append('被害者_成人')
                                else: conditions.append('被害者_高齢者')
                            except: pass
                            break
                        for gc in gender_cols:
                            val = str(row.get(gc,''))
                            if any(kw in val for kw in ['女','F']): conditions.append('被害者_女性')
                            elif any(kw in val for kw in ['男','M']): conditions.append('被害者_男性')
                            break
                        for lc in lock_cols:
                            val = str(row.get(lc,''))
                            if '無施錠' in val or val == '2': conditions.append('無施錠')
                            elif '施錠' in val or val == '1': conditions.append('施錠あり')
                            break
                        if len(conditions) >= 2:
                            events.append(list(set(conditions)))
                    file_count += 1
                    break
            except: continue
    print(f'読み込みファイル数: {file_count}, トランザクション数: {len(events):,}')
    return events

print('犯罪イベント読み込み中...')
transactions = load_all_crime_events()

te = TransactionEncoder()
te_array = te.fit_transform(transactions)
df_te = pd.DataFrame(te_array, columns=te.columns_)

print('Apriori実行中（min_support=0.005）...')
frequent_itemsets = apriori(df_te, min_support=0.005, use_colnames=True, max_len=4)
print(f'頻出アイテムセット: {len(frequent_itemsets)}件')

rules = association_rules(frequent_itemsets, metric='lift', min_threshold=1.2, num_itemsets=len(frequent_itemsets))
rules = rules.sort_values('lift', ascending=False)
print(f'発見されたルール: {len(rules)}件')

print('\n=== 子供に関連する高リフトルール ===')
child_rules = rules[rules.apply(lambda r: any('小学生' in str(x) or '未成年' in str(x) for x in list(r['antecedents'])+list(r['consequents'])), axis=1)]
print(child_rules[['antecedents','consequents','support','confidence','lift']].head(20).to_string())

print('\n=== 女性×深夜リスク ===')
female_night = rules[rules.apply(lambda r: '被害者_女性' in str(r['antecedents']) and '深夜' in str(r['antecedents']), axis=1)]
print(female_night[['antecedents','consequents','support','confidence','lift']].head(10).to_string())

print('\n=== lift上位20 ===')
print(rules[['antecedents','consequents','support','confidence','lift']].head(20).to_string())

rules_out = rules.head(200).copy()
rules_out['antecedents'] = rules_out['antecedents'].apply(lambda x: list(x))
rules_out['consequents'] = rules_out['consequents'].apply(lambda x: list(x))
rules_out.to_json('data/analysis/cooccurrence/association_rules.json', orient='records', force_ascii=False)
print('\n共起ルール保存完了')
