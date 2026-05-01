"""
全国犯罪オープンデータ直接ダウンロード
NPA統一フォーマット: 7窃盗手口 × 都道府県 × 年度
"""
import requests, json, time, os
from pathlib import Path
from datetime import datetime
import chardet, pandas as pd

BASE = Path("/Users/reikumaki/Library/CloudStorage/GoogleDrive-teddykmk@gmail.com/マイドライブ/piracy_detector/claude_code/risk_space")
os.chdir(BASE)

headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# 7 standard crime types (NPA unified format)
CRIME_TYPES = [
    ("hittakuri", "ひったくり"),
    ("syazyounerai", "車上ねらい"),
    ("buhinnerai", "部品ねらい"),
    ("zidouhanbaikinerai", "自販機ねらい"),
    ("zidousyatou", "自動車盗"),
    ("ootobaitou", "オートバイ盗"),
    ("zitensyatou", "自転車盗"),
]

YEAR = "2024"

# Confirmed direct CSV URL patterns per prefecture
PREF_URLS = {
    "神奈川県": {
        "code": "14",
        "base": "https://www.police.pref.kanagawa.jp/assets/entry/",
        "pattern": "kanagawa_{year}{type}.csv",
    },
    "愛知県": {
        "code": "23",
        "base": "https://www.pref.aichi.jp/police/anzen/toukei/opendata/seian-s/images/",
        "pattern": "aichi-{year}{type}.csv",
    },
    "大阪府": {
        "code": "27",
        "base": "https://www.police.pref.osaka.lg.jp/material/files/group/2/",
        "pattern": "osaka_{year}{type}.csv",
    },
    "埼玉県": {
        "code": "11",
        "base": "https://www.police.pref.saitama.lg.jp/documents/33251/",
        "pattern": "saitama_{year}{type}.csv",
    },
    "宮城県": {
        "code": "04",
        "base": "https://www.police.pref.miyagi.jp/seian/csv/",
        "pattern": "miyagi_{year}{type}.csv",
    },
    "兵庫県": {
        "code": "28",
        "base": "https://web.pref.hyogo.lg.jp/kk26/johoseisaku/documents/",
        "pattern": "hyogo_{year}{type}.csv",
    },
}

