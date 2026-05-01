#!/usr/bin/env python3
"""
Deep crawl v3 - Streamlined based on v1/v2 learnings.
Key fixes: NO Gaccom sub-links (they timeout), strict timeouts, faster flow.
"""

import json, time, re, os, hashlib, shutil
from datetime import datetime, timedelta
from urllib.parse import quote, urljoin
from pathlib import Path
import requests
from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parent

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en;q=0.5",
}
S = requests.Session()
S.headers.update(HEADERS)

all_events = []
all_fushinsha = []
stats = {}

def get(url, t=8):
    try:
        r = S.get(url, timeout=t, allow_redirects=True)
        return r if r.status_code == 200 else None
    except:
        return None

def mkid(pfx, *p):
    return f"{pfx}_{hashlib.md5(':'.join(str(x) for x in p).encode()).hexdigest()[:12]}"

def mkevent(name, date, loc, cat="event", crowd=None, cm=1.0, im=1.0, src=""):
    e = {"id": mkid("ev", name, date, loc), "name": name, "date": date,
         "location": loc, "category": cat, "source": src,
         "crowd_multiplier": cm, "incident_multiplier": im}
    if crowd: e["expected_crowd"] = crowd
    return e

def mkfs(title, date, pref, city="", ftype="不審者", src=""):
    return {"id": mkid("fs", title, date), "title": title, "date": date,
            "prefecture": pref, "city": city, "type": ftype, "source": src}

PREFS = "北海道 青森 岩手 宮城 秋田 山形 福島 茨城 栃木 群馬 埼玉 千葉 東京 神奈川 新潟 富山 石川 福井 山梨 長野 岐阜 静岡 愛知 三重 滋賀 京都 大阪 兵庫 奈良 和歌山 鳥取 島根 岡山 広島 山口 徳島 香川 愛媛 高知 福岡 佐賀 長崎 熊本 大分 宮崎 鹿児島 沖縄".split()

def fpref(t):
    for p in PREFS:
        if p in t: return p
    return ""

def ftype(t):
    for k, v in [("痴漢","痴漢"),("声かけ","声かけ"),("露出","露出"),("つきまとい","つきまとい"),
                 ("盗撮","盗撮"),("クマ","クマ出没"),("熊","クマ出没"),("詐欺","特殊詐欺"),
                 ("ひったくり","ひったくり"),("空き巣","窃盗"),("窃盗","窃盗"),("暴行","暴行"),
                 ("強盗","強盗"),("器物","器物損壊"),("不審","不審者")]:
        if k in t: return v
    return "不審者"

# ============ PART 1: J-LEAGUE ============
def p1_jleague():
    print("\n=== PART 1: J-LEAGUE ===")
    m = []
    # Monthly search (worked: 211+187+3+3+3+8+3+3+3 from v1)
    for mo in range(1, 13):
        r = get(f"https://www.jleague.jp/match/search?year=2026&month={mo}")
        time.sleep(1.2)
        if not r: continue
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select("[class*=match]"):
            t = card.get_text(" ", strip=True)
            if len(t) < 5: continue
            dm = re.search(r'(\d{1,2})/(\d{1,2})', t)
            d = f"2026-{mo:02d}-{int(dm.group(2)):02d}" if dm else f"2026-{mo:02d}-15"
            m.append(mkevent(t[:100], d, "Japan", "sports_jleague", 20000, 2.0, 1.3, "jleague.jp"))
        print(f"  month {mo}: {len(soup.select('[class*=match]'))} elements")

    # Section pages J1 (1-18 worked, 19+ was 404)
    for sec in range(1, 20):
        r = get(f"https://www.jleague.jp/match/section/j1/{sec}/", 6)
        time.sleep(0.8)
        if not r: continue
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select("[class*=match]"):
            t = card.get_text(" ", strip=True)
            if len(t) < 5: continue
            dm = re.search(r'(\d{1,2})/(\d{1,2})', t)
            d = f"2026-{int(dm.group(1)):02d}-{int(dm.group(2)):02d}" if dm else "2026-06-15"
            m.append(mkevent(f"[J1 第{sec}節] {t[:80]}", d, "Japan", "sports_j1", 20000, 2.0, 1.3, "jleague.jp/j1"))

    # Dedup
    seen = set()
    u = [x for x in m if (k := x["name"][:50]+x["date"]) not in seen and not seen.add(k)]
    print(f"  J-LEAGUE: {len(u)}")
    stats["jleague"] = len(u)
    all_events.extend(u)

