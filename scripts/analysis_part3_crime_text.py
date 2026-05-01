import json, re
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timedelta

Path("data/analysis/crime_qualitative").mkdir(parents=True, exist_ok=True)

text_events = []

# ガッコム（最大のテキストソース）
gaccom_path = Path("data/realtime/fushinsha_7days/gaccom_full.json")
if gaccom_path.exists():
    with open(gaccom_path, encoding="utf-8") as f:
        gdata = json.load(f)
    for inc in gdata.get("incidents", []):
        title = inc.get("title", "") or ""
        desc = inc.get("description", "") or ""
        full = inc.get("full_description", "") or ""
        text = f"{title} {desc} {full}".strip()
        if len(text) < 10:
            continue
        text_events.append(
            {
                "text": text,
                "kind_name": inc.get("kind_name", ""),
                "severity": inc.get("severity", 2),
                "pref": inc.get("prefecture", ""),
                "city": inc.get("city", ""),
                "date": inc.get("date", ""),
                "lat": inc.get("lat"),
                "lng": inc.get("lng"),
                "source": "gaccom",
            }
        )
    print(f"gaccom: {len(text_events)}件")

# police_deep_crawl
pdp = Path("data/realtime/fushinsha_7days/police_deep_crawl.json")
if pdp.exists():
    with open(pdp, encoding="utf-8") as f:
        pdata = json.load(f)
    for inc in pdata.get("incidents", []):
        text = inc.get("title", "") or inc.get("description", "") or ""
        if len(text) < 10:
            continue
        text_events.append(
            {
                "text": text,
                "kind_name": inc.get("category", ""),
                "severity": inc.get("severity", 2),
                "pref": inc.get("prefecture", ""),
                "date": inc.get("date", ""),
                "source": "police_direct",
            }
        )
    print(f"police_direct追加後: {len(text_events)}件")

# deep_crawl
dcp = Path("data/realtime/fushinsha_7days/deep_crawl.json")
if dcp.exists():
    with open(dcp, encoding="utf-8") as f:
        dcdata = json.load(f)
    items = dcdata if isinstance(dcdata, list) else dcdata.get("items", dcdata.get("incidents", []))
    for inc in items:
        text = inc.get("title", "") or ""
        if len(text) < 10:
            continue
        text_events.append({"text": text, "kind_name": "", "severity": 2, "pref": "", "date": "", "source": "deep_crawl"})
    print(f"deep_crawl追加後: {len(text_events)}件")

print(f"\nテキストイベント合計: {len(text_events)}件")
for src in set(e["source"] for e in text_events):
    n = sum(1 for e in text_events if e["source"] == src)
    print(f"  {src}: {n}件")

TIME_PATTERNS = {
    "登校時(6-9時)": r"(?:午前[6-9]時|登校|通学|登下校)",
    "昼間(9-14時)": r"(?:午前1[0-2]時|正午|昼|日中|午後[1-2]時)",
    "下校時(14-18時)": r"(?:午後[2-6]時|1[4-8]時|下校|放課後|帰宅途中)",
    "夕方(18-20時)": r"(?:午後[6-8]時|1[89]時|20時|夕方|夕暮)",
    "夜間(20-23時)": r"(?:午後[8-9]時|2[0-3]時|夜間|夜)",
    "深夜(23-6時)": r"(?:午後1[1-2]時|23時|午前[0-5]時|深夜|未明)",
}
LOCATION_PATTERNS = {
    "通学路・学校付近": r"(?:通学路|学校|小学|中学|高校|校門|校区|通学|学区)",
    "路上・歩道": r"(?:路上|歩道|道路|横断歩道|歩行中|付近の路上)",
    "公園": r"(?:公園|児童公園|広場|緑地)",
    "駅・バス停": r"(?:駅|バス停|電車|ホーム|改札|乗車中|車内)",
    "住宅地": r"(?:住宅|アパート|マンション|自宅|帰宅|玄関)",
    "駐車場": r"(?:駐車場|駐輪場)",
    "店舗・商業": r"(?:スーパー|コンビニ|店|ショッピング|商業|商店)",
}
MODUS_PATTERNS = {
    "声かけ型": r"(?:声をかけ|話しかけ|声かけ|呼び止め|声をかけら|声を掛け)",
    "追尾型": r"(?:後をつけ|追いかけ|つきまとい|つきまとわ|ついてく|後を付け|尾行)",
    "接触型": r"(?:体を触|さわ|抱きつ|体に触れ|接触|触られ|触った|身体を触)",
    "露出型": r"(?:下半身|露出|見せ|陰部|裸)",
    "撮影型": r"(?:撮影|カメラ|写真|盗撮|スマホを向け|スマートフォンを向け)",
    "待ち伏せ型": r"(?:待ち伏せ|物陰|陰から|潜ん|隠れ|立ちはだか)",
    "車両使用型": r"(?:車から|自動車|乗れ|乗せてあげ|ワゴン|バン|車で|車両|バイクで)",
    "凶器型": r"(?:包丁|刃物|ナイフ|凶器|金属バット|鉄パイプ|刃物様)",
    "脅迫型": r"(?:脅迫|脅し|殺す|金を出せ|殴るぞ)",
    "侵入型": r"(?:侵入|押し入|忍び込|不法侵入|鍵を開け)",
}
VICTIM_PATTERNS = {
    "小学生": r"(?:小学生|小学校|ランドセル|小さな子|児童|女子児童|男子児童|小学生女児|小学生男児)",
    "中高生": r"(?:中学生|高校生|制服|学生服|女子生徒|男子生徒|女子中学生|女子高校生|女子高生|男子中学生)",
    "女性": r"(?:女性|女の子|女子|女児|20代女性|30代女性)",
    "高齢者": r"(?:高齢|お年寄り|おばあ|おじい|老人|高齢女性|高齢男性)",
    "一人歩き": r"(?:一人で|単独|一人歩き|一人で歩|ひとり|1人で)",
}

