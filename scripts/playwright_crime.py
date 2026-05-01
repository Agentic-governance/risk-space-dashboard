"""
Playwright で JS必須の都道府県警サイトから犯罪CSVをダウンロード
"""
import asyncio, json, os, time, re
from pathlib import Path
from datetime import datetime

BASE = Path("/Users/reikumaki/Library/CloudStorage/GoogleDrive-teddykmk@gmail.com/マイドライブ/piracy_detector/claude_code/risk_space")
os.chdir(BASE)

# NPA公式リンクから判明したURL + 追加調査URL
TARGETS = [
    # NPA公式リンクあり
    {"pref": "北海道", "urls": [
        "https://www.harp.lg.jp/opendata/dataset/2093",
        "https://www.harp.lg.jp/opendata/dataset/1537",
        "https://www.harp.lg.jp/opendata/dataset/1184",
    ]},
    {"pref": "茨城県", "urls": [
        "https://www.ibaraki-opendata.jp/index.php",
        "https://www.pref.ibaraki.jp/kenkei/a01_safety/map/crime.html",
    ]},
    {"pref": "群馬県", "urls": [
        "https://www.police.pref.gunma.jp/site/police/28701.html",
    ]},
    {"pref": "石川県", "urls": [
        "https://www2.police.pref.ishikawa.lg.jp/security/security24/",
        "https://www2.police.pref.ishikawa.lg.jp/security/security23/",
    ]},
    {"pref": "三重県", "urls": [
        "http://www.police.pref.mie.jp/safety_info/op_data_index.html",
    ]},
    {"pref": "京都府", "urls": [
        "https://www.pref.kyoto.jp/fukei/anzen/bouhan/opendata.html",
        "https://www.pref.kyoto.jp/fukei/anzen/toukei/index.html",
    ]},
    {"pref": "和歌山県", "urls": [
        "https://www.police.pref.wakayama.lg.jp/04_toukei/index.html",
    ]},
    {"pref": "島根県", "urls": [
        "https://shimane-opendata.jp/datasets/1055",
    ]},
    {"pref": "岡山県", "urls": [
        "https://www.okayama-opendata.jp/opendata/api/1/detail?id=d3a8dfb0-1c7e-4a81-809d-b0e7c96cc3be",
        "https://www.okayama-opendata.jp/datasets?tag=防犯",
    ]},
    {"pref": "広島県", "urls": [
        "https://hiroshima-opendata.dataeye.jp/datasets?group=gr_0200",
    ]},
    {"pref": "香川県", "urls": [
        "https://opendata.pref.kagawa.lg.jp/dataset/bunya/bosai/",
    ]},
    {"pref": "高知県", "urls": [
        "https://www.police.pref.kochi.lg.jp/docs/2023111400109/",
    ]},
    {"pref": "沖縄県", "urls": [
        "https://www.police.pref.okinawa.jp/category/bunya/tokei",
    ]},
    # NPA公式リンクなし - パターン推定
    {"pref": "栃木県", "urls": [
        "https://www.police.pref.tochigi.lg.jp/kenke/kikaku/opendata/",
        "https://tochigi-opendata.jp/",
    ]},
    {"pref": "新潟県", "urls": [
        "https://www.police.pref.niigata.jp/",
        "https://www.pref.niigata.lg.jp/sec/kikakuka/opendata.html",
    ]},
    {"pref": "福井県", "urls": [
        "https://www.police.pref.fukui.jp/",
        "https://www.pref.fukui.lg.jp/doc/toukei-jouhou/opendata/",
    ]},
    {"pref": "山梨県", "urls": [
        "https://www.police.pref.yamanashi.jp/",
        "https://www.pref.yamanashi.jp/opendata/",
    ]},
    {"pref": "滋賀県", "urls": [
        "https://www.police.pref.shiga.jp/",
    ]},
    {"pref": "鳥取県", "urls": [
        "https://www.police.pref.tottori.jp/",
        "https://db.pref.tottori.jp/opendata.nsf",
    ]},
    {"pref": "佐賀県", "urls": [
        "https://www.police.pref.saga.jp/",
        "https://data.bodik.jp/dataset?tags=佐賀県+犯罪",
    ]},
    {"pref": "熊本県", "urls": [
        "https://www.police.pref.kumamoto.jp/",
    ]},
    {"pref": "大分県", "urls": [
        "https://www.police.pref.oita.jp/",
        "https://data.bodik.jp/dataset?tags=大分県+犯罪",
    ]},
    {"pref": "宮崎県", "urls": [
        "https://www.police.pref.miyazaki.lg.jp/",
    ]},
    {"pref": "鹿児島県", "urls": [
        "https://www.police.pref.kagoshima.jp/",
        "https://opendata.pref.kagoshima.jp/",
    ]},
]