# ============ PART 2: NPB ============
def p2_npb():
    print("\n=== PART 2: NPB ===")
    g = []
    TEAMS = {"巨人":"東京ドーム","ヤクルト":"神宮球場","DeNA":"横浜スタジアム",
             "阪神":"甲子園球場","広島":"マツダスタジアム","中日":"バンテリンドーム",
             "オリックス":"京セラドーム","ソフトバンク":"PayPayドーム","西武":"ベルーナドーム",
             "楽天":"楽天モバイルパーク","ロッテ":"ZOZOマリンスタジアム","日本ハム":"エスコンフィールド"}

    for mo in range(3, 11):
        for sfx in [f"schedule_{mo:02d}.html", f"schedule_{mo:02d}_detail.html"]:
            r = get(f"https://npb.jp/games/2026/{sfx}")
            time.sleep(1.0)
            if not r: continue
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")
            cnt = 0
            for el in soup.find_all(["tr","div","li","td","dd"], limit=1000):
                t = el.get_text(" ", strip=True)
                ft = [tm for tm in TEAMS if tm in t]
                if ft and 10 < len(t) < 300:
                    dm = re.search(r'(\d{1,2})月(\d{1,2})日|(\d{1,2})/(\d{1,2})', t)
                    if dm:
                        mv = dm.group(1) or dm.group(3)
                        dv = dm.group(2) or dm.group(4)
                        d = f"2026-{int(mv):02d}-{int(dv):02d}"
                    else:
                        d = f"2026-{mo:02d}-15"
                    g.append(mkevent(t[:120], d, TEAMS.get(ft[0],"Japan"), "sports_npb", 30000, 2.0, 1.2, "npb.jp"))
                    cnt += 1
            print(f"  {sfx}: {cnt}")

    # Playoff pages
    for pg in ["schedule_climax_cl.html","schedule_climax_pl.html"]:
        r = get(f"https://npb.jp/games/2026/{pg}")
        time.sleep(0.8)
        if r:
            soup = BeautifulSoup(r.text, "html.parser")
            for el in soup.find_all(["tr","div","li"], limit=300):
                t = el.get_text(" ", strip=True)
                if any(tm in t for tm in TEAMS) and 10 < len(t) < 200:
                    g.append(mkevent(t[:120], "2026-10-15", "Japan", "sports_npb_playoff", 40000, 2.5, 1.4, "npb.jp"))

    seen = set()
    u = [x for x in g if (k := x["name"][:60]) not in seen and not seen.add(k)]
    print(f"  NPB: {len(u)}")
    stats["npb"] = len(u)
    all_events.extend(u)