# Additional prefectures to try with common patterns
# Many follow: {pref}_{year}{type}.csv
EXTRA_PREF_PATTERNS = [
    # NPA link page based prefectures with guessed URL patterns
    {"pref": "京都府", "code": "26", "bases": [
        "https://www.pref.kyoto.jp/fukei/anzen/bouhan/opendata/",
        "https://www.pref.kyoto.jp/fukei/anzen/bouhan/opendata/documents/",
    ], "prefix": "kyoto"},
    {"pref": "静岡県", "code": "22", "bases": [
        "https://www.police.pref.shizuoka.jp/about/release/opendata/",
        "https://www.police.pref.shizuoka.jp/about/release/opendata/documents/",
    ], "prefix": "shizuoka"},
    {"pref": "茨城県", "code": "08", "bases": [
        "https://www.police.pref.ibaraki.jp/opendata/",
        "https://www.police.pref.ibaraki.jp/opendata/csv/",
    ], "prefix": "ibaraki"},
    {"pref": "広島県", "code": "34", "bases": [
        "https://www.pref.hiroshima.lg.jp/site/police/opendata/",
        "https://www.pref.hiroshima.lg.jp/uploaded/attachment/",
    ], "prefix": "hiroshima"},
    {"pref": "新潟県", "code": "15", "bases": [
        "https://www.police.pref.niigata.jp/kikaku/opendata/",
        "https://www.police.pref.niigata.jp/kikaku/opendata/csv/",
    ], "prefix": "niigata"},
    {"pref": "群馬県", "code": "10", "bases": [
        "https://www.police.pref.gunma.jp/seianbu/01seiki/opendata/",
    ], "prefix": "gunma"},
    {"pref": "栃木県", "code": "09", "bases": [
        "https://www.police.pref.tochigi.lg.jp/kenke/kikaku/opendata/",
    ], "prefix": "tochigi"},
    {"pref": "岐阜県", "code": "21", "bases": [
        "https://www.pref.gifu.lg.jp/police/kenmin/opendata/",
    ], "prefix": "gifu"},
    {"pref": "三重県", "code": "24", "bases": [
        "https://www.police.pref.mie.jp/crime/opendata/",
    ], "prefix": "mie"},
    {"pref": "長野県", "code": "20", "bases": [
        "https://www.police.pref.nagano.lg.jp/opendata/",
    ], "prefix": "nagano"},
    {"pref": "岡山県", "code": "33", "bases": [
        "https://www.pref.okayama.jp/police/soumu/opendata/",
    ], "prefix": "okayama"},
    {"pref": "福島県", "code": "07", "bases": [
        "https://www.police.pref.fukushima.jp/seianki/seian/opendata/",
    ], "prefix": "fukushima"},
    {"pref": "滋賀県", "code": "25", "bases": [
        "https://www.police.pref.shiga.jp/opendata/",
    ], "prefix": "shiga"},
    {"pref": "奈良県", "code": "29", "bases": [
        "https://www.police.pref.nara.jp/opendata/",
    ], "prefix": "nara"},
    {"pref": "富山県", "code": "16", "bases": [
        "https://www.police.pref.toyama.jp/opendata/",
    ], "prefix": "toyama"},
    {"pref": "石川県", "code": "17", "bases": [
        "https://www.police.pref.ishikawa.lg.jp/opendata/",
    ], "prefix": "ishikawa"},
    {"pref": "山形県", "code": "06", "bases": [
        "https://www.police.pref.yamagata.jp/opendata/",
    ], "prefix": "yamagata"},
    {"pref": "岩手県", "code": "03", "bases": [
        "https://www.police.pref.iwate.jp/opendata/",
    ], "prefix": "iwate"},
    {"pref": "秋田県", "code": "05", "bases": [
        "https://www.police.pref.akita.jp/opendata/",
    ], "prefix": "akita"},
    {"pref": "青森県", "code": "02", "bases": [
        "https://www.police.pref.aomori.jp/opendata/",
    ], "prefix": "aomori"},
    {"pref": "和歌山県", "code": "30", "bases": [
        "https://www.police.pref.wakayama.lg.jp/opendata/",
    ], "prefix": "wakayama"},
    {"pref": "山口県", "code": "35", "bases": [
        "https://www.police.pref.yamaguchi.lg.jp/opendata/",
    ], "prefix": "yamaguchi"},
    {"pref": "香川県", "code": "37", "bases": [
        "https://www.police.pref.kagawa.lg.jp/opendata/",
    ], "prefix": "kagawa"},
    {"pref": "愛媛県", "code": "38", "bases": [
        "https://www.police.pref.ehime.jp/opendata/",
    ], "prefix": "ehime"},
    {"pref": "佐賀県", "code": "41", "bases": [
        "https://www.police.pref.saga.jp/opendata/",
    ], "prefix": "saga"},
    {"pref": "長崎県", "code": "42", "bases": [
        "https://www.police.pref.nagasaki.jp/opendata/",
    ], "prefix": "nagasaki"},
    {"pref": "熊本県", "code": "43", "bases": [
        "https://www.police.pref.kumamoto.jp/opendata/",
    ], "prefix": "kumamoto"},
    {"pref": "大分県", "code": "44", "bases": [
        "https://www.police.pref.oita.jp/opendata/",
    ], "prefix": "oita"},
    {"pref": "宮崎県", "code": "45", "bases": [
        "https://www.police.pref.miyazaki.lg.jp/opendata/",
    ], "prefix": "miyazaki"},
    {"pref": "鹿児島県", "code": "46", "bases": [
        "https://www.police.pref.kagoshima.jp/opendata/",
    ], "prefix": "kagoshima"},
    {"pref": "沖縄県", "code": "47", "bases": [
        "https://www.police.pref.okinawa.jp/opendata/",
    ], "prefix": "okinawa"},
    {"pref": "鳥取県", "code": "31", "bases": [
        "https://www.police.pref.tottori.jp/opendata/",
    ], "prefix": "tottori"},
    {"pref": "島根県", "code": "32", "bases": [
        "https://www.police.pref.shimane.lg.jp/opendata/",
    ], "prefix": "shimane"},
    {"pref": "徳島県", "code": "36", "bases": [
        "https://www.police.pref.tokushima.jp/opendata/",
    ], "prefix": "tokushima"},
    {"pref": "高知県", "code": "39", "bases": [
        "https://www.police.pref.kochi.lg.jp/opendata/",
    ], "prefix": "kochi"},
    {"pref": "山梨県", "code": "19", "bases": [
        "https://www.police.pref.yamanashi.jp/opendata/",
    ], "prefix": "yamanashi"},
    {"pref": "福井県", "code": "18", "bases": [
        "https://www.police.pref.fukui.jp/opendata/",
    ], "prefix": "fukui"},
]


