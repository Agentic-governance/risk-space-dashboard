"""
Phase 2: NPA公式リンクページ経由で各都道府県のCSVを取得
各都道府県のオープンデータページを訪問し、CSVリンクを抽出してダウンロード
"""
import requests, json, time, os, re
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime
import chardet, pandas as pd

BASE = Path("/Users/reikumaki/Library/CloudStorage/GoogleDrive-teddykmk@gmail.com/マイドライブ/piracy_detector/claude_code/risk_space")
os.chdir(BASE)

headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# Already downloaded prefectures (skip)
DONE = {"東京都", "神奈川県", "愛知県", "大阪府", "埼玉県", "宮城県", "兵庫県", "福岡県", "千葉県"}

# NPA official links for remaining prefectures
NPA_PREF_PAGES = [
    {"pref": "北海道", "code": "01", "url": "https://www.harp.lg.jp/opendata/dataset/bunya/kurashi/"},
    {"pref": "青森県", "code": "02", "url": "https://www.police.pref.aomori.jp/seianbu/seian_kikaku/hanyoku/hanyoku_opendate.html"},
    {"pref": "岩手県", "code": "03", "url": "https://www.pref.iwate.jp/kenkei/koho/opendata/3000711.html"},
    {"pref": "秋田県", "code": "05", "url": "https://www.police.pref.akita.lg.jp/kenkei/statistics"},
    {"pref": "山形県", "code": "06", "url": "https://www.pref.yamagata.jp/020051/kensei/shoukai/toukeijouhou/tokeijoho-opendate/opendata/cata1.html"},
    {"pref": "福島県", "code": "07", "url": "http://www.police.pref.fukushima.jp/seianki/homepage/top_page/R04custom.crime_open_data.html"},
    {"pref": "茨城県", "code": "08", "url": "https://www.ibaraki-opendata.jp/index.php"},
    {"pref": "群馬県", "code": "10", "url": "https://www.police.pref.gunma.jp/site/police/28701.html"},
    {"pref": "新潟県", "code": "15", "url": None},  # Not in NPA list
    {"pref": "富山県", "code": "16", "url": "https://opendata.pref.toyama.jp/dataset/settou2024"},
    {"pref": "石川県", "code": "17", "url": "https://www2.police.pref.ishikawa.lg.jp/security/security24/"},
    {"pref": "長野県", "code": "20", "url": "https://www.pref.nagano.lg.jp/police/toukei/hanzai/opendata.html"},
    {"pref": "静岡県", "code": "22", "url": "https://www.pref.shizuoka.jp/police/kurashi/hanzai/nenkan/opendata.html"},
    {"pref": "岐阜県", "code": "21", "url": "https://gifu-opendata.pref.gifu.lg.jp/dataset/c18879-007"},
    {"pref": "三重県", "code": "24", "url": "http://www.police.pref.mie.jp/safety_info/op_data_index.html"},
    {"pref": "京都府", "code": "26", "url": None},  # Not in NPA list
    {"pref": "奈良県", "code": "29", "url": "http://www.police.pref.nara.jp/0000003672.html"},
    {"pref": "和歌山県", "code": "30", "url": "https://www.police.pref.wakayama.lg.jp/04_toukei/index.html"},
    {"pref": "島根県", "code": "32", "url": "https://shimane-opendata.jp/datasets/1055"},
    {"pref": "岡山県", "code": "33", "url": "https://www.okayama-opendata.jp/datasets?tag=防犯"},
    {"pref": "広島県", "code": "34", "url": "https://hiroshima-opendata.dataeye.jp/datasets?group=gr_0200"},
    {"pref": "山口県", "code": "35", "url": "https://yamaguchi-opendata.jp/"},
    {"pref": "徳島県", "code": "36", "url": "https://www.police.pref.tokushima.jp/28opendata/index.html"},
    {"pref": "香川県", "code": "37", "url": "https://opendata.pref.kagawa.lg.jp/dataset/bunya/bosai/"},
    {"pref": "愛媛県", "code": "38", "url": "https://www.police.pref.ehime.jp/seiki/mokuji/fusegou.html"},
    {"pref": "高知県", "code": "39", "url": "https://www.police.pref.kochi.lg.jp/docs/2023111400109/"},
    {"pref": "長崎県", "code": "42", "url": "https://www.police.pref.nagasaki.jp/police/kurashi/kurashi-tokei/hanzainincti-top/"},
    {"pref": "沖縄県", "code": "47", "url": "https://www.police.pref.okinawa.jp/category/bunya/tokei"},
    # Prefectures not in NPA list at all (less likely to have open data):
    {"pref": "栃木県", "code": "09", "url": None},
    {"pref": "福井県", "code": "18", "url": None},
    {"pref": "山梨県", "code": "19", "url": None},
    {"pref": "滋賀県", "code": "25", "url": None},
    {"pref": "鳥取県", "code": "31", "url": None},
    {"pref": "佐賀県", "code": "41", "url": None},
    {"pref": "熊本県", "code": "43", "url": None},
    {"pref": "大分県", "code": "44", "url": None},
    {"pref": "宮崎県", "code": "45", "url": None},
    {"pref": "鹿児島県", "code": "46", "url": None},
]