MODUS_SEVERITY = {"声かけ型": 1, "待ち伏せ型": 2, "撮影型": 3, "追尾型": 2, "露出型": 3, "接触型": 4, "車両使用型": 4, "凶器型": 5, "脅迫型": 5, "侵入型": 4}

for ev in text_events:
    text = ev["text"]
    ev["time"] = [k for k, p in TIME_PATTERNS.items() if re.search(p, text)]
    ev["location"] = [k for k, p in LOCATION_PATTERNS.items() if re.search(p, text)]
    ev["modus"] = [k for k, p in MODUS_PATTERNS.items() if re.search(p, text)]
    ev["victim"] = [k for k, p in VICTIM_PATTERNS.items() if re.search(p, text)]
    ev["pattern_count"] = sum(len(ev[k]) for k in ["time", "location", "modus", "victim"])
    ev["modus_severity"] = max([MODUS_SEVERITY.get(m, 1) for m in ev["modus"]], default=1)

rich = [e for e in text_events if e["pattern_count"] >= 2]
print(f"\nパターン豊富なイベント: {len(rich)}件 / 全{len(text_events)}件")

# 全体のパターン分布
print("\n=== 全体パターン分布 ===")
for cat in ["time", "location", "modus", "victim"]:
    dist = Counter(v for e in rich for v in e[cat])
    print(f"\n{cat}:")
    for k, c in dist.most_common(10):
        print(f"  {k}: {c}件")

# 問い1: 子供被害
print("\n" + "=" * 60)
print("問い1: 子供被害はいつ・どこで・どんな手口か")
print("=" * 60)
for label, keyword in [("小学生", "小学生"), ("中高生", "中高生")]:
    evs = [e for e in rich if keyword in e.get("victim", [])]
    if not evs:
        print(f"\n{label}: データなし")
        continue
    print(f"\n{label}: {len(evs)}件")
    t_dist = Counter(t for e in evs for t in e["time"])
    print("  時間帯:", [(f"{t}:{c}") for t, c in t_dist.most_common(5)])
    l_dist = Counter(l for e in evs for l in e["location"])
    print("  場所:", [(f"{l}:{c}") for l, c in l_dist.most_common(5)])
    m_dist = Counter(m for e in evs for m in e["modus"])
    print("  手口:", [(f"{m}:{c}") for m, c in m_dist.most_common(5)])
    combo = Counter()
    for e in evs:
        if e["time"] and e["modus"]:
            k = (e["time"][0], e["modus"][0], e["location"][0] if e["location"] else "場所不明")
            combo[k] += 1
    print("  典型パターン Top3:")
    for (t, m, l), c in combo.most_common(3):
        print(f"    {t} × {m} × {l} : {c}件")

