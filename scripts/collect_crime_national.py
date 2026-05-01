"""
全国犯罪データ収集スクリプト (Step 2〜6統合)
"""
import requests, json, time, re, os, sys
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter
import chardet
import pandas as pd

BASE = Path("/Users/reikumaki/Library/CloudStorage/GoogleDrive-teddykmk@gmail.com/マイドライブ/piracy_detector/claude_code/risk_space")
os.chdir(BASE)

headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# =====================================================================
# Step 2: 警察庁リンク集 + 47都道府県クロール
# =====================================================================
print("=" * 60)
print("Step 2: 47都道府県 犯罪オープンデータ収集")
print("=" * 60)

LINK_COLLECTION_URL = "https://www.npa.go.jp/bureau/safetylife/seianki/bouhan/opendata.html"

PREF_SOURCES = [
    {"pref": "東京都", "code": "13", "status": "done"},
    {"pref": "大阪府", "code": "27", "urls": [
        "https://www.police.pref.osaka.lg.jp/seikatsu/bouhan/10956.html",
        "https://www.police.pref.osaka.lg.jp/seikatsu/bouhan/",
    ]},
    {"pref": "神奈川県", "code": "14", "urls": [
        "https://www.police.pref.kanagawa.jp/mes/faq60030.htm",
        "https://www.police.pref.kanagawa.jp/mes/",
    ]},
    {"pref": "愛知県", "code": "23", "urls": [
        "https://www.pref.aichi.jp/police/anzen/bouhan/data/",
        "https://www.police.pref.aichi.jp/",
    ]},
    {"pref": "福岡県", "code": "40", "urls": [
        "https://www.police.pref.fukuoka.jp/kikaku/opendata/index.html",
        "https://www.police.pref.fukuoka.jp/kikaku/opendata/",
    ]},
    {"pref": "埼玉県", "code": "11", "urls": [
        "https://www.police.pref.saitama.lg.jp/f0010/bouhan/hasseijouho/",
    ]},
    {"pref": "千葉県", "code": "12", "urls": [
        "https://www.police.pref.chiba.jp/seianki/bouhan/opendata.html",
        "https://www.police.pref.chiba.jp/seianki/",
    ]},
    {"pref": "兵庫県", "code": "28", "urls": [
        "https://www.police.pref.hyogo.lg.jp/kikaku/opendata/index.html",
    ]},
    {"pref": "北海道", "code": "01", "urls": [
        "https://www.police.pref.hokkaido.lg.jp/info/kikaku/opendata/opendata.html",
    ]},
    {"pref": "京都府", "code": "26", "urls": [
        "https://www.pref.kyoto.jp/fukei/anzen/bouhan/opendata.html",
    ]},
    {"pref": "静岡県", "code": "22", "urls": [
        "https://www.police.pref.shizuoka.jp/about/release/opendata/",
    ]},
    {"pref": "茨城県", "code": "08", "urls": [
        "https://www.police.pref.ibaraki.jp/opendata/",
    ]},
    {"pref": "広島県", "code": "34", "urls": [
        "https://www.pref.hiroshima.lg.jp/site/police/",
    ]},
    {"pref": "宮城県", "code": "04", "urls": [
        "https://www.police.pref.miyagi.jp/index2/kikaku/open_data/",
    ]},
]

# Add remaining 33 prefectures
remaining = [
    ("青森県","02","aomori"), ("岩手県","03","iwate"), ("秋田県","05","akita"),
    ("山形県","06","yamagata"), ("福島県","07","fukushima"), ("栃木県","09","tochigi"),
    ("群馬県","10","gunma"), ("新潟県","15","niigata"), ("富山県","16","toyama"),
    ("石川県","17","ishikawa"), ("福井県","18","fukui"), ("山梨県","19","yamanashi"),
    ("長野県","20","nagano"), ("岐阜県","21","gifu"), ("三重県","24","mie"),
    ("滋賀県","25","shiga"), ("奈良県","29","nara"), ("和歌山県","30","wakayama"),
    ("鳥取県","31","tottori"), ("島根県","32","shimane"), ("岡山県","33","okayama"),
    ("山口県","35","yamaguchi"), ("徳島県","36","tokushima"), ("香川県","37","kagawa"),
    ("愛媛県","38","ehime"), ("高知県","39","kochi"), ("佐賀県","41","saga"),
    ("長崎県","42","nagasaki"), ("熊本県","43","kumamoto"), ("大分県","44","oita"),
    ("宮崎県","45","miyazaki"), ("鹿児島県","46","kagoshima"), ("沖縄県","47","okinawa"),
]

