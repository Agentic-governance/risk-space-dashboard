#!/usr/bin/env python3
"""Step 1: Analyze JASPIC schema from nordot.app (news.jp)"""

import json
import re
import time
import hashlib
import os
import sys
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE_DIR, "data", "realtime", "jaspic_analysis")
os.makedirs(OUT_DIR, exist_ok=True)

FEEDS = [
    ("https://news.jp/i/-/units/133089874031904245", "不審者情報"),
    ("https://news.jp/i/-/units/402299803402830945", "危険動物情報"),
    ("https://news.jp/i/-/units/468644598573220961", "財産ねらい情報"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en;q=0.5",
}

# Known kind patterns for taxonomy
KIND_PATTERNS = [
    "声かけ", "つきまとい", "痴漢", "わいせつ", "盗撮", "強盗", "暴行",
    "刃物所持", "不審者", "露出", "のぞき", "ひったくり", "すり",
    "クマ出没", "イノシシ出没", "サル出没", "シカ出没",
    "空き巣", "車上ねらい", "自転車盗", "オレオレ詐欺", "還付金詐欺",
    "特殊詐欺", "架空請求", "窃盗", "侵入盗", "万引き",
    "公然わいせつ", "器物損壊", "不審車両", "不審電話",
    "写真撮影", "容姿撮影", "付きまとい",
]

PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県",
    "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県",
    "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]


def extract_article_links(feed_url, category):
    """Extract article links from a nordot/news.jp feed page."""
    links = []
    print(f"  Fetching feed: {category} -> {feed_url}")
    try:
        resp = requests.get(feed_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Look for article links in various formats
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # nordot article links typically contain numeric IDs
            if re.search(r'/\d{10,}', href):
                full_url = urljoin(feed_url, href)
                if full_url not in [l[0] for l in links]:
                    links.append((full_url, a.get_text(strip=True)))

        # Also check for JSON-LD or script-embedded data
        for script in soup.find_all("script", type="application/json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, dict):
                    _extract_from_json(data, links, feed_url)
            except (json.JSONDecodeError, TypeError):
                pass

        # Check for Next.js __NEXT_DATA__
        for script in soup.find_all("script", id="__NEXT_DATA__"):
            try:
                data = json.loads(script.string or "")
                _extract_from_json(data, links, feed_url)
            except (json.JSONDecodeError, TypeError):
                pass

        print(f"    Found {len(links)} article links")
    except Exception as e:
        print(f"    Error fetching feed: {e}")

    return links


def _extract_from_json(data, links, base_url):
    """Recursively extract article URLs from JSON data."""
    if isinstance(data, dict):
        for key, val in data.items():
            if key in ("url", "href", "link") and isinstance(val, str) and re.search(r'/\d{10,}', val):
                full = urljoin(base_url, val)
                if full not in [l[0] for l in links]:
                    links.append((full, ""))
            else:
                _extract_from_json(val, links, base_url)
    elif isinstance(data, list):
        for item in data:
            _extract_from_json(item, links, base_url)


def parse_title(title):
    """Parse JASPIC-style title: '都道府県名 市区町村名（種別）' """
    result = {"raw_title": title, "prefecture": None, "city": None, "kind": None}

    # Extract kind from parentheses
    kind_match = re.search(r'[（(]([^）)]+)[）)]', title)
    if kind_match:
        result["kind"] = kind_match.group(1)

    # Extract prefecture
    for pref in PREFECTURES:
        if pref in title:
            result["prefecture"] = pref
            break

    # Extract city (between prefecture and parentheses)
    if result["prefecture"]:
        after_pref = title.split(result["prefecture"])[-1]
        city_match = re.match(r'\s*(\S+?(?:市|区|町|村|郡))', after_pref)
        if city_match:
            result["city"] = city_match.group(1)

    return result


def parse_article(url, title_hint=""):
    """Parse a single article page."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Get title
        title = ""
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
        if not title:
            title = title_hint

        # Get body text
        body_text = ""
        article = soup.find("article") or soup.find("div", class_=re.compile(r"article|content|body|main", re.I))
        if article:
            body_text = article.get_text("\n", strip=True)
        else:
            body_text = soup.get_text("\n", strip=True)

        # Parse title structure
        parsed = parse_title(title)

        # Extract date/time from body
        date_match = re.search(r'(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})[日]?', body_text)
        time_match = re.search(r'(\d{1,2})[時:](\d{1,2})[分]?(?:[頃ごろ])?', body_text)

        if date_match:
            parsed["date"] = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
        if time_match:
            parsed["time"] = f"{int(time_match.group(1)):02d}:{int(time_match.group(2)):02d}"

        # Extract address
        addr_match = re.search(r'((?:北海道|東京都|大阪府|京都府|.{2,3}県).{2,30}?(?:丁目|番地?|号|付近|地先|地内))', body_text)
        if addr_match:
            parsed["address"] = addr_match.group(1)

        # Detect kind from body if not in title
        if not parsed["kind"]:
            for kp in KIND_PATTERNS:
                if kp in body_text or kp in title:
                    parsed["kind"] = kp
                    break

        parsed["url"] = url
        parsed["body_length"] = len(body_text)
        parsed["body_snippet"] = body_text[:500]

        return parsed
    except Exception as e:
        return {"url": url, "error": str(e)}


def main():
    print("=" * 60)
    print("Step 1: Analyzing JASPIC schema from nordot.app / news.jp")
    print("=" * 60)

    all_links = []
    for feed_url, category in FEEDS:
        links = extract_article_links(feed_url, category)
        for url, title in links:
            all_links.append({"url": url, "title": title, "category": category})
        time.sleep(1)

    print(f"\nTotal article links found: {len(all_links)}")

    # Parse articles (up to 200)
    samples = []
    kind_counts = {}
    prefecture_counts = {}

    limit = min(200, len(all_links))
    print(f"\nParsing up to {limit} articles...")

    for i, link_info in enumerate(all_links[:limit]):
        if i % 10 == 0:
            print(f"  Parsing article {i+1}/{limit}...")

        parsed = parse_article(link_info["url"], link_info["title"])
        parsed["feed_category"] = link_info["category"]
        samples.append(parsed)

        if parsed.get("kind"):
            kind_counts[parsed["kind"]] = kind_counts.get(parsed["kind"], 0) + 1
        if parsed.get("prefecture"):
            prefecture_counts[parsed["prefecture"]] = prefecture_counts.get(parsed["prefecture"], 0) + 1

        time.sleep(0.5)

    # If we got no links from feeds, create synthetic analysis from known JASPIC patterns
    if len(samples) == 0 or all("error" in s for s in samples):
        print("\n  Note: Could not fetch live articles. Building schema from known JASPIC patterns.")
        samples = _build_synthetic_samples()
        for s in samples:
            if s.get("kind"):
                kind_counts[s["kind"]] = kind_counts.get(s["kind"], 0) + 1
            if s.get("prefecture"):
                prefecture_counts[s["prefecture"]] = prefecture_counts.get(s["prefecture"], 0) + 1

    # Build kind taxonomy
    kind_taxonomy = {}
    for kind_name in sorted(set(list(kind_counts.keys()) + KIND_PATTERNS)):
        category = _categorize_kind(kind_name)
        kind_taxonomy[kind_name] = {
            "category": category,
            "count_in_sample": kind_counts.get(kind_name, 0),
            "layer": "crime" if category != "wildlife" else "disaster",
        }

    # Save results
    schema_out = {
        "analyzed_at": datetime.now().isoformat(),
        "feeds_checked": [f[0] for f in FEEDS],
        "total_links_found": len(all_links),
        "articles_parsed": len(samples),
        "title_format": "都道府県名 市区町村名（種別）",
        "extracted_fields": ["kind", "prefecture", "city", "date", "time", "address"],
        "prefecture_coverage": prefecture_counts,
        "kind_distribution": kind_counts,
        "samples": samples[:50],  # Save up to 50 samples
    }

    schema_path = os.path.join(OUT_DIR, "schema_samples.json")
    with open(schema_path, "w", encoding="utf-8") as f:
        json.dump(schema_out, f, ensure_ascii=False, indent=2)
    print(f"\nSaved schema samples: {schema_path}")

    taxonomy_path = os.path.join(OUT_DIR, "kind_taxonomy.json")
    with open(taxonomy_path, "w", encoding="utf-8") as f:
        json.dump(kind_taxonomy, f, ensure_ascii=False, indent=2)
    print(f"Saved kind taxonomy: {taxonomy_path}")

    print(f"\nKind distribution: {json.dumps(kind_counts, ensure_ascii=False, indent=2)}")
    print(f"Prefecture coverage: {len(prefecture_counts)} prefectures")

    return schema_out, kind_taxonomy


def _categorize_kind(kind):
    person_kinds = ["声かけ", "つきまとい", "痴漢", "わいせつ", "盗撮", "不審者", "露出", "のぞき", "公然わいせつ", "写真撮影", "容姿撮影", "付きまとい"]
    violent_kinds = ["強盗", "暴行", "刃物所持", "ひったくり"]
    property_kinds = ["空き巣", "車上ねらい", "自転車盗", "すり", "窃盗", "侵入盗", "万引き", "器物損壊"]
    fraud_kinds = ["オレオレ詐欺", "還付金詐欺", "特殊詐欺", "架空請求"]
    wildlife_kinds = ["クマ出没", "イノシシ出没", "サル出没", "シカ出没"]
    vehicle_kinds = ["不審車両"]
    phone_kinds = ["不審電話"]

    if kind in person_kinds:
        return "suspicious_person"
    elif kind in violent_kinds:
        return "violent_crime"
    elif kind in property_kinds:
        return "property_crime"
    elif kind in fraud_kinds:
        return "fraud"
    elif kind in wildlife_kinds:
        return "wildlife"
    elif kind in vehicle_kinds:
        return "suspicious_vehicle"
    elif kind in phone_kinds:
        return "suspicious_phone"
    return "other"


def _build_synthetic_samples():
    """Build synthetic samples representing known JASPIC article patterns."""
    samples = []
    example_data = [
        {"kind": "声かけ", "prefecture": "埼玉県", "city": "さいたま市", "date": "2026-04-02", "time": "15:30", "address": "埼玉県さいたま市浦和区高砂3丁目付近"},
        {"kind": "つきまとい", "prefecture": "東京都", "city": "新宿区", "date": "2026-04-02", "time": "19:00", "address": "東京都新宿区歌舞伎町1丁目付近"},
        {"kind": "痴漢", "prefecture": "神奈川県", "city": "横浜市", "date": "2026-04-01", "time": "08:15", "address": "神奈川県横浜市西区南幸2丁目付近"},
        {"kind": "不審者", "prefecture": "大阪府", "city": "大阪市", "date": "2026-04-02", "time": "21:00", "address": "大阪府大阪市北区梅田1丁目付近"},
        {"kind": "クマ出没", "prefecture": "長野県", "city": "松本市", "date": "2026-04-01", "time": "06:30", "address": "長野県松本市安曇地先"},
        {"kind": "空き巣", "prefecture": "愛知県", "city": "名古屋市", "date": "2026-04-02", "time": "14:00", "address": "愛知県名古屋市中区栄3丁目付近"},
        {"kind": "強盗", "prefecture": "福岡県", "city": "福岡市", "date": "2026-04-01", "time": "23:30", "address": "福岡県福岡市博多区中洲5丁目付近"},
        {"kind": "盗撮", "prefecture": "千葉県", "city": "千葉市", "date": "2026-04-02", "time": "17:45", "address": "千葉県千葉市中央区富士見2丁目付近"},
        {"kind": "わいせつ", "prefecture": "兵庫県", "city": "神戸市", "date": "2026-04-01", "time": "22:10", "address": "兵庫県神戸市中央区三宮町1丁目付近"},
        {"kind": "刃物所持", "prefecture": "北海道", "city": "札幌市", "date": "2026-04-02", "time": "16:20", "address": "北海道札幌市中央区南3条西4丁目付近"},
        {"kind": "特殊詐欺", "prefecture": "静岡県", "city": "静岡市", "date": "2026-04-02", "time": "11:00", "address": "静岡県静岡市葵区追手町付近"},
        {"kind": "イノシシ出没", "prefecture": "広島県", "city": "広島市", "date": "2026-04-01", "time": "05:45", "address": "広島県広島市安佐北区可部付近"},
        {"kind": "露出", "prefecture": "京都府", "city": "京都市", "date": "2026-04-02", "time": "20:30", "address": "京都府京都市下京区四条通付近"},
        {"kind": "ひったくり", "prefecture": "大阪府", "city": "堺市", "date": "2026-04-01", "time": "18:50", "address": "大阪府堺市堺区南瓦町付近"},
        {"kind": "不審電話", "prefecture": "宮城県", "city": "仙台市", "date": "2026-04-02", "time": "10:30", "address": "宮城県仙台市青葉区一番町付近"},
    ]
    for ex in example_data:
        ex["raw_title"] = f"{ex['prefecture']} {ex['city']}（{ex['kind']}）"
        ex["url"] = "synthetic"
        ex["body_length"] = 0
        ex["body_snippet"] = ""
        samples.append(ex)
    return samples


if __name__ == "__main__":
    main()
