#!/usr/bin/env python3
"""
cron_news_crime.py — Crime News RSS Fetcher
============================================
Fetches crime-related news from multiple Japanese RSS feeds, extracts
prefecture/city from titles, and geo-codes to approximate lat/lon.

Sources:
  A. NHK事件・事故: https://www3.nhk.or.jp/rss/news/cat1.xml
  B. NHK社会: https://www3.nhk.or.jp/rss/news/cat7.xml
  C. 毎日新聞事件: https://mainichi.jp/rss/etc/mainichi-flash.rss

Output: docs/data/news_crime_latest.json
Format: {incidents: [{title, url, date, prefecture, subtype, lat, lon}]}

Usage:
    python scripts/cron_news_crime.py
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(BASE_DIR, "docs", "data", "news_crime_latest.json")
NORM_DIR = os.path.join(BASE_DIR, "data", "normalized")

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
os.makedirs(NORM_DIR, exist_ok=True)

# ── Constants ──────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
}

RSS_FEEDS = [
    {
        "name": "nhk_crime",
        "url": "https://www3.nhk.or.jp/rss/news/cat1.xml",
        "description": "NHK事件・事故",
    },
    {
        "name": "nhk_society",
        "url": "https://www3.nhk.or.jp/rss/news/cat7.xml",
        "description": "NHK社会",
    },
    {
        "name": "mainichi_flash",
        "url": "https://mainichi.jp/rss/etc/mainichi-flash.rss",
        "description": "毎日新聞フラッシュ",
    },
]

# Crime keywords for filtering
CRIME_KEYWORDS = {
    "殺人", "強盗", "窃盗", "詐欺", "暴行", "傷害", "逮捕", "刺す", "刺され",
    "遺体", "死体", "不審者", "声かけ", "つきまとい", "痴漢", "盗撮", "わいせつ",
    "露出", "ひったくり", "凶器", "拳銃", "刃物", "放火", "火災", "爆発物",
    "特殊詐欺", "振り込め詐欺", "オレオレ詐欺", "行方不明", "誘拐", "監禁",
    "ストーカー", "脅迫", "恐喝", "性犯罪", "性的暴行", "レイプ", "援助交際",
    "薬物", "覚醒剤", "大麻", "密輸", "テロ", "爆弾",
}

# Subtype mapping from crime keywords
CRIME_SUBTYPE_MAP = {
    "殺人": "murder",
    "強盗": "robbery",
    "窃盗": "theft",
    "詐欺": "fraud",
    "特殊詐欺": "fraud",
    "振り込め詐欺": "fraud",
    "オレオレ詐欺": "fraud",
    "暴行": "assault",
    "傷害": "assault",
    "刺す": "assault",
    "刺され": "assault",
    "不審者": "suspicious_person",
    "声かけ": "solicitation",
    "つきまとい": "stalking",
    "ストーカー": "stalking",
    "痴漢": "groping",
    "盗撮": "voyeurism",
    "わいせつ": "indecent_act",
    "露出": "exposure",
    "ひったくり": "purse_snatching",
    "凶器": "weapon",
    "拳銃": "weapon",
    "刃物": "weapon",
    "放火": "arson",
    "薬物": "drug",
    "覚醒剤": "drug",
    "大麻": "drug",
    "誘拐": "kidnapping",
    "監禁": "confinement",
    "テロ": "terrorism",
    "爆弾": "terrorism",
}

# Prefecture name → (lat, lon) approximate center
PREF_COORDS = {
    "北海道": (43.0642, 141.3469),
    "青森": (40.8244, 140.7400),
    "岩手": (39.7036, 141.1527),
    "宮城": (38.2688, 140.8721),
    "秋田": (39.7186, 140.1024),
    "山形": (38.2404, 140.3636),
    "福島": (37.7502, 140.4675),
    "茨城": (36.3418, 140.4468),
    "栃木": (36.5658, 139.8836),
    "群馬": (36.3911, 139.0608),
    "埼玉": (35.8573, 139.6489),
    "千葉": (35.6073, 140.1063),
    "東京": (35.6762, 139.6503),
    "神奈川": (35.4478, 139.6425),
    "新潟": (37.9026, 139.0232),
    "富山": (36.6959, 137.2137),
    "石川": (36.5947, 136.6256),
    "福井": (36.0652, 136.2217),
    "山梨": (35.6641, 138.5684),
    "長野": (36.6513, 138.1810),
    "岐阜": (35.3911, 136.7223),
    "静岡": (34.9769, 138.3831),
    "愛知": (35.1802, 136.9066),
    "三重": (34.7303, 136.5086),
    "滋賀": (35.0045, 135.8686),
    "京都": (35.0116, 135.7681),
    "大阪": (34.6937, 135.5023),
    "兵庫": (34.6913, 135.1830),
    "奈良": (34.6851, 135.8329),
    "和歌山": (34.2260, 135.1675),
    "鳥取": (35.5039, 134.2381),
    "島根": (35.4723, 133.0505),
    "岡山": (34.6618, 133.9344),
    "広島": (34.3963, 132.4596),
    "山口": (34.1859, 131.4706),
    "徳島": (34.0657, 134.5593),
    "香川": (34.3401, 134.0434),
    "愛媛": (33.8417, 132.7657),
    "高知": (33.5597, 133.5311),
    "福岡": (33.6064, 130.4183),
    "佐賀": (33.2635, 130.3008),
    "長崎": (32.7448, 129.8737),
    "熊本": (32.7898, 130.7417),
    "大分": (33.2382, 131.6126),
    "宮崎": (31.9111, 131.4239),
    "鹿児島": (31.5602, 130.5581),
    "沖縄": (26.2124, 127.6809),
}

# Major city → prefecture mapping (for geocoding from city mentions)
CITY_TO_PREF = {
    "札幌": "北海道", "函館": "北海道", "旭川": "北海道",
    "仙台": "宮城", "盛岡": "岩手", "秋田": "秋田", "山形": "山形", "福島": "福島",
    "水戸": "茨城", "宇都宮": "栃木", "前橋": "群馬", "高崎": "群馬",
    "さいたま": "埼玉", "川口": "埼玉", "熊谷": "埼玉",
    "千葉": "千葉", "船橋": "千葉", "松戸": "千葉",
    "新宿": "東京", "渋谷": "東京", "池袋": "東京", "上野": "東京",
    "品川": "東京", "世田谷": "東京", "江戸川": "東京", "足立": "東京",
    "横浜": "神奈川", "川崎": "神奈川", "相模原": "神奈川",
    "新潟": "新潟", "金沢": "石川", "富山": "富山", "福井": "福井",
    "甲府": "山梨", "長野": "長野", "松本": "長野",
    "静岡": "静岡", "浜松": "静岡", "名古屋": "愛知", "岐阜": "岐阜", "津": "三重",
    "大津": "滋賀", "京都": "京都", "大阪": "大阪", "堺": "大阪",
    "神戸": "兵庫", "姫路": "兵庫", "奈良": "奈良", "和歌山": "和歌山",
    "鳥取": "鳥取", "松江": "島根", "岡山": "岡山", "倉敷": "岡山",
    "広島": "広島", "福山": "広島", "山口": "山口",
    "徳島": "徳島", "高松": "香川", "松山": "愛媛", "高知": "高知",
    "福岡": "福岡", "北九州": "福岡", "久留米": "福岡",
    "佐賀": "佐賀", "長崎": "長崎", "熊本": "熊本", "大分": "大分",
    "宮崎": "宮崎", "鹿児島": "鹿児島", "那覇": "沖縄",
}

# ── HTTP helper ────────────────────────────────────────────────────────────

def fetch_url(url: str, retries: int = 3, timeout: int = 20) -> Optional[str]:
    """Fetch raw text from URL with exponential-backoff retry."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                charset = resp.headers.get_content_charset("utf-8")
                return resp.read().decode(charset, errors="replace")
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            code = getattr(e, "code", None)
            print(f"  [WARN] fetch attempt {attempt + 1}/{retries}: {url} -> {e}",
                  file=sys.stderr)
            if code == 404:
                return None
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
        except Exception as e:
            print(f"  [WARN] fetch unexpected error: {url} -> {e}", file=sys.stderr)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None