# ============ PART 3: EVENTS ============
def p3_events():
    print("\n=== PART 3: EVENTS ===")
    ev = []

    # Walker+ main pages (1-20)
    print("  Walker+ main...")
    for pg in range(1, 20):
        url = "https://www.walkerplus.com/event_list/" if pg == 1 else f"https://www.walkerplus.com/event_list/?page={pg}"
        r = get(url)
        time.sleep(1.2)
        if not r: break
        soup = BeautifulSoup(r.text, "html.parser")
        cnt = 0
        for link in soup.find_all("a", href=True):
            title = link.get_text(strip=True)
            if "/event/" in link["href"] and "event_list" not in link["href"] and 5 < len(title) < 100:
                ev.append(mkevent(title[:120], "2026-06-01", "Japan", "event_festival", 5000, 1.5, 1.1, "walkerplus.com"))
                cnt += 1
        if cnt == 0 and pg > 2: break
        print(f"    page {pg}: {cnt}")

    # Walker+ regions that worked (ar0313=Tokyo, ar0101=Hokkaido)
    for rid, rn in [("ar0313","東京"),("ar0101","北海道")]:
        r = get(f"https://www.walkerplus.com/event_list/{rid}/")
        time.sleep(1.2)
        if r:
            soup = BeautifulSoup(r.text, "html.parser")
            cnt = 0
            for link in soup.find_all("a", href=True):
                title = link.get_text(strip=True)
                if "/event/" in link["href"] and 5 < len(title) < 100:
                    ev.append(mkevent(title[:120], "2026-06-01", rn, "event_festival", 5000, 1.5, 1.1, "walkerplus.com"))
                    cnt += 1
            print(f"    {rn}: {cnt}")

    # Hanabi (each page gave 16 in v2)
    print("  Hanabi...")
    for pg in range(1, 20):
        url = "https://hanabi.walkerplus.com/list/" if pg == 1 else f"https://hanabi.walkerplus.com/list/?page={pg}"
        r = get(url)
        time.sleep(1.2)
        if not r: break
        soup = BeautifulSoup(r.text, "html.parser")
        cnt = 0
        for link in soup.find_all("a", href=True):
            title = link.get_text(strip=True)
            if ("/detail/" in link["href"] or "/hanabi/" in link["href"]) and len(title) > 5:
                ev.append(mkevent(title[:120], "2026-08-01", "Japan", "event_hanabi", 50000, 3.0, 1.5, "hanabi.walkerplus.com"))
                cnt += 1
        if cnt == 0 and pg > 2: break
        print(f"    page {pg}: {cnt}")

    # Jalan events for top prefectures
    print("  Jalan...")
    for pid, pn in [("130000","東京"),("270000","大阪"),("140000","神奈川"),
                     ("230000","愛知"),("400000","福岡"),("010000","北海道"),
                     ("260000","京都"),("280000","兵庫"),("110000","埼玉"),("120000","千葉")]:
        r = get(f"https://www.jalan.net/event/evt_list.html?screenId=OUW2801&ken={pid}")
        time.sleep(1.5)
        if not r: continue
        soup = BeautifulSoup(r.text, "html.parser")
        cnt = 0
        for el in soup.find_all(["h2","h3","a"]):
            t = el.get_text(strip=True)
            href = el.get("href", "")
            if 8 < len(t) < 100 and ("event" in href or any(k in t for k in ["祭","花火","まつり","フェス","イベント","市"])):
                ev.append(mkevent(t[:120], "2026-06-01", pn, "event_festival", 5000, 1.5, 1.1, "jalan.net"))
                cnt += 1
        if cnt: print(f"    {pn}: {cnt}")

    # Jorudan events
    print("  Jorudan...")
    for pref in ["tokyo","osaka","kanagawa","aichi","saitama","chiba","fukuoka","hokkaido","hyogo","kyoto"]:
        r = get(f"https://www.jorudan.co.jp/event/{pref}/")
        time.sleep(1.2)
        if not r: continue
        soup = BeautifulSoup(r.text, "html.parser")
        cnt = 0
        for link in soup.find_all("a", href=True):
            title = link.get_text(strip=True)
            if "/event/" in link["href"] and pref in link["href"] and 5 < len(title) < 100:
                ev.append(mkevent(title[:120], "2026-06-01", pref, "event_festival", 5000, 1.5, 1.1, "jorudan.co.jp"))
                cnt += 1
        if cnt: print(f"    {pref}: {cnt}")

    # RuruBu monthly events (Tokyo + Osaka + Aichi)
    print("  RuruBu...")
    for kencd, kname in [("13","東京"),("27","大阪"),("23","愛知"),("14","神奈川"),("01","北海道")]:
        for mo in range(4, 13):
            r = get(f"https://www.rurubu.com/event/list.aspx?KenCD={kencd}&Month={mo}")
            time.sleep(1.0)
            if not r: continue
            soup = BeautifulSoup(r.text, "html.parser")
            cnt = 0
            for link in soup.find_all("a", href=True):
                title = link.get_text(strip=True)
                if "event" in link["href"].lower() and 5 < len(title) < 100:
                    ev.append(mkevent(title[:120], f"2026-{mo:02d}-15", kname, "event_festival", 5000, 1.5, 1.1, "rurubu.com"))
                    cnt += 1
            if cnt: print(f"    {kname} month {mo}: {cnt}")

    seen = set()
    u = [x for x in ev if (k := x["name"]) not in seen and not seen.add(k)]
    print(f"  EVENTS: {len(u)}")
    stats["events"] = len(u)
    all_events.extend(u)