def try_download(url, save_path):
    """Download file, return True if successful (non-HTML, >100 bytes)"""
    try:
        r = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
        if r.status_code != 200:
            return False
        ct = r.headers.get("Content-Type", "")
        if "text/html" in ct:
            # Could still be CSV served as text/html, check content
            if r.content[:20].startswith(b'<!') or b'<html' in r.content[:200].lower():
                return False
        if len(r.content) < 100:
            return False
        with open(save_path, "wb") as f:
            f.write(r.content)
        return True
    except:
        return False


def count_csv_rows(path):
    """Count rows in CSV with auto-detected encoding"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
        enc = chardet.detect(raw[:10000])["encoding"] or "cp932"
        df = pd.read_csv(path, encoding=enc, low_memory=False)
        return len(df), list(df.columns)
    except:
        try:
            df = pd.read_csv(path, encoding="cp932", low_memory=False)
            return len(df), list(df.columns)
        except:
            try:
                return sum(1 for _ in open(path, "rb")) - 1, []
            except:
                return 0, []


# =====================================================================
# Phase 1: NPA master link page
# =====================================================================
print("=" * 60)
print("Phase 1: 警察庁マスターリンクページ取得")
print("=" * 60)

NPA_URL = "https://www.npa.go.jp/toukei/seianki/hanzaiopendatalink.html"
npa_csv_links = []

try:
    from bs4 import BeautifulSoup
    r = requests.get(NPA_URL, headers=headers, timeout=15)
    if r.status_code == 200:
        soup = BeautifulSoup(r.text, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if any(ext in href.lower() for ext in [".csv", ".xlsx"]):
                full = href if href.startswith("http") else f"https://www.npa.go.jp{href}"
                npa_csv_links.append({"url": full, "text": text})
            elif "police.pref" in href or "opendata" in href.lower():
                full = href if href.startswith("http") else f"https://www.npa.go.jp{href}"
                npa_csv_links.append({"url": full, "text": text, "type": "page"})
        print(f"  NPA リンク: {len(npa_csv_links)}件")
    else:
        print(f"  NPA: HTTP {r.status_code}")
except Exception as e:
    print(f"  NPA: {e}")

# Save NPA links
Path("data/crime/national").mkdir(parents=True, exist_ok=True)
with open("data/crime/national/npa_master_links.json", "w", encoding="utf-8") as f:
    json.dump(npa_csv_links, f, ensure_ascii=False, indent=2)

# =====================================================================
# Phase 2: Confirmed prefectures - direct download
# =====================================================================
print("\n" + "=" * 60)
print("Phase 2: 確認済み都道府県の直接ダウンロード")
print("=" * 60)

results = {}
total_rows_all = 0
total_files_all = 0

for pref, cfg in PREF_URLS.items():
    print(f"\n{pref} (確認済みURL)")
    pref_dir = Path(f"data/crime/prefectures/{pref}")
    pref_dir.mkdir(parents=True, exist_ok=True)

    pref_files = []
    pref_rows = 0

    for type_key, type_name in CRIME_TYPES:
        fname = cfg["pattern"].format(year=YEAR, type=type_key)
        url = cfg["base"] + fname
        save_path = pref_dir / fname

        if try_download(url, save_path):
            rows, cols = count_csv_rows(save_path)
            pref_rows += rows
            pref_files.append({"file": fname, "type": type_name, "rows": rows})
            print(f"  ✓ {type_name}: {rows:,}行")
        else:
            print(f"  ✗ {type_name}: ダウンロード失敗")
        time.sleep(1)

    results[pref] = {
        "code": cfg["code"],
        "status": "success" if pref_files else "failed",
        "files": len(pref_files),
        "total_rows": pref_rows,
        "details": pref_files,
    }
    total_rows_all += pref_rows
    total_files_all += len(pref_files)

# =====================================================================
# Phase 3: Extra prefectures - try common patterns
# =====================================================================
print("\n" + "=" * 60)
print("Phase 3: 追加都道府県 パターン探索")
print("=" * 60)

for cfg in EXTRA_PREF_PATTERNS:
    pref = cfg["pref"]
    prefix = cfg["prefix"]
    print(f"\n{pref} 試行中...")
    pref_dir = Path(f"data/crime/prefectures/{pref}")
    pref_dir.mkdir(parents=True, exist_ok=True)

    pref_files = []
    pref_rows = 0
    found_base = None

    # Try each base URL with each crime type
    for base in cfg["bases"]:
        # Try different naming patterns
        patterns = [
            f"{prefix}_{YEAR}{{type}}.csv",
            f"{prefix}-{YEAR}{{type}}.csv",
            f"{prefix}_{YEAR}_{{type}}.csv",
        ]
        for pat in patterns:
            test_type = "hittakuri"  # Test with smallest file
            test_fname = pat.format(type=test_type)
            test_url = base + test_fname
            test_path = pref_dir / test_fname

            if try_download(test_url, test_path):
                found_base = base
                rows, _ = count_csv_rows(test_path)
                pref_files.append({"file": test_fname, "type": "ひったくり", "rows": rows})
                pref_rows += rows
                print(f"  ✓ パターン発見: {base}")
                print(f"    ひったくり: {rows:,}行")

                # Download remaining types
                for type_key, type_name in CRIME_TYPES[1:]:
                    fname = pat.format(type=type_key)
                    url = base + fname
                    save_path = pref_dir / fname
                    if try_download(url, save_path):
                        rows, _ = count_csv_rows(save_path)
                        pref_rows += rows
                        pref_files.append({"file": fname, "type": type_name, "rows": rows})
                        print(f"    {type_name}: {rows:,}行")
                    time.sleep(0.8)
                break
            time.sleep(0.5)

        if found_base:
            break

    if not pref_files:
        print(f"  ✗ {pref}: パターン不一致")

    results[pref] = {
        "code": cfg["code"],
        "status": "success" if pref_files else "no_match",
        "files": len(pref_files),
        "total_rows": pref_rows,
        "details": pref_files,
    }
    total_rows_all += pref_rows
    total_files_all += len(pref_files)

# =====================================================================
# Phase 4: Hokkaido via HARP & Fukuoka via BODIK
# =====================================================================
print("\n" + "=" * 60)
print("Phase 4: 特殊ポータル（北海道HARP・福岡BODIK）")
print("=" * 60)

# Hokkaido HARP
print("\n北海道 (HARP OpenData)")
harp_pref_dir = Path("data/crime/prefectures/北海道")
harp_pref_dir.mkdir(parents=True, exist_ok=True)
harp_files = []
harp_rows = 0

# Try HARP CKAN API
try:
    harp_api = "https://www.harp.lg.jp/opendata/api/3/action/package_show?id=2093"
    r = requests.get(harp_api, headers=headers, timeout=15)
    if r.status_code == 200:
        data = r.json()
        resources = data.get("result", {}).get("resources", [])
        for res in resources:
            url = res.get("url", "")
            name = res.get("name", "")
            if ".csv" in url.lower():
                fname = url.split("/")[-1]
                if try_download(url, harp_pref_dir / fname):
                    rows, _ = count_csv_rows(harp_pref_dir / fname)
                    harp_rows += rows
                    harp_files.append({"file": fname, "rows": rows})
                    print(f"  ✓ {name}: {rows:,}行")
                time.sleep(1)
    else:
        print(f"  HARP API: HTTP {r.status_code}")
except Exception as e:
    print(f"  HARP: {e}")

# Try direct pattern
if not harp_files:
    for type_key, type_name in CRIME_TYPES:
        for base in [
            "https://www.harp.lg.jp/opendata/dataset/2093/resource/",
            "https://www.police.pref.hokkaido.lg.jp/info/kikaku/opendata/csv/",
        ]:
            fname = f"hokkaido_{YEAR}{type_key}.csv"
            if try_download(base + fname, harp_pref_dir / fname):
                rows, _ = count_csv_rows(harp_pref_dir / fname)
                harp_rows += rows
                harp_files.append({"file": fname, "type": type_name, "rows": rows})
                print(f"  ✓ {type_name}: {rows:,}行")
                break
            time.sleep(0.5)

results["北海道"] = {
    "code": "01",
    "status": "success" if harp_files else "failed",
    "files": len(harp_files),
    "total_rows": harp_rows,
    "details": harp_files,
}
total_rows_all += harp_rows
total_files_all += len(harp_files)

# Fukuoka BODIK
print("\n福岡県 (BODIK CKAN)")
fuk_pref_dir = Path("data/crime/prefectures/福岡県")
fuk_pref_dir.mkdir(parents=True, exist_ok=True)
fuk_files = []
fuk_rows = 0

try:
    bodik_api = "https://data.bodik.jp/api/3/action/package_show?id=400009_hanzair6"
    r = requests.get(bodik_api, headers=headers, timeout=15)
    if r.status_code == 200:
        data = r.json()
        resources = data.get("result", {}).get("resources", [])
        for res in resources:
            url = res.get("url", "")
            name = res.get("name", "")
            fmt = res.get("format", "").upper()
            if fmt == "CSV" or ".csv" in url.lower():
                fname = url.split("/")[-1] if "/" in url else f"{name}.csv"
                if not fname.endswith(".csv"):
                    fname = f"{name.replace(' ', '_')}.csv"
                if try_download(url, fuk_pref_dir / fname):
                    rows, _ = count_csv_rows(fuk_pref_dir / fname)
                    fuk_rows += rows
                    fuk_files.append({"file": fname, "rows": rows, "name": name})
                    print(f"  ✓ {name}: {rows:,}行")
                time.sleep(1)
    else:
        print(f"  BODIK API: HTTP {r.status_code}")
except Exception as e:
    print(f"  BODIK: {e}")

results["福岡県"] = {
    "code": "40",
    "status": "success" if fuk_files else "failed",
    "files": len(fuk_files),
    "total_rows": fuk_rows,
    "details": fuk_files,
}
total_rows_all += fuk_rows
total_files_all += len(fuk_files)

# Also try Chiba with known numeric pattern
print("\n千葉県 (numeric IDs)")
chiba_dir = Path("data/crime/prefectures/千葉県")
chiba_dir.mkdir(parents=True, exist_ok=True)
chiba_files = []
chiba_rows = 0

chiba_ids = {
    "000066997": "ひったくり",
    "000066998": "車上ねらい",
    "000066999": "部品ねらい",
    "000067000": "自販機ねらい",
    "000067001": "自動車盗",
    "000067002": "オートバイ盗",
    "000067003": "自転車盗",
}

for cid, cname in chiba_ids.items():
    url = f"https://www.police.pref.chiba.jp/content/common/{cid}.csv"
    fname = f"chiba_{YEAR}_{cname}.csv"
    if try_download(url, chiba_dir / fname):
        rows, _ = count_csv_rows(chiba_dir / fname)
        chiba_rows += rows
        chiba_files.append({"file": fname, "type": cname, "rows": rows})
        print(f"  ✓ {cname}: {rows:,}行")
    time.sleep(1)

results["千葉県"] = {
    "code": "12",
    "status": "success" if chiba_files else "failed",
    "files": len(chiba_files),
    "total_rows": chiba_rows,
    "details": chiba_files,
}
total_rows_all += chiba_rows
total_files_all += len(chiba_files)

# =====================================================================
# Final Report
# =====================================================================
print("\n" + "=" * 60)
print("最終結果")
print("=" * 60)

# Add Tokyo
results["東京都"] = {"code": "13", "status": "done", "files": 7, "total_rows": 29043}
total_rows_all += 29043

success_prefs = [p for p, v in results.items() if v["status"] in ("success", "done")]
failed_prefs = [p for p, v in results.items() if v["status"] in ("failed", "no_match")]

print(f"\n  成功: {len(success_prefs)}都道府県")
for p in sorted(success_prefs):
    v = results[p]
    print(f"    {p}: {v['files']}ファイル / {v.get('total_rows', 0):,}行")

print(f"\n  未取得: {len(failed_prefs)}都道府県")
for p in sorted(failed_prefs)[:10]:
    print(f"    {p}")
if len(failed_prefs) > 10:
    print(f"    ...他{len(failed_prefs)-10}府県")

print(f"\n  総ファイル数: {total_files_all + 7}")
print(f"  総レコード数: {total_rows_all:,}")

with open("data/crime/prefectures/download_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n完了: {datetime.now().isoformat()}")
