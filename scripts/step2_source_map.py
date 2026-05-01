#!/usr/bin/env python3
"""Step 2: Build 47 prefecture source URL master - check which police/open data pages are reachable."""

import json
import os
import time
from datetime import datetime

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "data", "realtime")
os.makedirs(OUT_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Prefecture police/safety info URLs
# Format: (prefecture_name, code, [list of candidate URLs to check])
PREFECTURE_SOURCES = [
    ("北海道", "01", [
        "https://www.police.pref.hokkaido.lg.jp/",
        "https://www.gaccom.jp/safety/area/p1",
    ]),
    ("青森県", "02", [
        "https://www.police.pref.aomori.jp/",
        "https://www.gaccom.jp/safety/area/p2",
    ]),
    ("岩手県", "03", [
        "https://www.pref.iwate.jp/kenkei/",
        "https://www.gaccom.jp/safety/area/p3",
    ]),
    ("宮城県", "04", [
        "https://www.police.pref.miyagi.jp/",
        "https://www.gaccom.jp/safety/area/p4",
    ]),
    ("秋田県", "05", [
        "https://www.police.pref.akita.jp/",
        "https://www.gaccom.jp/safety/area/p5",
    ]),
    ("山形県", "06", [
        "https://www.pref.yamagata.jp/police/",
        "https://www.gaccom.jp/safety/area/p6",
    ]),
    ("福島県", "07", [
        "https://www.police.pref.fukushima.jp/",
        "https://www.gaccom.jp/safety/area/p7",
    ]),
    ("茨城県", "08", [
        "https://www.pref.ibaraki.jp/kenkei/",
        "https://www.gaccom.jp/safety/area/p8",
    ]),
    ("栃木県", "09", [
        "https://www.pref.tochigi.lg.jp/keisatu/",
        "https://www.gaccom.jp/safety/area/p9",
    ]),
    ("群馬県", "10", [
        "https://www.police.pref.gunma.jp/",
        "https://www.gaccom.jp/safety/area/p10",
    ]),
    ("埼玉県", "11", [
        "https://www.police.pref.saitama.lg.jp/",
        "https://www.gaccom.jp/safety/area/p11",
    ]),
    ("千葉県", "12", [
        "https://www.police.pref.chiba.jp/",
        "https://www.gaccom.jp/safety/area/p12",
    ]),
    ("東京都", "13", [
        "https://www.keishicho.metro.tokyo.lg.jp/",
        "https://www.gaccom.jp/safety/area/p13",
    ]),
    ("神奈川県", "14", [
        "https://www.police.pref.kanagawa.jp/",
        "https://www.gaccom.jp/safety/area/p14",
    ]),
    ("新潟県", "15", [
        "https://www.police.pref.niigata.jp/",
        "https://www.gaccom.jp/safety/area/p15",
    ]),
    ("富山県", "16", [
        "https://www.pref.toyama.jp/sections/1001/",
        "https://www.gaccom.jp/safety/area/p16",
    ]),
    ("石川県", "17", [
        "https://www.pref.ishikawa.lg.jp/kensei/kouan/",
        "https://www.gaccom.jp/safety/area/p17",
    ]),
    ("福井県", "18", [
        "https://www.pref.fukui.jp/kenkei/",
        "https://www.gaccom.jp/safety/area/p18",
    ]),
    ("山梨県", "19", [
        "https://www.pref.yamanashi.jp/police/",
        "https://www.gaccom.jp/safety/area/p19",
    ]),
    ("長野県", "20", [
        "https://www.pref.nagano.lg.jp/police/",
        "https://www.gaccom.jp/safety/area/p20",
    ]),
    ("岐阜県", "21", [
        "https://www.pref.gifu.lg.jp/police/",
        "https://www.gaccom.jp/safety/area/p21",
    ]),
    ("静岡県", "22", [
        "https://www.pref.shizuoka.jp/police/",
        "https://www.gaccom.jp/safety/area/p22",
    ]),
    ("愛知県", "23", [
        "https://www.pref.aichi.jp/police/",
        "https://www.gaccom.jp/safety/area/p23",
    ]),
    ("三重県", "24", [
        "https://www.police.pref.mie.jp/",
        "https://www.gaccom.jp/safety/area/p24",
    ]),
    ("滋賀県", "25", [
        "https://www.pref.shiga.lg.jp/police/",
        "https://www.gaccom.jp/safety/area/p25",
    ]),
    ("京都府", "26", [
        "https://www.pref.kyoto.jp/fukei/",
        "https://www.gaccom.jp/safety/area/p26",
    ]),
    ("大阪府", "27", [
        "https://www.police.pref.osaka.lg.jp/",
        "https://www.gaccom.jp/safety/area/p27",
    ]),
    ("兵庫県", "28", [
        "https://www.police.pref.hyogo.lg.jp/",
        "https://www.gaccom.jp/safety/area/p28",
    ]),
    ("奈良県", "29", [
        "https://www.police.pref.nara.jp/",
        "https://www.gaccom.jp/safety/area/p29",
    ]),
    ("和歌山県", "30", [
        "https://www.police.pref.wakayama.lg.jp/",
        "https://www.gaccom.jp/safety/area/p30",
    ]),
    ("鳥取県", "31", [
        "https://www.pref.tottori.lg.jp/police/",
        "https://www.gaccom.jp/safety/area/p31",
    ]),
    ("島根県", "32", [
        "https://www.pref.shimane.lg.jp/police/",
        "https://www.gaccom.jp/safety/area/p32",
    ]),
    ("岡山県", "33", [
        "https://www.pref.okayama.jp/page/detail-4415.html",
        "https://www.gaccom.jp/safety/area/p33",
    ]),
    ("広島県", "34", [
        "https://www.pref.hiroshima.lg.jp/site/police/",
        "https://www.gaccom.jp/safety/area/p34",
    ]),
    ("山口県", "35", [
        "https://www.police.pref.yamaguchi.lg.jp/",
        "https://www.gaccom.jp/safety/area/p35",
    ]),
    ("徳島県", "36", [
        "https://www.police.pref.tokushima.jp/",
        "https://www.gaccom.jp/safety/area/p36",
    ]),
    ("香川県", "37", [
        "https://www.pref.kagawa.lg.jp/police/",
        "https://www.gaccom.jp/safety/area/p37",
    ]),
    ("愛媛県", "38", [
        "https://www.police.pref.ehime.jp/",
        "https://www.gaccom.jp/safety/area/p38",
    ]),
    ("高知県", "39", [
        "https://www.police.pref.kochi.lg.jp/",
        "https://www.gaccom.jp/safety/area/p39",
    ]),
    ("福岡県", "40", [
        "https://www.police.pref.fukuoka.jp/",
        "https://www.gaccom.jp/safety/area/p40",
    ]),
    ("佐賀県", "41", [
        "https://www.police.pref.saga.jp/",
        "https://www.gaccom.jp/safety/area/p41",
    ]),
    ("長崎県", "42", [
        "https://www.police.pref.nagasaki.jp/",
        "https://www.gaccom.jp/safety/area/p42",
    ]),
    ("熊本県", "43", [
        "https://www.police.pref.kumamoto.jp/",
        "https://www.gaccom.jp/safety/area/p43",
    ]),
    ("大分県", "44", [
        "https://www.pref.oita.jp/site/keisatu/",
        "https://www.gaccom.jp/safety/area/p44",
    ]),
    ("宮崎県", "45", [
        "https://www.pref.miyazaki.lg.jp/police/",
        "https://www.gaccom.jp/safety/area/p45",
    ]),
    ("鹿児島県", "46", [
        "https://www.pref.kagoshima.jp/police/",
        "https://www.gaccom.jp/safety/area/p46",
    ]),
    ("沖縄県", "47", [
        "https://www.police.pref.okinawa.jp/",
        "https://www.gaccom.jp/safety/area/p47",
    ]),
]


def check_url(url, timeout=10):
    """Check if URL is reachable. Returns (status_code, response_time_ms) or (error, -1)."""
    try:
        start = time.time()
        resp = requests.head(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        elapsed = int((time.time() - start) * 1000)
        return resp.status_code, elapsed
    except requests.exceptions.SSLError:
        # Retry without SSL verification for police sites with bad certs
        try:
            start = time.time()
            resp = requests.head(url, headers=HEADERS, timeout=timeout, allow_redirects=True, verify=False)
            elapsed = int((time.time() - start) * 1000)
            return resp.status_code, elapsed
        except Exception as e:
            return str(e)[:80], -1
    except Exception as e:
        return str(e)[:80], -1


def main():
    print("=" * 60)
    print("Step 2: Building 47 prefecture source URL master")
    print("=" * 60)

    source_map = {}
    reachable_count = 0
    gaccom_count = 0

    for pref_name, code, urls in PREFECTURE_SOURCES:
        print(f"  [{code}] {pref_name}...", end=" ", flush=True)
        sources = []

        for url in urls:
            status, latency = check_url(url)
            is_ok = isinstance(status, int) and status < 400
            sources.append({
                "url": url,
                "status": status,
                "latency_ms": latency,
                "reachable": is_ok,
                "type": "gaccom" if "gaccom.jp" in url else "police",
            })
            time.sleep(0.5)

        police_ok = any(s["reachable"] and s["type"] == "police" for s in sources)
        gaccom_ok = any(s["reachable"] and s["type"] == "gaccom" for s in sources)

        if police_ok:
            reachable_count += 1
        if gaccom_ok:
            gaccom_count += 1

        status_str = "POLICE_OK" if police_ok else ("GACCOM_OK" if gaccom_ok else "FAIL")
        print(status_str)

        source_map[code] = {
            "prefecture": pref_name,
            "code": code,
            "sources": sources,
            "police_reachable": police_ok,
            "gaccom_reachable": gaccom_ok,
            "has_any_source": police_ok or gaccom_ok,
        }

    # Also add JASPIC / nordot as a universal source
    source_map["jaspic"] = {
        "name": "日本不審者情報センター (JASPIC)",
        "type": "aggregator",
        "feeds": [
            {"url": "https://news.jp/i/-/units/133089874031904245", "category": "不審者情報"},
            {"url": "https://news.jp/i/-/units/402299803402830945", "category": "危険動物情報"},
            {"url": "https://news.jp/i/-/units/468644598573220961", "category": "財産ねらい情報"},
        ],
        "coverage": "全国",
        "reachable": True,
    }

    # Add gaccom.jp as universal source
    source_map["gaccom"] = {
        "name": "ガッコム安全ナビ",
        "type": "aggregator",
        "base_url": "https://www.gaccom.jp/safety/",
        "coverage": "全国",
        "reachable": True,
    }

    result = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_prefectures": 47,
            "police_sites_reachable": reachable_count,
            "gaccom_reachable": gaccom_count,
            "any_source_available": sum(1 for k, v in source_map.items() if isinstance(v, dict) and v.get("has_any_source")),
            "universal_aggregators": ["JASPIC (nordot/news.jp)", "ガッコム安全ナビ"],
        },
        "prefectures": source_map,
    }

    out_path = os.path.join(OUT_DIR, "source_map.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"Results:")
    print(f"  Police sites reachable: {reachable_count}/47")
    print(f"  Gaccom pages reachable: {gaccom_count}/47")
    print(f"  Saved: {out_path}")
    print(f"{'=' * 60}")

    return result


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    main()