# ── Parsing helpers ────────────────────────────────────────────────────────

def is_crime_related(text: str) -> bool:
    """Return True if text contains at least one crime keyword."""
    return any(kw in text for kw in CRIME_KEYWORDS)


def classify_subtype(text: str) -> str:
    """Return the best-match crime subtype from text."""
    for kw, subtype in CRIME_SUBTYPE_MAP.items():
        if kw in text:
            return subtype
    return "crime_news"


def extract_prefecture(text: str) -> Optional[str]:
    """
    Extract prefecture name from text.
    Checks direct prefecture name matches (都/道/府/県 suffix or bare name),
    then falls back to city-level lookup.
    """
    # Direct prefecture match with suffix
    for pref in PREF_COORDS:
        suffixes = ["都", "道", "府", "県"]
        if pref == "東京":
            suffixes = ["都"]
        elif pref == "北海道":
            suffixes = [""]
        elif pref in ("大阪", "京都"):
            suffixes = ["府"]
        else:
            suffixes = ["県"]
        for sfx in suffixes:
            if (pref + sfx) in text or pref in text:
                return pref

    # City-level fallback
    for city, pref in CITY_TO_PREF.items():
        if city in text:
            return pref

    return None


def geocode_prefecture(pref: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    """Return approximate (lat, lon) for a prefecture name."""
    if pref and pref in PREF_COORDS:
        return PREF_COORDS[pref]
    return None, None


def parse_pubdate(raw: str) -> Optional[str]:
    """Parse RFC 2822 pubDate string to ISO-8601 UTC. Returns None on failure."""
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw.strip())
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return None