async def download_from_page(page, url, pref_dir, pref):
    """1ページからCSV/XLSXリンクを探してDL"""
    downloaded = []
    try:
        await page.goto(url, timeout=20000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)  # JS rendering待ち

        # CSVリンクを探す
        links = await page.query_selector_all("a")
        csv_links = []
        for link in links:
            href = await link.get_attribute("href") or ""
            text = (await link.inner_text()).strip()
            if any(ext in href.lower() for ext in [".csv", ".xlsx", ".xls"]):
                if href.startswith("http"):
                    full = href
                elif href.startswith("/"):
                    parts = url.split("/")
                    full = f"{parts[0]}//{parts[2]}{href}"
                else:
                    full = f"{'/'.join(url.split('/')[:-1])}/{href}"
                csv_links.append({"url": full, "text": text})

        # サブページも探す（オープンデータ・犯罪関連）
        if not csv_links:
            sub_links = []
            for link in links:
                href = await link.get_attribute("href") or ""
                text = (await link.inner_text()).strip()
                if any(kw in text for kw in ["オープンデータ", "犯罪", "窃盗", "統計", "2024", "令和6"]) or \
                   any(kw in href for kw in ["opendata", "hanzai", "settou", "2024", "r06"]):
                    if href.startswith("http"):
                        sub_url = href
                    elif href.startswith("/"):
                        parts = url.split("/")
                        sub_url = f"{parts[0]}//{parts[2]}{href}"
                    else:
                        sub_url = f"{'/'.join(url.split('/')[:-1])}/{href}"
                    sub_links.append(sub_url)

            # サブページを最大3つ訪問
            for sub_url in sub_links[:3]:
                try:
                    await page.goto(sub_url, timeout=15000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(1500)
                    sub_anchors = await page.query_selector_all("a")
                    for a in sub_anchors:
                        href = await a.get_attribute("href") or ""
                        text = (await a.inner_text()).strip()
                        if any(ext in href.lower() for ext in [".csv", ".xlsx"]):
                            if href.startswith("http"):
                                full = href
                            elif href.startswith("/"):
                                parts = sub_url.split("/")
                                full = f"{parts[0]}//{parts[2]}{href}"
                            else:
                                full = f"{'/'.join(sub_url.split('/')[:-1])}/{href}"
                            csv_links.append({"url": full, "text": text})
                    if csv_links:
                        break
                except:
                    pass

        # CKAN API チェック
        if not csv_links and ("opendata" in url or "dataset" in url or "bodik" in url):
            try:
                # CKAN package_show
                ckan_base = "/".join(url.split("/")[:3])
                dataset_id = url.split("/")[-1].split("?")[0]
                api_url = f"{ckan_base}/api/3/action/package_show?id={dataset_id}"
                resp = await page.goto(api_url, timeout=10000)
                if resp and resp.status == 200:
                    body = await page.inner_text("body")
                    import json as jn
                    data = jn.loads(body)
                    for res in data.get("result", {}).get("resources", []):
                        dl_url = res.get("url", "")
                        name = res.get("name", "")
                        fmt = res.get("format", "").upper()
                        if fmt in ("CSV", "XLSX") or ".csv" in dl_url.lower():
                            csv_links.append({"url": dl_url, "text": name})
            except:
                pass

        if not csv_links:
            return downloaded

        print(f"    {len(csv_links)}件のCSVリンク発見")

        # ダウンロード（最大10件）
        import requests
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        seen = set()
        for link in csv_links[:10]:
            dl_url = link["url"]
            if dl_url in seen:
                continue
            seen.add(dl_url)
            try:
                r = requests.get(dl_url, headers=headers, timeout=30, allow_redirects=True)
                ct = r.headers.get("Content-Type", "")
                if r.status_code == 200 and len(r.content) > 100:
                    if "text/html" in ct and (r.content[:20].startswith(b"<!") or b"<html" in r.content[:200].lower()):
                        continue
                    fname = dl_url.split("/")[-1].split("?")[0]
                    if not fname or len(fname) < 3:
                        fname = f"{pref}_data_{len(downloaded)}.csv"
                    save_path = pref_dir / fname
                    with open(save_path, "wb") as f:
                        f.write(r.content)
                    downloaded.append({"file": fname, "size": len(r.content), "text": link["text"][:50]})
                    print(f"      ✓ {fname} ({len(r.content)//1024}KB)")
            except:
                pass

    except Exception as e:
        pass

    return downloaded


async def main():
    from playwright.async_api import async_playwright

    results = {}
    total_files = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )

        for target in TARGETS:
            pref = target["pref"]
            if pref == "東京都":
                continue

            print(f"\n{pref} 処理中...")
            pref_dir = Path(f"data/crime/prefectures/{pref}")
            pref_dir.mkdir(parents=True, exist_ok=True)

            all_downloaded = []
            page = await context.new_page()

            for url in target["urls"]:
                print(f"  → {url[:60]}...")
                dl = await download_from_page(page, url, pref_dir, pref)
                all_downloaded.extend(dl)
                if all_downloaded:
                    break  # 成功したらスキップ
                await asyncio.sleep(1)

            await page.close()

            results[pref] = {
                "status": "success" if all_downloaded else "failed",
                "files": len(all_downloaded),
                "details": all_downloaded,
            }
            total_files += len(all_downloaded)

            if all_downloaded:
                print(f"  ✓ {pref}: {len(all_downloaded)}ファイル取得")
            else:
                print(f"  ✗ {pref}: 取得失敗")

            await asyncio.sleep(2)

        await browser.close()

    # Summary
    success = [p for p, v in results.items() if v["status"] == "success"]
    failed = [p for p, v in results.items() if v["status"] == "failed"]

    print(f"\n{'='*60}")
    print(f"Playwright取得結果")
    print(f"{'='*60}")
    print(f"  成功: {len(success)}都道府県")
    for p in success:
        v = results[p]
        print(f"    {p}: {v['files']}ファイル")
    print(f"  失敗: {len(failed)}都道府県")
    for p in failed:
        print(f"    {p}")
    print(f"  総ファイル: {total_files}")

    with open("data/crime/prefectures/playwright_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n完了: {datetime.now().isoformat()}")

asyncio.run(main())