# ============ PART 4: FUSHINSHA ============
def p4_fushinsha():
    print("\n=== PART 4: FUSHINSHA NEWS ===")
    arts = []

    # Yahoo News (worked well: ~20-52 per keyword per search in v2)
    print("  Yahoo News...")
    kw_pages = [("不審者",20),("痴漢",15),("声かけ事案",15),("クマ出没",10),
                ("つきまとい",10),("盗撮",10),("露出狂",5),("ひったくり",10),
                ("窃盗事件",10),("暴行事件",10),("強盗事件",10),("特殊詐欺",10),
                ("不審火",5),("変質者",5),("器物損壊",5)]
    for kw, mp in kw_pages:
        enc = quote(kw)
        kwt = 0
        for pg in range(1, mp + 1):
            st = (pg - 1) * 10 + 1
            r = get(f"https://news.yahoo.co.jp/search?p={enc}&ei=UTF-8&b={st}")
            time.sleep(1.0)
            if not r: break
            soup = BeautifulSoup(r.text, "html.parser")
            found = 0
            # Try structured selectors
            for sel in [".newsFeed_item","article","[class*=news]","[class*=article]","li[class*=item]",".sw-Card"]:
                items = soup.select(sel)
                if items and len(items) >= 2:
                    for it in items:
                        te = it.select_one("h2,h3,.title,a")
                        title = te.get_text(strip=True) if te else ""
                        if len(title) < 8: continue
                        txt = it.get_text(" ", strip=True)
                        dm = re.search(r'(\d{1,2})/(\d{1,2})', txt)
                        d = f"2026-{int(dm.group(1)):02d}-{int(dm.group(2)):02d}" if dm else "2026-04-01"
                        arts.append(mkfs(title[:150], d, fpref(title+txt), ftype=ftype(title+txt), src="news.yahoo.co.jp"))
                        found += 1
                    break
            # Fallback: links with article-like content
            if found == 0:
                for link in soup.find_all("a", href=True):
                    title = link.get_text(strip=True)
                    if 15 < len(title) < 200 and any(k in title for k in [kw[:2],"事件","事案","逮捕","容疑"]):
                        arts.append(mkfs(title[:150], "2026-04-01", fpref(title), ftype=ftype(title), src="news.yahoo.co.jp"))
                        found += 1
            kwt += found
            if found == 0 and pg > 2: break
        print(f"    [{kw}]: {kwt}")

    # Google News (worked well: 60-99 per keyword)
    print("  Google News...")
    for kw in ["不審者情報","痴漢情報","声かけ事案","クマ目撃","つきまとい被害",
               "盗撮事件","特殊詐欺被害","ひったくり発生","不審者出没","露出事案",
               "暴行事件","窃盗事件","強盗事件","器物損壊","変質者"]:
        r = get(f"https://news.google.com/search?q={quote(kw)}&hl=ja&gl=JP&ceid=JP:ja")
        time.sleep(2)
        if not r: continue
        soup = BeautifulSoup(r.text, "html.parser")
        cnt = 0
        for link in soup.find_all("a"):
            title = link.get_text(strip=True)
            if 15 < len(title) < 200 and any(k in title for k in
                ["不審","痴漢","声かけ","クマ","事案","犯罪","逮捕","容疑","詐欺",
                 "盗撮","つきまとい","露出","ひったくり","窃盗","暴行","強盗","事件","火災"]):
                arts.append(mkfs(title[:150], "2026-04-01", fpref(title), ftype=ftype(title), src="news.google.com"))
                cnt += 1
        print(f"    [{kw}]: {cnt}")

    # Gaccom (main pages only, NO sub-links)
    print("  Gaccom...")
    for pid, pn in [("13","東京"),("27","大阪"),("14","神奈川"),("23","愛知"),
                     ("11","埼玉"),("12","千葉"),("40","福岡"),("01","北海道"),
                     ("28","兵庫"),("22","静岡"),("26","京都"),("34","広島"),
                     ("04","宮城"),("08","茨城"),("09","栃木")]:
        r = get(f"https://www.gaccom.jp/safety/area/p{pid}")
        time.sleep(1.5)
        if not r: continue
        soup = BeautifulSoup(r.text, "html.parser")
        cnt = 0
        for el in soup.find_all(["li","div","article","tr","p","dd"], limit=500):
            t = el.get_text(" ", strip=True)
            if 15 < len(t) < 500 and any(k in t for k in
                ["不審者","声かけ","痴漢","窃盗","事案","露出","つきまとい","盗撮","暴行","詐欺","クマ","犯罪","ひったくり","強盗"]):
                te = el.find(["a","h3","h2"])
                title = te.get_text(strip=True) if te else t[:80]
                dm = re.search(r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})', t)
                d = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}" if dm else "2026-04-01"
                arts.append(mkfs(title[:150], d, pn, ftype=ftype(t), src="gaccom.jp"))
                cnt += 1
        if cnt: print(f"    [{pn}]: {cnt}")

    # Mainichi / Sankei
    print("  Newspapers...")
    for base, src in [("https://mainichi.jp/search?q={}&p={}","mainichi.jp"),
                       ("https://www.sankei.com/search/?q={}&page={}","sankei.com")]:
        for kw in ["不審者","痴漢","声かけ","クマ出没","特殊詐欺"]:
            for pg in range(1, 4):
                r = get(base.format(quote(kw), pg))
                time.sleep(1.5)
                if not r: break
                soup = BeautifulSoup(r.text, "html.parser")
                cnt = 0
                for link in soup.find_all("a"):
                    title = link.get_text(strip=True)
                    if 15 < len(title) < 200 and any(k in title for k in
                        ["不審","痴漢","声かけ","事件","逮捕","犯罪","詐欺","クマ","窃盗"]):
                        arts.append(mkfs(title[:150], "2026-04-01", fpref(title), ftype=ftype(title), src=src))
                        cnt += 1
                if cnt == 0 and pg > 1: break

    # NHK
    print("  NHK...")
    for kw in ["不審者","痴漢","声かけ","クマ出没","特殊詐欺","ひったくり"]:
        r = get(f"https://www3.nhk.or.jp/news/json/search/v2/?keyword={quote(kw)}&page=1&sort=date")
        time.sleep(1.5)
        if not r: continue
        try:
            data = r.json()
            items = data.get("result",{}).get("items",[])
            for it in items:
                title = it.get("title","")
                date = it.get("pubDate","")[:10]
                arts.append(mkfs(title[:150], date, fpref(title), ftype=ftype(title), src="nhk.or.jp"))
            if items: print(f"    [{kw}]: {len(items)}")
        except:
            pass

    seen = set()
    u = [x for x in arts if (k := x["title"]) not in seen and not seen.add(k)]
    print(f"  FUSHINSHA NEWS: {len(u)}")
    stats["fushinsha_news"] = len(u)
    all_fushinsha.extend(u)