# 問い2: 女性深夜
print("\n" + "=" * 60)
print("問い2: 女性深夜被害の手口")
print("=" * 60)
female_night = [e for e in rich if "女性" in e.get("victim", []) and any("夜" in t or "深夜" in t for t in e.get("time", []))]
print(f"女性×夜間/深夜: {len(female_night)}件")
if female_night:
    m_dist = Counter(m for e in female_night for m in e["modus"])
    n = len(female_night)
    print("手口分布:")
    for m, c in m_dist.most_common():
        pct = c / n * 100
        print(f"  {m:<15} {'█' * int(pct / 3):<20} {c}件 ({pct:.0f}%)")
    tracking = sum(1 for e in female_night if "追尾型" in e["modus"])
    ambush = sum(1 for e in female_night if "待ち伏せ型" in e["modus"])
    vehicle = sum(1 for e in female_night if "車両使用型" in e["modus"])
    contact = sum(1 for e in female_night if "接触型" in e["modus"])
    print(f"\n  追尾型: {tracking}/{n} ({tracking / n * 100:.0f}%)")
    print(f"  待ち伏せ型: {ambush}/{n} ({ambush / n * 100:.0f}%)")
    print(f"  車両使用型: {vehicle}/{n} ({vehicle / n * 100:.0f}%)")
    print(f"  接触型: {contact}/{n} ({contact / n * 100:.0f}%)")

# 問い3: エスカレーション
print("\n" + "=" * 60)
print("問い3: 都道府県エスカレーション")
print("=" * 60)
pref_events = defaultdict(list)
for ev in rich:
    if ev.get("pref"):
        pref_events[ev["pref"]].append(ev)

escalation_results = []
for pref, evs in pref_events.items():
    if len(evs) < 5:
        continue
    mid = len(evs) // 2
    early_avg = sum(e["modus_severity"] for e in evs[:mid]) / mid
    recent_avg = sum(e["modus_severity"] for e in evs[mid:]) / (len(evs) - mid)
    if recent_avg > early_avg * 1.15:
        escalation_results.append(
            {
                "pref": pref,
                "early": round(early_avg, 2),
                "recent": round(recent_avg, 2),
                "increase": round((recent_avg - early_avg) / max(early_avg, 0.01) * 100, 1),
                "n": len(evs),
                "latest_modus": [e["modus"][0] for e in evs if e["modus"]][-5:],
            }
        )

escalation_results.sort(key=lambda x: -x["increase"])
if escalation_results:
    print("エスカレーション検知（重篤度上昇15%+）:")
    for r in escalation_results[:10]:
        print(f"  {r['pref']}: {r['early']:.2f}→{r['recent']:.2f} (+{r['increase']:.0f}%, n={r['n']})")
        if r["latest_modus"]:
            print(f"    最近: {' → '.join(r['latest_modus'][-3:])}")
else:
    print("  エスカレーション検知なし")

# 問い4: 声かけ→つきまとい→接触の連鎖
print("\n" + "=" * 60)
print("問い4: 同一エリアでの犯罪段階的悪化")
print("=" * 60)
for pref, evs in pref_events.items():
    if len(evs) < 5:
        continue
    sevs = [e["modus_severity"] for e in evs]
    n = len(sevs)
    ranks = list(range(n))
    d_sq = sum((i - sorted(range(n), key=lambda j: sevs[j]).index(i)) ** 2 for i in range(n))
    corr = 1 - 6 * d_sq / (n * (n**2 - 1)) if n > 1 else 0
    if corr > 0.3:
        seq = [e["modus"][0] for e in evs if e["modus"]][-5:]
        if seq:
            print(f"  {pref}: 相関={corr:.2f} 手口推移: {' → '.join(seq)}")

# 保存
output = {
    "generated_at": str(datetime.now()),
    "total_text_events": len(text_events),
    "rich_events": len(rich),
    "source_counts": {src: sum(1 for e in text_events if e["source"] == src) for src in set(e["source"] for e in text_events)},
    "child_elementary": len([e for e in rich if "小学生" in e.get("victim", [])]),
    "child_teen": len([e for e in rich if "中高生" in e.get("victim", [])]),
    "female_night": len(female_night),
    "escalation_prefs": escalation_results,
}
with open("data/analysis/crime_qualitative/text_analysis_v2.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print("\n保存完了: data/analysis/crime_qualitative/text_analysis_v2.json")
