import pandas as pd
import numpy as np
from itertools import combinations
import json, chardet
from pathlib import Path

Path("data/analysis/interaction").mkdir(parents=True, exist_ok=True)

dfs = []
for f in sorted(Path("data/traffic").glob("honhyo_*.csv")):
    if 'head' in f.name or 'geocoded' in f.name: continue
    try:
        df = pd.read_csv(f, encoding="cp932", low_memory=False, dtype=str)
        dfs.append(df)
        print(f"  {f.name}: {len(df):,}行")
    except:
        try:
            with open(f,"rb") as fh: enc=chardet.detect(fh.read(5000))["encoding"] or "cp932"
            df = pd.read_csv(f, encoding=enc, low_memory=False, dtype=str)
            dfs.append(df)
        except Exception as e: print(f"  {f.name}: {e}")

df = pd.concat(dfs, ignore_index=True)
print(f"\n交通事故 全件: {len(df):,}件")

col_map = {}
for c in df.columns:
    cs = c.strip()
    if cs == "天候": col_map["weather"] = c
    elif cs == "路面状態": col_map["road_surface"] = c
    elif cs == "道路形状": col_map["road_shape"] = c
    elif "当事者種別（当事者A）" in c: col_map["party_a"] = c
    elif "当事者種別（当事者B）" in c: col_map["party_b"] = c
    elif "人身損傷程度（当事者A）" in c: col_map["injury_a"] = c
    elif "人身損傷程度（当事者B）" in c: col_map["injury_b"] = c
    elif cs == "昼夜": col_map["day_night"] = c
    elif "年齢（当事者A）" in c: col_map["age_a"] = c
    elif "年齢（当事者B）" in c: col_map["age_b"] = c

CODEBOOK = {
    "weather": {"1":"sunny","2":"cloudy","3":"rain","4":"fog","5":"snow"},
    "road_surface": {"1":"dry","2":"wet","3":"frozen","4":"snow_covered","5":"other"},
    "road_shape": {"01":"intersection","02":"near_intersection","14":"straight","03":"curve","04":"bend"},
    "day_night": {"11":"day_light","12":"day","13":"day_dim","21":"night_dark","22":"night_lit","23":"night_road_lit"},
}
PARTY_MAP = {"01":"car","02":"truck","03":"bus","04":"large_truck","05":"light_car","06":"light_truck","07":"special","11":"motorcycle","12":"scooter","13":"bicycle","14":"pedestrian","15":"e_kickboard","75":"pedestrian","76":"elderly_pedestrian"}

for field, codes in CODEBOOK.items():
    if field in col_map: df[f"{field}_text"] = df[col_map[field]].astype(str).str.strip().map(codes)
if "party_a" in col_map: df["party_a_text"] = df[col_map["party_a"]].astype(str).str.strip().map(PARTY_MAP)
if "party_b" in col_map: df["party_b_text"] = df[col_map["party_b"]].astype(str).str.strip().map(PARTY_MAP)

if "age_b" in col_map:
    age_num = pd.to_numeric(df[col_map["age_b"]], errors="coerce")
    df["age_group_b"] = pd.cut(age_num, bins=[-1,12,17,64,120], labels=["child","youth","adult","elderly"]).astype(str).replace("nan",None)

if "injury_a" in col_map:
    df["is_fatal"] = df[col_map["injury_a"]].astype(str).str.strip() == "1"
    df["is_severe"] = df[col_map["injury_a"]].astype(str).str.strip().isin(["1","2"])
else:
    df["is_fatal"] = False; df["is_severe"] = False

baseline_fatal = float(df["is_fatal"].mean())
baseline_severe = float(df["is_severe"].mean())
print(f"\nベースライン死亡率: {baseline_fatal:.6f} ({baseline_fatal*100:.4f}%)")
print(f"ベースライン重傷以上率: {baseline_severe:.5f}")

DIMENSIONS = {}
for col in ["age_group_b","party_b_text","weather_text","road_surface_text","day_night_text","road_shape_text"]:
    if col in df.columns:
        vals = [v for v in df[col].dropna().unique() if v and v != "nan"]
        if vals: DIMENSIONS[col] = vals

print(f"分析次元: {list(DIMENSIONS.keys())}")

interaction_table = {}

print("\n2次元交互作用構築中...")
for dim_a, dim_b in combinations(DIMENSIONS.keys(), 2):
    for val_a in DIMENSIONS[dim_a]:
        for val_b in DIMENSIONS[dim_b]:
            mask = (df[dim_a]==val_a) & (df[dim_b]==val_b)
            subset = df[mask]
            if len(subset) < 20: continue
            fr = float(subset["is_fatal"].mean())
            sr = float(subset["is_severe"].mean())
            lift = fr / baseline_fatal if baseline_fatal > 0 else 1.0
            key = f"{val_a}+{val_b}"
            interaction_table[key] = {"dims":[dim_a,dim_b],"values":[val_a,val_b],"fatal_rate":round(fr,6),"severe_rate":round(sr,5),"baseline":round(baseline_fatal,6),"lift":round(lift,3),"n":int(len(subset))}

print("3次元交互作用構築中...")
KEY_3D = [
    ("age_group_b","weather_text","road_surface_text"),
    ("age_group_b","party_b_text","weather_text"),
    ("age_group_b","party_b_text","day_night_text"),
    ("party_b_text","weather_text","day_night_text"),
    ("age_group_b","road_surface_text","day_night_text"),
]
for dims in KEY_3D:
    if not all(d in df.columns for d in dims): continue
    for val_a in DIMENSIONS.get(dims[0],[]):
        for val_b in DIMENSIONS.get(dims[1],[]):
            for val_c in DIMENSIONS.get(dims[2],[]):
                mask = (df[dims[0]]==val_a) & (df[dims[1]]==val_b) & (df[dims[2]]==val_c)
                subset = df[mask]
                if len(subset) < 15: continue
                fr = float(subset["is_fatal"].mean())
                lift = fr / baseline_fatal if baseline_fatal > 0 else 1.0
                if lift < 2.0: continue
                key = f"{val_a}+{val_b}+{val_c}"
                interaction_table[key] = {"dims":list(dims),"values":[val_a,val_b,val_c],"fatal_rate":round(fr,6),"baseline":round(baseline_fatal,6),"lift":round(lift,3),"n":int(len(subset))}

top = sorted(interaction_table.values(), key=lambda x: -x["lift"])
print(f"\n交互作用テーブル: {len(interaction_table)}エントリ")
print(f"\n{'条件':<55} {'死亡率':>9} {'lift':>8} {'n':>8}")
print("-"*83)
for r in top[:30]:
    cond = " × ".join(r["values"])
    print(f"  {cond:<53}  {r['fatal_rate']*100:>6.3f}%  {r['lift']:>7.1f}x  {r['n']:>7,}")

with open("data/analysis/interaction/traffic_interaction_table.json","w",encoding="utf-8") as f:
    json.dump({"generated_at":str(pd.Timestamp.now()),"baseline_fatal_rate":baseline_fatal,"baseline_severe_rate":baseline_severe,"total_records":int(len(df)),"entry_count":len(interaction_table),"table":interaction_table},f,ensure_ascii=False,indent=2)
print("\n保存完了")