# ============ PART 5: POLICE ============
def p5_police():
    print("\n=== PART 5: POLICE ===")
    reps = []
    crime_kw = ["不審","声かけ","痴漢","事案","露出","つきまとい","盗撮","犯罪","詐欺","クマ","ひったくり","前兆"]

    configs = [
        ("東京","https://www.keishicho.metro.tokyo.lg.jp",["/kurashi/anzen/index.html"]),
        ("大阪","https://www.police.pref.osaka.lg.jp",["/bouhan/index.html","/seikatsu/anzen/index.html"]),
        ("神奈川","https://www.police.pref.kanagawa.jp",["/"]),
        ("埼玉","https://www.police.pref.saitama.lg.jp",["/"]),
        ("千葉","https://www.police.pref.chiba.jp",["/"]),
        ("福岡","https://www.police.pref.fukuoka.jp",["/"]),
        ("北海道","https://www.police.pref.hokkaido.lg.jp",["/info/seianbu/fusin/index.html"]),
        ("兵庫","https://www.police.pref.hyogo.lg.jp",["/"]),
    ]

    for pref, base, paths in configs:
        cnt = 0
        for path in paths:
            r = get(base + path, 8)
            time.sleep(1.5)
            if not r: continue
            for enc in ["utf-8","shift_jis","euc-jp"]:
                try: r.encoding = enc; _ = r.text[:200]; break
                except: continue
            soup = BeautifulSoup(r.text, "html.parser")

            for el in soup.find_all(["li","tr","dd","p","div","article","td"], limit=500):
                t = el.get_text(" ", strip=True)
                if 15 < len(t) < 500 and any(k in t for k in crime_kw):
                    dm = re.search(r'(\d{1,2})月(\d{1,2})日|(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})', t)
                    if dm:
                        d = f"2026-{int(dm.group(1)):02d}-{int(dm.group(2)):02d}" if dm.group(1) else f"{dm.group(3)}-{int(dm.group(4)):02d}-{int(dm.group(5)):02d}"
                    else:
                        d = "2026-04-01"
                    reps.append(mkfs(t[:150], d, pref, ftype=ftype(t), src=base))
                    cnt += 1

            # Follow 5 sub-links max
            subs = set()
            for link in soup.find_all("a", href=True):
                lt = link.get_text(strip=True) + link["href"]
                if any(k in lt for k in ["不審","前兆","犯罪","事案","声かけ","安全","fushin","precrime","anzen","bouhan"]):
                    fu = urljoin(base + path, link["href"])
                    if fu.startswith("http") and fu != base + path:
                        subs.add(fu)
            for su in list(subs)[:5]:
                r2 = get(su, 6)
                time.sleep(0.8)
                if not r2: continue
                s2 = BeautifulSoup(r2.text, "html.parser")
                for el in s2.find_all(["li","tr","dd","p","div"], limit=300):
                    t = el.get_text(" ", strip=True)
                    if 10 < len(t) < 500 and any(k in t for k in crime_kw):
                        reps.append(mkfs(t[:150], "2026-04-01", pref, ftype=ftype(t), src=su))
                        cnt += 1
        print(f"  [{pref}]: {cnt}")

    seen = set()
    u = [x for x in reps if (k := x["title"]) not in seen and not seen.add(k)]
    print(f"  POLICE: {len(u)}")
    stats["police"] = len(u)
    all_fushinsha.extend(u)

