import json
from pathlib import Path

ipath = Path("data/analysis/interaction/traffic_interaction_table.json")
if not ipath.exists():
    print("交互作用テーブル未生成。Part1を先に実行してください。"); exit()

with open(ipath, encoding="utf-8") as f:
    raw = json.load(f)

INTERACTION_TABLE = raw["table"]
BASELINE = raw["baseline_fatal_rate"]
print(f"テーブルエントリ数: {len(INTERACTION_TABLE)}")
print(f"ベースライン死亡率: {BASELINE:.6f}")

def lookup_traffic_lift(age_group, party_type, weather, road_surface, day_night):
    candidates = [
        f"{age_group}+{party_type}+{weather}+{road_surface}+{day_night}",
        f"{age_group}+{party_type}+{weather}+{road_surface}",
        f"{age_group}+{party_type}+{weather}",
        f"{age_group}+{weather}+{road_surface}",
        f"{age_group}+{road_surface}+{day_night}",
        f"{age_group}+{party_type}+{day_night}",
        f"{party_type}+{weather}+{day_night}",
        f"{age_group}+{weather}",
        f"{age_group}+{party_type}",
        f"{party_type}+{weather}",
        f"{weather}+{road_surface}",
        f"{age_group}+{day_night}",
        f"{age_group}+{road_surface}",
        f"{party_type}+{day_night}",
    ]
    for key in candidates:
        if key in INTERACTION_TABLE:
            e = INTERACTION_TABLE[key]
            return {"lift":e["lift"],"fatal_rate":e["fatal_rate"],"n":e["n"],"match_dims":len(e["dims"]),"matched":key,"confidence":"high" if len(e["dims"])>=3 else "medium"}
    return {"lift":1.0,"fatal_rate":BASELINE,"n":0,"match_dims":0,"matched":"default","confidence":"low"}

def calc_personalized_traffic_risk(base_risk, age_group, party_type, weather, road_surface, hour):
    if 6<=hour<16: dn="day_light"
    elif 16<=hour<19: dn="day_dim"
    elif 19<=hour<22: dn="night_lit"
    else: dn="night_dark"
    r = lookup_traffic_lift(age_group, party_type, weather, road_surface, dn)
    return {"dynamic_risk":round(min(1.0,base_risk*r["lift"]),5),"lift":round(r["lift"],2),"confidence":r["confidence"],"matched":r["matched"],"fatal_pct":round(r["fatal_rate"]*100,3)}

print("\n=== テストケース ===")
tests = [
    ("elderly","elderly_pedestrian","snow","snow_covered",20,"高齢者×歩行者×雪×積雪×夜"),
    ("elderly","elderly_pedestrian","sunny","dry",14,"高齢者×歩行者×晴×乾燥×昼"),
    ("child","pedestrian","rain","wet",16,"子供×歩行者×雨×湿潤×下校時"),
    ("adult","car","sunny","dry",10,"成人×車×晴×乾燥×昼"),
    ("youth","bicycle","rain","wet",23,"若者×自転車×雨×深夜"),
    ("elderly","elderly_pedestrian","fog","wet",19,"高齢者×歩行者×霧×湿潤×夜"),
    ("child","bicycle","cloudy","dry",16,"子供×自転車×曇×下校時"),
    ("elderly","pedestrian","rain","wet",21,"高齢者×歩行者×雨×夜"),
]
print(f"{'シナリオ':<35} {'lift':>8} {'致死率':>8} {'信頼度':>8} {'マッチ'}")
print("-"*85)
for age,party,w,rs,h,label in tests:
    r = calc_personalized_traffic_risk(0.25,age,party,w,rs,h)
    print(f"  {label:<33} {r['lift']:>7.1f}x {r['fatal_pct']:>6.3f}% {r['confidence']:>8} {r['matched']}")

# interaction_model.py保存
model_code = '''import json
from pathlib import Path

_TABLE_PATH = Path(__file__).parent.parent / "data" / "analysis" / "interaction" / "traffic_interaction_table.json"
_DATA = None

def _load():
    global _DATA
    if _DATA is None:
        with open(_TABLE_PATH, encoding="utf-8") as f:
            _DATA = json.load(f)
    return _DATA

def lookup_traffic_lift(age_group, party_type, weather, road_surface, day_night):
    data = _load()
    table = data["table"]
    baseline = data["baseline_fatal_rate"]
    candidates = [
        f"{age_group}+{party_type}+{weather}+{road_surface}+{day_night}",
        f"{age_group}+{party_type}+{weather}+{road_surface}",
        f"{age_group}+{party_type}+{weather}",
        f"{age_group}+{weather}+{road_surface}",
        f"{age_group}+{party_type}+{day_night}",
        f"{party_type}+{weather}+{day_night}",
        f"{age_group}+{weather}",
        f"{age_group}+{party_type}",
        f"{party_type}+{weather}",
        f"{weather}+{road_surface}",
        f"{age_group}+{day_night}",
        f"{party_type}+{day_night}",
    ]
    for key in candidates:
        if key in table:
            e = table[key]
            return {"lift":e["lift"],"fatal_rate":e["fatal_rate"],"matched":key,"confidence":"high" if len(e["dims"])>=3 else "medium"}
    return {"lift":1.0,"fatal_rate":baseline,"matched":"default","confidence":"low"}

def personalized_risk(base, age_group, party_type, weather, road_surface, hour):
    if 6<=hour<16: dn="day_light"
    elif 16<=hour<19: dn="day_dim"
    elif 19<=hour<22: dn="night_lit"
    else: dn="night_dark"
    r = lookup_traffic_lift(age_group, party_type, weather, road_surface, dn)
    return {"risk":min(1.0, base*r["lift"]), "lift":r["lift"], "confidence":r["confidence"], "matched":r["matched"]}
'''
Path("scripts/interaction_model.py").write_text(model_code, encoding="utf-8")
print("\nscripts/interaction_model.py 保存完了")