for p, c, domain in remaining:
    PREF_SOURCES.append({
        "pref": p, "code": c, "urls": [
            f"https://www.police.pref.{domain}.jp/kikaku/opendata/",
            f"https://www.police.pref.{domain}.jp/",
        ]
    })


def find_csv_links(url, pref):
    """ページからCSV/XLSXリンクを探す"""
    try:
        r = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "lxml")
        links = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if any(ext in href.lower() for ext in [".csv", ".xlsx", ".xls", ".zip"]):
                if href.startswith("http"):
                    full_url = href
                elif href.startswith("/"):
                    parts = url.split("/")
                    full_url = f"{parts[0]}//{parts[2]}{href}"
                else:
                    full_url = f"{'/'.join(url.split('/')[:-1])}/{href}"
                if full_url not in seen:
                    seen.add(full_url)
                    links.append({"url": full_url, "text": text})
        return links
    except Exception as e:
        return []


def download_file(url, save_path):
    """ファイルをダウンロード"""
    try:
        r = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        if r.status_code == 200 and len(r.content) > 100:
            # Check if it's actually HTML (error page)
            ct = r.headers.get("Content-Type", "")
            if "text/html" in ct and not url.endswith(".html"):
                return False
            with open(save_path, "wb") as f:
                f.write(r.content)
            return True
    except:
        pass
    return False


# First: get NPA link collection
print("\n--- 警察庁リンク集を取得中 ---")
npa_links = []
try:
    r = requests.get(LINK_COLLECTION_URL, headers=headers, timeout=15)
    if r.status_code == 200:
        soup = BeautifulSoup(r.text, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if any(kw in href for kw in ["police.pref", "opendata", ".csv"]):
                full = href if href.startswith("http") else f"https://www.npa.go.jp{href}"
                npa_links.append({"url": full, "text": text})
        print(f"  警察庁リンク集: {len(npa_links)}件発見")
    else:
        print(f"  警察庁リンク集: HTTP {r.status_code}")
except Exception as e:
    print(f"  警察庁リンク集取得失敗: {e}")

Path("data/crime/national").mkdir(parents=True, exist_ok=True)
with open("data/crime/national/npa_links.json", "w", encoding="utf-8") as f:
    json.dump(npa_links, f, ensure_ascii=False, indent=2)

# Also try to find CSV links from NPA page directly
npa_csvs = [l for l in npa_links if any(ext in l["url"].lower() for ext in [".csv", ".xlsx"])]
if npa_csvs:
    print(f"  警察庁直接CSV: {len(npa_csvs)}件")
    npa_dir = Path("data/crime/national")
    for link in npa_csvs[:20]:
        fname = link["url"].split("/")[-1].split("?")[0]
        if download_file(link["url"], npa_dir / fname):
            print(f"    DL成功: {fname}")
        time.sleep(1)

# Prefecture-level crawl
results = {}
total_files = 0

for source in PREF_SOURCES:
    pref = source["pref"]
    if source.get("status") == "done":
        print(f"\n{pref}: 取得済みスキップ")
        results[pref] = {"status": "done", "files": 0, "rows": 0}
        continue

    print(f"\n{pref} 処理中...")
    pref_dir = Path(f"data/crime/prefectures/{pref}")
    pref_dir.mkdir(parents=True, exist_ok=True)

    all_csv_links = []
    for url in source.get("urls", []):
        links = find_csv_links(url, pref)
        all_csv_links.extend(links)
        time.sleep(1.5)

        # If first page has sub-pages with opendata/crime links, follow them
        if not links:
            try:
                r = requests.get(url, headers=headers, timeout=15)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "lxml")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        text = a.get_text(strip=True)
                        if any(kw in text for kw in ["オープンデータ", "犯罪", "統計", "発生"]) or \
                           any(kw in href for kw in ["opendata", "hanzai", "bouhan", "tokei", "hassei"]):
                            if href.startswith("http"):
                                sub_url = href
                            elif href.startswith("/"):
                                parts = url.split("/")
                                sub_url = f"{parts[0]}//{parts[2]}{href}"
                            else:
                                sub_url = f"{'/'.join(url.split('/')[:-1])}/{href}"
                            sub_links = find_csv_links(sub_url, pref)
                            all_csv_links.extend(sub_links)
                            time.sleep(1)
                            if sub_links:
                                break
            except:
                pass

    # Deduplicate
    seen_urls = set()
    unique_links = []
    for l in all_csv_links:
        if l["url"] not in seen_urls:
            seen_urls.add(l["url"])
            unique_links.append(l)
    all_csv_links = unique_links

    if not all_csv_links:
        print(f"  {pref}: CSVリンク見つからず")
        results[pref] = {"status": "no_links", "files": 0, "rows": 0}
        continue

    print(f"  {pref}: {len(all_csv_links)}件のファイルリンク発見")
    downloaded = []
    total_rows = 0

    for link in all_csv_links[:15]:  # Max 15 files per prefecture
        fname = link["url"].split("/")[-1].split("?")[0]
        if not fname or len(fname) < 3:
            fname = f"data_{len(downloaded)}.csv"
        save_path = pref_dir / fname

        if download_file(link["url"], save_path):
            # Try to count rows
            rows = 0
            if fname.endswith(".csv"):
                try:
                    with open(save_path, "rb") as f:
                        raw = f.read()
                    enc = chardet.detect(raw[:10000])["encoding"] or "cp932"
                    df = pd.read_csv(save_path, encoding=enc, low_memory=False)
                    rows = len(df)
                    total_rows += rows
                except:
                    try:
                        rows = sum(1 for _ in open(save_path, "rb")) - 1
                        total_rows += max(0, rows)
                    except:
                        pass

            downloaded.append({"file": fname, "rows": rows})
            print(f"    DL成功: {fname} ({rows}行)")
            total_files += 1
        time.sleep(1.5)

    results[pref] = {
        "status": "success" if downloaded else "failed",
        "files": len(downloaded),
        "rows": total_rows,
        "details": downloaded,
    }