def find_data_links(url):
    """Find CSV/XLSX/data links from a page, including CKAN API pages"""
    links = []
    try:
        r = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        if r.status_code != 200:
            return links

        # Check if it's a CKAN API
        if "api/3/action" in url or "dataset" in url:
            try:
                data = r.json()
                resources = data.get("result", {}).get("resources", [])
                if not resources and isinstance(data.get("result"), list):
                    for ds in data["result"]:
                        resources.extend(ds.get("resources", []))
                for res in resources:
                    dl_url = res.get("url", "")
                    name = res.get("name", "")
                    fmt = res.get("format", "").upper()
                    if fmt in ("CSV", "XLSX", "XLS") or any(ext in dl_url.lower() for ext in [".csv", ".xlsx"]):
                        links.append({"url": dl_url, "text": name})
                return links
            except:
                pass

        soup = BeautifulSoup(r.text, "lxml")

        # Find direct CSV/XLSX links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if any(ext in href.lower() for ext in [".csv", ".xlsx", ".xls", ".zip"]):
                if href.startswith("http"):
                    full = href
                elif href.startswith("/"):
                    parts = url.split("/")
                    full = f"{parts[0]}//{parts[2]}{href}"
                else:
                    full = f"{'/'.join(url.split('/')[:-1])}/{href}"
                links.append({"url": full, "text": text})

        # If no direct links, look for sub-pages that might have them
        if not links:
            sub_pages = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True)
                if any(kw in text for kw in ["2024", "令和6", "R6", "オープンデータ", "犯罪", "窃盗"]) or \
                   any(kw in href for kw in ["2024", "r6", "r06", "opendata", "hanzai", "settou"]):
                    if href.startswith("http"):
                        sub_url = href
                    elif href.startswith("/"):
                        parts = url.split("/")
                        sub_url = f"{parts[0]}//{parts[2]}{href}"
                    else:
                        sub_url = f"{'/'.join(url.split('/')[:-1])}/{href}"
                    sub_pages.append(sub_url)

            # Visit first few sub-pages
            for sub_url in sub_pages[:5]:
                try:
                    time.sleep(1)
                    sr = requests.get(sub_url, headers=headers, timeout=15)
                    if sr.status_code != 200:
                        continue

                    # Try CKAN JSON
                    try:
                        sdata = sr.json()
                        resources = sdata.get("result", {}).get("resources", [])
                        for res in resources:
                            dl_url = res.get("url", "")
                            name = res.get("name", "")
                            fmt = res.get("format", "").upper()
                            if fmt in ("CSV", "XLSX") or ".csv" in dl_url.lower():
                                links.append({"url": dl_url, "text": name})
                        if links:
                            break
                    except:
                        pass

                    ssoup = BeautifulSoup(sr.text, "lxml")
                    for a in ssoup.find_all("a", href=True):
                        href = a["href"]
                        text = a.get_text(strip=True)
                        if any(ext in href.lower() for ext in [".csv", ".xlsx"]):
                            if href.startswith("http"):
                                full = href
                            elif href.startswith("/"):
                                parts = sub_url.split("/")
                                full = f"{parts[0]}//{parts[2]}{href}"
                            else:
                                full = f"{'/'.join(sub_url.split('/')[:-1])}/{href}"
                            links.append({"url": full, "text": text})
                    if links:
                        break
                except:
                    pass

    except Exception as e:
        pass
    return links


def try_download(url, save_path):
    try:
        r = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        if r.status_code != 200 or len(r.content) < 100:
            return False
        ct = r.headers.get("Content-Type", "")
        if "text/html" in ct and (r.content[:20].startswith(b'<!') or b'<html' in r.content[:200].lower()):
            return False
        with open(save_path, "wb") as f:
            f.write(r.content)
        return True
    except:
        return False


def count_csv_rows(path):
    try:
        with open(path, "rb") as f:
            raw = f.read()
        enc = chardet.detect(raw[:10000])["encoding"] or "cp932"
        df = pd.read_csv(path, encoding=enc, low_memory=False)
        return len(df)
    except:
        try:
            df = pd.read_csv(path, encoding="cp932", low_memory=False)
            return len(df)
        except:
            try:
                return sum(1 for _ in open(path, "rb")) - 1
            except:
                return 0


# =====================================================================
print("=" * 60)
print("NPA公式リンク経由 都道府県犯罪データ収集")
print("=" * 60)

results = {}