# ── RSS fetcher ────────────────────────────────────────────────────────────

def fetch_rss(feed: dict) -> list:
    """
    Fetch and parse one RSS feed. Filters for crime keywords.
    Returns list of normalized incident dicts.
    """
    url = feed["url"]
    name = feed["name"]
    print(f"\n  [{name}] {url}")
    xml = fetch_url(url, timeout=15)
    if not xml:
        print(f"    [SKIP] Not reachable.")
        return []

    items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
    incidents = []
    for item in items:
        title_m = re.search(r"<title[^>]*>(.*?)</title>", item, re.DOTALL)
        desc_m = re.search(r"<description[^>]*>(.*?)</description>", item, re.DOTALL)
        date_m = re.search(r"<pubDate>(.*?)</pubDate>", item)
        link_m = re.search(r"<link>(.*?)</link>", item)
        guid_m = re.search(r"<guid[^>]*>(.*?)</guid>", item)

        def clean(m) -> str:
            if not m:
                return ""
            raw = m.group(1)
            # Strip CDATA
            raw = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", raw, flags=re.DOTALL)
            # Strip HTML tags
            raw = re.sub(r"<[^>]+>", "", raw)
            return raw.strip()

        title = clean(title_m)
        desc = clean(desc_m)
        pub_date_raw = date_m.group(1).strip() if date_m else ""
        link = clean(link_m) or clean(guid_m)

        combined = title + " " + desc
        if not is_crime_related(combined):
            continue

        subtype = classify_subtype(combined)
        pref = extract_prefecture(combined)
        lat, lon = geocode_prefecture(pref)
        date_iso = parse_pubdate(pub_date_raw)
        date_str = date_iso[:10] if date_iso else datetime.now(timezone.utc).strftime("%Y-%m-%d")

        incidents.append({
            "title": title[:200],
            "url": link[:500],
            "date": date_str,
            "prefecture": pref or "",
            "subtype": subtype,
            "lat": round(lat, 4) if lat is not None else None,
            "lon": round(lon, 4) if lon is not None else None,
            "source": name,
        })

    print(f"    Crime-related items: {len(incidents)}")
    return incidents

# ── Main ───────────────────────────────────────────────────────────────────

def main():
    now_utc = datetime.now(timezone.utc)

    print("=" * 60)
    print("cron_news_crime.py — Crime News RSS Fetcher")
    print(f"  fetched_at: {now_utc.isoformat(timespec='seconds')}")
    print(f"  feeds     : {len(RSS_FEEDS)}")
    print("=" * 60)

    all_incidents = []
    for feed in RSS_FEEDS:
        incidents = fetch_rss(feed)
        all_incidents.extend(incidents)
        if feed != RSS_FEEDS[-1]:
            time.sleep(1)

    # Deduplicate by URL
    seen_urls: set = set()
    unique: list = []
    for inc in all_incidents:
        key = inc.get("url") or inc.get("title", "")
        if key and key in seen_urls:
            continue
        seen_urls.add(key)
        unique.append(inc)

    # Sort by date descending
    unique.sort(key=lambda x: x.get("date", ""), reverse=True)

    from collections import Counter
    src_counts = Counter(i["source"] for i in unique)
    type_counts = Counter(i["subtype"] for i in unique)
    pref_counts = Counter(i["prefecture"] for i in unique if i["prefecture"])

    output = {
        "metadata": {
            "sources": [f["name"] for f in RSS_FEEDS],
            "fetched_at": now_utc.isoformat(timespec="seconds"),
            "total_count": len(unique),
            "source_counts": dict(src_counts),
            "type_counts": dict(type_counts),
            "top_prefectures": dict(pref_counts.most_common(10)),
            "description": (
                "Crime-related news headlines from Japanese RSS feeds. "
                "Prefecture and subtype are extracted from title/description. "
                "lat/lon is the approximate center of the inferred prefecture."
            ),
        },
        "incidents": unique,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    norm_path = os.path.join(NORM_DIR, "news_crime_latest.json")
    with open(norm_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[DONE] {len(unique)} crime incidents written to:")
    print(f"  {OUT_PATH}")
    print(f"  {norm_path}")
    print(f"  Source breakdown: {dict(src_counts)}")
    print(f"  Type breakdown:   {dict(type_counts)}")
    if pref_counts:
        print(f"  Top prefectures:  {dict(pref_counts.most_common(5))}")


if __name__ == "__main__":
    main()