with open("data/crime/prefectures/collection_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

success = sum(1 for v in results.values() if v["status"] == "success")
done = sum(1 for v in results.values() if v["status"] == "done")
no_links = sum(1 for v in results.values() if v["status"] == "no_links")
total_rows = sum(v.get("rows", 0) for v in results.values())
print(f"\n--- Step 2 完了 ---")
print(f"  成功: {success}府県 / 取得済み: {done} / リンクなし: {no_links}")
print(f"  総ファイル数: {total_files}")
print(f"  総レコード数: {total_rows:,}")

# =====================================================================
# Step 3: e-Stat API補完
# =====================================================================
print("\n" + "=" * 60)
print("Step 3: e-Stat API 犯罪統計補完")
print("=" * 60)

# Check if we have an e-Stat API key from previous work
estat_key = None
estat_key_paths = [
    BASE / "data" / "estat_appid.txt",
    BASE / ".estat_key",
    Path.home() / ".estat_key",
]
for p in estat_key_paths:
    if p.exists():
        estat_key = p.read_text().strip()
        break

# Also check environment
if not estat_key:
    estat_key = os.environ.get("ESTAT_APP_ID", "")

# Try to find it from previous API calls in the codebase
if not estat_key:
    for f in BASE.glob("scripts/*.py"):
        try:
            content = f.read_text()
            m = re.search(r'appId["\s:=]+([a-f0-9]{32,})', content)
            if m:
                estat_key = m.group(1)
                break
        except:
            pass

# Also check existing e-Stat data
if not estat_key:
    for f in (BASE / "data").rglob("*estat*"):
        try:
            content = f.read_text()
            m = re.search(r'appId["\s:=]+([a-f0-9]{32,})', content)
            if m:
                estat_key = m.group(1)
                break
        except:
            pass

ESTAT_TARGETS = [
    {"id": "0000010111", "name": "犯罪統計（社会・人口統計体系）"},
    {"id": "0003348499", "name": "刑法犯認知件数（都道府県別）"},
]

estat_results = {}

if estat_key:
    print(f"  e-Stat APIキー: 発見")
    for target in ESTAT_TARGETS:
        url = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"
        params = {
            "appId": estat_key,
            "statsDataId": target["id"],
            "metaGetFlg": "Y",
            "cntGetFlg": "N",
        }
        try:
            r = requests.get(url, params=params, timeout=30)
            data = r.json()
            stats = data.get("GET_STATS_DATA", {}).get("STATISTICAL_DATA", {})
            values = stats.get("DATA_INF", {}).get("VALUE", [])
            print(f"  {target['name']}: {len(values)}件")
            with open(f"data/crime/national/estat_{target['id']}.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            estat_results[target["id"]] = {"count": len(values), "status": "success"}
            time.sleep(1)
        except Exception as e:
            print(f"  {target['name']}: 失敗 - {e}")
            estat_results[target["id"]] = {"status": "failed", "error": str(e)}
else:
    print("  e-Stat APIキーが見つかりません")
    # Try without API key (some endpoints work)
    print("  APIキーなしでアクセス試行...")
    for target in ESTAT_TARGETS:
        url = f"https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData?statsDataId={target['id']}&metaGetFlg=Y&cntGetFlg=N&limit=10"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                status = data.get("GET_STATS_DATA", {}).get("RESULT", {}).get("STATUS", -1)
                print(f"  {target['name']}: status={status}")
                estat_results[target["id"]] = {"status": f"http_ok_api_status_{status}"}
            else:
                print(f"  {target['name']}: HTTP {r.status_code}")
                estat_results[target["id"]] = {"status": f"http_{r.status_code}"}
        except Exception as e:
            print(f"  {target['name']}: {e}")
            estat_results[target["id"]] = {"status": "failed"}
        time.sleep(1)

# Check if we already have e-Stat data from previous batch
existing_estat = list(Path("data/normalized").glob("*estat*")) + list(Path("data").rglob("*estat*.json"))
if existing_estat:
    print(f"  既存e-Statデータ: {len(existing_estat)}ファイル")
    for f in existing_estat:
        print(f"    {f}")

with open("data/crime/national/estat_results.json", "w", encoding="utf-8") as f:
    json.dump(estat_results, f, ensure_ascii=False, indent=2)

print("--- Step 3 完了 ---")

# =====================================================================
# Step 4: 不審者情報全国収集
# =====================================================================
print("\n" + "=" * 60)
print("Step 4: 全国不審者情報収集")
print("=" * 60)

FUSHINSHA_SOURCES = [
    {"name": "ガッコム安全ナビ", "url": "https://www.gaccom.jp/safety/", "type": "scrape"},
    {"name": "ガッコム安全ナビ（地域別）", "url": "https://www.gaccom.jp/safety/search/", "type": "scrape"},
    {"name": "日本不審者情報センター", "url": "https://fushinsha-joho.co.jp/", "type": "scrape"},
    {"name": "愛知パトネット", "url": "https://www.pref.aichi.jp/police/anzen/bouhan/patnet/", "type": "scrape"},
    {"name": "神奈川防犯情報", "url": "https://www.police.pref.kanagawa.jp/mes/faq60030.htm", "type": "scrape"},
    {"name": "大阪防犯情報", "url": "https://www.police.pref.osaka.lg.jp/seikatsu/bouhan/", "type": "scrape"},
    {"name": "福岡防犯情報", "url": "https://www.police.pref.fukuoka.jp/seian/seianki/", "type": "scrape"},
    {"name": "メールけいしちょう", "url": "https://catalog.data.metro.tokyo.lg.jp/api/3/action/package_search?q=不審者&rows=10", "type": "api"},
]

FUSHINSHA_KW = ["不審者", "ちかん", "痴漢", "声かけ", "つきまとい", "盗撮", "わいせつ",
                "露出", "のぞき", "変質者", "尾行", "待ち伏せ"]

all_fushinsha = []

for source in FUSHINSHA_SOURCES:
    print(f"\n  取得中: {source['name']}")
    try:
        r = requests.get(source["url"], headers=headers, timeout=15)
        r.encoding = r.apparent_encoding or "utf-8"

        if source["type"] == "api":
            try:
                data = r.json()
                results_list = data.get("result", {}).get("results", [])
                print(f"    API結果: {len(results_list)}件")
                for item in results_list:
                    all_fushinsha.append({
                        "source": source["name"],
                        "text": item.get("title", "")[:200],
                        "layer": "crime",
                        "subtype": "suspicious_person",
                        "scraped_at": datetime.now().isoformat(),
                    })
            except:
                pass
            continue

        soup = BeautifulSoup(r.text, "lxml")
        crime_texts = []

        for tag in soup.find_all(["a", "p", "li", "td", "div", "span"]):
            text = tag.get_text(strip=True)
            if any(kw in text for kw in FUSHINSHA_KW) and 10 < len(text) < 500:
                if text not in crime_texts:
                    crime_texts.append(text)

        for text in crime_texts[:30]:
            date_m = re.search(r'(\d{1,4}年?\d{1,2}月\d{1,2}日)', text)
            time_m = re.search(r'(\d{1,2}時\d{0,2}分?頃?)', text)
            addr_m = re.search(r'(.{2,4}[都道府県].{1,10}[市区町村郡].{0,15}(?:[丁目番地号]|\d丁目))', text)

            all_fushinsha.append({
                "source": source["name"],
                "text": text[:200],
                "date": date_m.group(1) if date_m else None,
                "time": time_m.group(1) if time_m else None,
                "address": addr_m.group(1) if addr_m else None,
                "layer": "crime",
                "subtype": "suspicious_person",
                "scraped_at": datetime.now().isoformat(),
            })

        print(f"    {source['name']}: {len(crime_texts)}件抽出")
        time.sleep(2)
    except Exception as e:
        print(f"    {source['name']}: 失敗 - {e}")

with open("data/realtime/fushinsha/all_fushinsha.json", "w", encoding="utf-8") as f:
    json.dump(all_fushinsha, f, ensure_ascii=False, indent=2)
print(f"\n--- Step 4 完了: 不審者情報 {len(all_fushinsha)}件 ---")

# =====================================================================
# Step 5: 地方新聞・NHKニュース事件クロール
# =====================================================================
print("\n" + "=" * 60)
print("Step 5: 地方新聞・NHK 事件情報クロール")
print("=" * 60)

NEWS_SOURCES = [
    {"name": "NHK地域ニュース", "url": "https://www3.nhk.or.jp/news/catnew.html"},
    {"name": "読売新聞", "url": "https://www.yomiuri.co.jp/national/"},
    {"name": "毎日新聞", "url": "https://mainichi.jp/jiken/"},
    {"name": "産経新聞", "url": "https://www.sankei.com/affairs/"},
    {"name": "朝日新聞", "url": "https://www.asahi.com/national/"},
    {"name": "北海道新聞", "url": "https://www.hokkaido-np.co.jp/news/society/"},
    {"name": "東京新聞", "url": "https://www.tokyo-np.co.jp/national"},
    {"name": "神奈川新聞", "url": "https://www.kanaloco.jp/"},
    {"name": "中日新聞", "url": "https://www.chunichi.co.jp/section/national"},
    {"name": "西日本新聞", "url": "https://www.nishinippon.co.jp/theme/crime/"},
    {"name": "琉球新報", "url": "https://ryukyushimpo.jp/category/society"},
    {"name": "河北新報", "url": "https://kahoku.news/tag/jiken/"},
]

CRIME_KEYWORDS = [
    "逮捕", "不審者", "強盗", "暴行", "傷害", "刃物",
    "痴漢", "盗撮", "わいせつ", "性犯罪", "ストーカー",
    "ひったくり", "詐欺", "特殊詐欺", "振り込め詐欺",
    "空き巣", "車上荒らし", "窃盗",
    "交通死亡事故", "轢き逃げ", "飲酒運転", "殺人", "放火",
]

ADDR_PATTERN = r'(.{2,4}[都道府県].{1,8}[市区町村郡].{0,15}(?:[丁目番地号]|\d丁目|\d番))'
DATE_PATTERN = r'(\d{1,4}年?\d{1,2}月\d{1,2}日)'

all_articles = []

for source in NEWS_SOURCES:
    print(f"\n  取得中: {source['name']}")
    try:
        r = requests.get(source["url"], headers=headers, timeout=15)
        r.encoding = r.apparent_encoding or "utf-8"
        soup = BeautifulSoup(r.text, "lxml")

        article_links = []
        seen_urls = set()
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a["href"]
            if any(kw in text for kw in CRIME_KEYWORDS) and len(text) > 5:
                if href.startswith("http"):
                    full_url = href
                elif href.startswith("/"):
                    parts = source["url"].split("/")
                    full_url = f"{parts[0]}//{parts[2]}{href}"
                else:
                    continue
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    article_links.append({"title": text[:100], "url": full_url})

        print(f"    事件関連記事: {len(article_links)}件")

        for article in article_links[:15]:
            try:
                ar = requests.get(article["url"], headers=headers, timeout=10)
                ar.encoding = ar.apparent_encoding or "utf-8"
                abody = BeautifulSoup(ar.text, "lxml").get_text()[:3000]

                date_m = re.search(DATE_PATTERN, abody)
                addr_m = re.search(ADDR_PATTERN, abody)
                keywords_found = [kw for kw in CRIME_KEYWORDS if kw in abody]

                subtype = "crime_other"
                if any(k in abody for k in ["強盗", "ひったくり"]): subtype = "robbery"
                elif any(k in abody for k in ["痴漢", "盗撮", "わいせつ", "性犯罪"]): subtype = "sexual_crime"
                elif any(k in abody for k in ["暴行", "傷害", "刃物"]): subtype = "assault"
                elif any(k in abody for k in ["不審者", "声かけ"]): subtype = "suspicious_person"
                elif any(k in abody for k in ["詐欺", "振り込め"]): subtype = "fraud"
                elif any(k in abody for k in ["殺人", "放火"]): subtype = "homicide_arson"
                elif any(k in abody for k in ["交通死亡", "轢き逃げ"]): subtype = "collision_fatal"
                elif any(k in abody for k in ["窃盗", "空き巣"]): subtype = "theft"

                all_articles.append({
                    "source": source["name"],
                    "title": article["title"],
                    "url": article["url"],
                    "date": date_m.group(1) if date_m else None,
                    "address": addr_m.group(1) if addr_m else None,
                    "subtype": subtype,
                    "keywords": keywords_found,
                    "layer": "crime",
                    "body_excerpt": abody[:500],
                    "scraped_at": datetime.now().isoformat(),
                })
                time.sleep(1.5)
            except:
                pass

        time.sleep(3)
    except Exception as e:
        print(f"    {source['name']}: 失敗 - {e}")

with open("data/realtime/news/crime_news.json", "w", encoding="utf-8") as f:
    json.dump(all_articles, f, ensure_ascii=False, indent=2)

subtypes = Counter(a["subtype"] for a in all_articles)
print(f"\n--- Step 5 完了: ニュース事件 {len(all_articles)}件 ---")
print("  種別内訳:")
for k, v in subtypes.most_common():
    print(f"    {k}: {v}件")

# =====================================================================
# Step 6: 統合レポート
# =====================================================================
print("\n" + "=" * 60)
print("Step 6: 統合レポート生成")
print("=" * 60)

all_crime_files = []
for pref_dir in Path("data/crime/prefectures").iterdir():
    if not pref_dir.is_dir():
        continue
    pref = pref_dir.name
    for csv_file in pref_dir.glob("*.csv"):
        try:
            with open(csv_file, "rb") as f:
                raw = f.read()
            enc = chardet.detect(raw[:10000])["encoding"] or "cp932"
            df = pd.read_csv(csv_file, encoding=enc, low_memory=False)
            all_crime_files.append({
                "pref": pref,
                "file": csv_file.name,
                "rows": len(df),
                "columns": list(df.columns)[:10],
                "sample": df.head(1).to_dict(orient="records"),
            })
            print(f"  {pref}/{csv_file.name}: {len(df):,}行")
        except Exception as e:
            # Try xlsx
            pass

    for xlsx_file in pref_dir.glob("*.xlsx"):
        try:
            df = pd.read_excel(xlsx_file)
            all_crime_files.append({
                "pref": pref,
                "file": xlsx_file.name,
                "rows": len(df),
                "columns": list(df.columns)[:10],
            })
            print(f"  {pref}/{xlsx_file.name}: {len(df):,}行")
        except:
            pass

report = {
    "generated_at": datetime.now().isoformat(),
    "prefecture_data": {
        "files": len(all_crime_files),
        "total_rows": sum(d["rows"] for d in all_crime_files),
        "prefectures_covered": sorted(set(d["pref"] for d in all_crime_files)),
        "prefectures_count": len(set(d["pref"] for d in all_crime_files)),
    },
    "tokyo_existing": {
        "rows": 29043,
        "geocoded": 28936,
    },
    "realtime": {
        "fushinsha": len(all_fushinsha),
        "news": len(all_articles),
    },
    "estat": estat_results,
    "details": all_crime_files,
}

with open("data/crime/COLLECTION_REPORT.json", "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(f"\n{'=' * 60}")
print(f"===== 全国犯罪データ収集 最終結果 =====")
print(f"{'=' * 60}")
print(f"  都道府県CSVファイル: {len(all_crime_files)}件")
print(f"  都道府県総レコード: {sum(d['rows'] for d in all_crime_files):,}件")
print(f"  カバー都道府県: {len(set(d['pref'] for d in all_crime_files))}府県")
print(f"  東京都（既取得）: 29,043件 (28,936件ジオコーディング済)")
print(f"  不審者情報: {len(all_fushinsha)}件")
print(f"  ニュース事件: {len(all_articles)}件")
print(f"\n  COLLECTION_REPORT.json 生成完了")
print(f"  完了時刻: {datetime.now().isoformat()}")