for cfg in NPA_PREF_PAGES:
    pref = cfg["pref"]
    if pref in DONE:
        continue
    if not cfg["url"]:
        print(f"\n{pref}: NPA リンクなし → スキップ")
        results[pref] = {"status": "no_npa_link", "files": 0, "rows": 0}
        continue

    print(f"\n{pref} ({cfg['url'][:60]}...)")
    pref_dir = Path(f"data/crime/prefectures/{pref}")
    pref_dir.mkdir(parents=True, exist_ok=True)

    data_links = find_data_links(cfg["url"])
    time.sleep(1.5)

    if not data_links:
        print(f"  CSVリンク見つからず")
        results[pref] = {"status": "no_csv", "files": 0, "rows": 0}
        continue

    # Filter to crime-related CSVs
    crime_keywords = ["hittakuri", "syazyou", "buhin", "zidouhanbaiki", "zidousya", "ootokai", "jitensy",
                       "zitensya", "settou", "窃盗", "ひったくり", "車上", "部品", "自販機", "自動車", "オートバイ", "自転車",
                       "crime", "hanzai", "犯罪"]
    crime_links = [l for l in data_links if any(kw in l["url"].lower() or kw in l["text"] for kw in crime_keywords)]
    if not crime_links:
        crime_links = data_links  # Use all if no keyword match

    print(f"  {len(crime_links)}件のデータリンク発見")
    downloaded = []
    total_rows = 0

    seen = set()
    for link in crime_links[:15]:
        url = link["url"]
        if url in seen:
            continue
        seen.add(url)

        fname = url.split("/")[-1].split("?")[0]
        if not fname or len(fname) < 3:
            fname = f"data_{len(downloaded)}.csv"
        save_path = pref_dir / fname

        if try_download(url, save_path):
            rows = count_csv_rows(save_path)
            total_rows += rows
            downloaded.append({"file": fname, "rows": rows, "text": link["text"]})
            print(f"    ✓ {link['text'][:30]}: {rows:,}行")
        time.sleep(1)

    results[pref] = {
        "code": cfg["code"],
        "status": "success" if downloaded else "failed",
        "files": len(downloaded),
        "rows": total_rows,
        "details": downloaded,
    }

# Also try CKAN-based open data portals for specific prefectures
CKAN_PORTALS = [
    {"pref": "富山県", "url": "https://opendata.pref.toyama.jp/api/3/action/package_show?id=settou2024"},
    {"pref": "岐阜県", "url": "https://gifu-opendata.pref.gifu.lg.jp/api/3/action/package_show?id=c18879-007"},
    {"pref": "島根県", "url": "https://shimane-opendata.jp/api/3/action/package_show?id=1055"},
    {"pref": "広島県", "url": "https://hiroshima-opendata.dataeye.jp/api/3/action/group_show?id=gr_0200"},
]

for portal in CKAN_PORTALS:
    pref = portal["pref"]
    if pref in DONE or (pref in results and results[pref]["status"] == "success"):
        continue
    print(f"\n{pref} (CKAN API試行)")
    pref_dir = Path(f"data/crime/prefectures/{pref}")
    pref_dir.mkdir(parents=True, exist_ok=True)

    try:
        r = requests.get(portal["url"], headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            result = data.get("result", {})
            resources = result.get("resources", [])

            # If group_show, need to get packages
            if not resources and "packages" in result:
                for pkg in result["packages"][:5]:
                    resources.extend(pkg.get("resources", []))

            downloaded = []
            total_rows = 0
            for res in resources:
                url = res.get("url", "")
                name = res.get("name", "")
                fmt = res.get("format", "").upper()
                if fmt in ("CSV",) or ".csv" in url.lower():
                    fname = url.split("/")[-1] or f"{name}.csv"
                    if try_download(url, pref_dir / fname):
                        rows = count_csv_rows(pref_dir / fname)
                        total_rows += rows
                        downloaded.append({"file": fname, "rows": rows})
                        print(f"  ✓ {name}: {rows:,}行")
                    time.sleep(1)

            if downloaded:
                results[pref] = {
                    "status": "success",
                    "files": len(downloaded),
                    "rows": total_rows,
                    "details": downloaded,
                }
    except Exception as e:
        print(f"  CKAN API失敗: {e}")
    time.sleep(1)

# =====================================================================
# Summary
# =====================================================================
print("\n" + "=" * 60)
print("Phase 2 最終結果")
print("=" * 60)

success = [(p, v) for p, v in results.items() if v.get("status") == "success"]
failed = [(p, v) for p, v in results.items() if v.get("status") != "success"]

print(f"\n新規取得成功: {len(success)}都道府県")
for p, v in sorted(success):
    print(f"  {p}: {v['files']}ファイル / {v['rows']:,}行")

total_new = sum(v["rows"] for _, v in success)
print(f"\n新規総レコード数: {total_new:,}")

print(f"\n未取得: {len(failed)}都道府県")
for p, v in sorted(failed):
    print(f"  {p}: {v.get('status', 'unknown')}")

with open("data/crime/prefectures/phase2_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n完了: {datetime.now().isoformat()}")