# ============ MAIN ============
def main():
    t0 = time.time()
    print("="*50)
    print("RISK SPACE DEEP CRAWL v3")
    print(f"Started: {datetime.now().isoformat()}")
    print("="*50)

    p1_jleague()
    p2_npb()
    p3_events()
    p4_fushinsha()
    p5_police()

    # Dedup all
    se = set()
    ue = [x for x in all_events if (k := x["name"][:60]) not in se and not se.add(k)]
    sf = set()
    uf = [x for x in all_fushinsha if (k := x["title"]) not in sf and not sf.add(k)]

    elapsed = time.time() - t0

    # Save events
    eo = {"crawl_date": datetime.now().isoformat(), "crawl_version": "v3_deep",
          "crawl_duration_seconds": round(elapsed), "total_events": len(ue),
          "sources": {k:v for k,v in stats.items() if "fushinsha" not in k and "police" not in k},
          "events": ue}
    ep = BASE / "data/dynamic/events/all_events_v2.json"
    with open(ep, "w", encoding="utf-8") as f:
        json.dump(eo, f, ensure_ascii=False, indent=2)

    # Save fushinsha
    fo = {"crawl_date": datetime.now().isoformat(), "crawl_version": "v3_deep",
          "crawl_duration_seconds": round(elapsed), "total_reports": len(uf),
          "sources": {k:v for k,v in stats.items() if "fushinsha" in k or "police" in k},
          "reports": uf}
    fp = BASE / "data/realtime/fushinsha_7days/deep_crawl.json"
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(fo, f, ensure_ascii=False, indent=2)

    # Copy to docs/data
    dd = BASE / "docs/data"
    shutil.copy2(ep, dd / "all_events_v2.json")
    shutil.copy2(fp, dd / "deep_crawl.json")

    print("\n" + "="*50)
    print("FINAL RESULTS")
    print("="*50)
    print(f"  Events:     {len(ue)}")
    print(f"  Fushinsha:  {len(uf)}")
    print(f"  TOTAL:      {len(ue) + len(uf)}")
    print(f"  Duration:   {elapsed:.0f}s ({elapsed/60:.1f}min)")
    print("\nSource breakdown:")
    for s, c in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {s:25s}: {c:6d}")

    cc = {}
    for e in ue:
        cat = e.get("category","?")
        cc[cat] = cc.get(cat, 0) + 1
    print("\nEvent categories:")
    for c, n in sorted(cc.items(), key=lambda x: -x[1]):
        print(f"  {c:30s}: {n:6d}")

    tc = {}
    for f in uf:
        t = f.get("type","?")
        tc[t] = tc.get(t, 0) + 1
    print("\nFushinsha types:")
    for t, n in sorted(tc.items(), key=lambda x: -x[1]):
        print(f"  {t:25s}: {n:6d}")

    print(f"\nSaved to:")
    print(f"  {ep}")
    print(f"  {fp}")
    print(f"  {dd / 'all_events_v2.json'}")
    print(f"  {dd / 'deep_crawl.json'}")

if __name__ == "__main__":
    main()
