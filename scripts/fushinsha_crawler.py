#!/usr/bin/env python3
"""
Fushinsha (不審者) Information Crawler
Beats JASPIC by adding: severity scores, geometry, risk_score, multi-layer integration.

Usage:
  python3 fushinsha_crawler.py              # Run one crawl cycle
  python3 fushinsha_crawler.py --loop       # Run continuously (30-min interval)
  python3 fushinsha_crawler.py --loop --interval 60  # Custom interval in minutes
"""

import json
import re
import os
import sys
import time
import hashlib
import argparse
from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ─── Config ───────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "realtime", "fushinsha_live")
HASH_FILE = os.path.join(DATA_DIR, "seen_hashes.json")
os.makedirs(DATA_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en;q=0.5",
}

# ─── Kind → Subtype mapping with severity ────────────────────────────────────
KIND_TO_SUBTYPE = {
    "声かけ":      {"subtype": "suspicious_person_approach",    "severity": 2, "layer": "crime"},
    "つきまとい":  {"subtype": "suspicious_person_stalking",    "severity": 3, "layer": "crime"},
    "付きまとい":  {"subtype": "suspicious_person_stalking",    "severity": 3, "layer": "crime"},
    "痴漢":        {"subtype": "sexual_crime_groping",          "severity": 4, "layer": "crime"},
    "チカン":      {"subtype": "sexual_crime_groping",          "severity": 4, "layer": "crime"},
    "わいせつ":    {"subtype": "sexual_crime",                  "severity": 4, "layer": "crime"},
    "公然わいせつ":{"subtype": "sexual_crime_exposure",         "severity": 3, "layer": "crime"},
    "盗撮":        {"subtype": "sexual_crime_voyeurism",        "severity": 3, "layer": "crime"},
    "強盗":        {"subtype": "robbery",                       "severity": 5, "layer": "crime"},
    "暴行":        {"subtype": "assault",                       "severity": 4, "layer": "crime"},
    "暴言":        {"subtype": "verbal_assault",                "severity": 2, "layer": "crime"},
    "刃物所持":    {"subtype": "weapons",                       "severity": 4, "layer": "crime"},
    "不審者":      {"subtype": "suspicious_person",             "severity": 2, "layer": "crime"},
    "露出":        {"subtype": "sexual_crime_exposure",         "severity": 3, "layer": "crime"},
    "のぞき":      {"subtype": "sexual_crime_peeping",          "severity": 3, "layer": "crime"},
    "ひったくり":  {"subtype": "purse_snatching",               "severity": 4, "layer": "crime"},
    "すり":        {"subtype": "pickpocketing",                 "severity": 3, "layer": "crime"},
    "写真撮影":    {"subtype": "suspicious_photography",        "severity": 2, "layer": "crime"},
    "容姿撮影":    {"subtype": "suspicious_photography",        "severity": 2, "layer": "crime"},
    "不審車両":    {"subtype": "suspicious_vehicle",            "severity": 2, "layer": "crime"},
    "不審電話":    {"subtype": "suspicious_phone_call",         "severity": 2, "layer": "crime"},
    # Property crimes
    "空き巣":      {"subtype": "burglary",                      "severity": 3, "layer": "crime"},
    "車上ねらい":  {"subtype": "vehicle_breakin",               "severity": 3, "layer": "crime"},
    "車上荒らし":  {"subtype": "vehicle_breakin",               "severity": 3, "layer": "crime"},
    "自転車盗":    {"subtype": "bicycle_theft",                 "severity": 2, "layer": "crime"},
    "窃盗":        {"subtype": "theft",                         "severity": 3, "layer": "crime"},
    "侵入盗":      {"subtype": "burglary",                      "severity": 3, "layer": "crime"},
    "万引き":      {"subtype": "shoplifting",                   "severity": 2, "layer": "crime"},
    "器物損壊":    {"subtype": "vandalism",                     "severity": 2, "layer": "crime"},
    # Fraud
    "オレオレ詐欺":{"subtype": "fraud_impersonation",           "severity": 3, "layer": "crime"},
    "還付金詐欺":  {"subtype": "fraud_refund",                  "severity": 3, "layer": "crime"},
    "特殊詐欺":    {"subtype": "fraud_special",                 "severity": 3, "layer": "crime"},
    "架空請求":    {"subtype": "fraud_billing",                 "severity": 3, "layer": "crime"},
    # Wildlife (disaster layer)
    "クマ出没":    {"subtype": "wildlife_bear",                 "severity": 4, "layer": "disaster"},
    "イノシシ出没":{"subtype": "wildlife_boar",                 "severity": 3, "layer": "disaster"},
    "サル出没":    {"subtype": "wildlife_monkey",               "severity": 2, "layer": "disaster"},
    "シカ出没":    {"subtype": "wildlife_deer",                 "severity": 2, "layer": "disaster"},
}

PREF_ABBREV_MAP = {
    "北海道": "北海道", "青森": "青森県", "岩手": "岩手県", "宮城": "宮城県",
    "秋田": "秋田県", "山形": "山形県", "福島": "福島県",
    "茨城": "茨城県", "栃木": "栃木県", "群馬": "群馬県", "埼玉": "埼玉県",
    "千葉": "千葉県", "東京": "東京都", "神奈川": "神奈川県",
    "新潟": "新潟県", "富山": "富山県", "石川": "石川県", "福井": "福井県",
    "山梨": "山梨県", "長野": "長野県",
    "岐阜": "岐阜県", "静岡": "静岡県", "愛知": "愛知県", "三重": "三重県",
    "滋賀": "滋賀県", "京都": "京都府", "大阪": "大阪府", "兵庫": "兵庫県",
    "奈良": "奈良県", "和歌山": "和歌山県",
    "鳥取": "鳥取県", "島根": "島根県", "岡山": "岡山県", "広島": "広島県", "山口": "山口県",
    "徳島": "徳島県", "香川": "香川県", "愛媛": "愛媛県", "高知": "高知県",
    "福岡": "福岡県", "佐賀": "佐賀県", "長崎": "長崎県", "熊本": "熊本県",
    "大分": "大分県", "宮崎": "宮崎県", "鹿児島": "鹿児島県", "沖縄": "沖縄県",
}

NORDOT_FEEDS = [
    ("https://news.jp/i/-/units/133089874031904245", "不審者情報"),
    ("https://news.jp/i/-/units/402299803402830945", "危険動物情報"),
    ("https://news.jp/i/-/units/468644598573220961", "財産ねらい情報"),
]

KIND_PATTERNS = sorted(KIND_TO_SUBTYPE.keys(), key=len, reverse=True)  # longest first


# ─── Deduplication ────────────────────────────────────────────────────────────
def load_seen_hashes():
    if os.path.exists(HASH_FILE):
        with open(HASH_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen_hashes(hashes):
    with open(HASH_FILE, "w") as f:
        json.dump(sorted(hashes), f)


def compute_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ─── Parsing ──────────────────────────────────────────────────────────────────
def parse_jaspic_title(title):
    """Parse JASPIC title: （都道府県略称）場所で種別　日付"""
    result = {"prefecture": None, "city": None, "kind": None, "resolved": False}

    # Prefecture from parentheses
    pref_match = re.search(r'[（(]([^）)]+)[）)]', title)
    if pref_match:
        abbrev = pref_match.group(1)
        result["prefecture"] = PREF_ABBREV_MAP.get(abbrev, abbrev if abbrev.endswith(("県", "都", "府", "道")) else None)

    # Kind from title text (longest match first)
    for kp in KIND_PATTERNS:
        if kp in title:
            result["kind"] = kp
            break

    # City
    after_paren = re.sub(r'^.*?[）)]', '', title).strip()
    city_match = re.match(r'(\S+?(?:市|区|町|村))', after_paren)
    if city_match:
        result["city"] = city_match.group(1)

    # Check if resolved
    if "解決" in title or "確保" in title:
        result["resolved"] = True

    return result


def parse_body_datetime(body):
    """Extract date and time from JASPIC body text."""
    result = {}
    fw_to_hw = str.maketrans('０１２３４５６７８９', '0123456789')
    normalized = body.translate(fw_to_hw)

    # Date
    date_match = re.search(r'(\d{1,2})月(\d{1,2})日', normalized)
    if date_match:
        month = int(date_match.group(1))
        day = int(date_match.group(2))
        now = datetime.now()
        year = now.year
        # If month is far in the future, assume last year
        if month > now.month + 1:
            year -= 1
        result["date"] = f"{year}-{month:02d}-{day:02d}"

    # Time: 午後５時３０分 format
    time_match = re.search(r'(午前|午後)(\d{1,2})時(\d{1,2})?分?', normalized)
    if time_match:
        hour = int(time_match.group(2))
        minute = int(time_match.group(3)) if time_match.group(3) else 0
        if time_match.group(1) == "午後" and hour < 12:
            hour += 12
        elif time_match.group(1) == "午前" and hour == 12:
            hour = 0
        result["time"] = f"{hour:02d}:{minute:02d}"

    if "time" not in result:
        t2 = re.search(r'(\d{1,2}):(\d{2})', normalized)
        if t2:
            result["time"] = f"{int(t2.group(1)):02d}:{t2.group(2)}"

    return result


def parse_body_details(body):
    """Extract perpetrator info, situation, facilities from body."""
    result = {}

    perp_match = re.search(r'実行者の特徴[：:](.+?)(?:[）)]|\n)', body)
    if perp_match:
        result["perpetrator"] = perp_match.group(1).strip()

    situation = []
    in_situation = False
    in_facilities = False
    facilities = []

    for line in body.split('\n'):
        line = line.strip()
        if '発生時の状況' in line:
            in_situation = True
            in_facilities = False
            continue
        if '現場付近の施設' in line:
            in_facilities = True
            in_situation = False
            continue
        if '■' in line:
            in_situation = False
            in_facilities = False
            continue
        if line.startswith('・'):
            content = line[1:].strip()
            if in_situation:
                situation.append(content)
            elif in_facilities:
                facilities.append(content)

    if situation:
        result["situation"] = situation
    if facilities:
        result["nearby_facilities"] = facilities

    return result


def build_event(title, body, url, feed_category):
    """Build a structured event from a JASPIC article."""
    title_parsed = parse_jaspic_title(title)
    dt_parsed = parse_body_datetime(body)
    details = parse_body_details(body)

    kind = title_parsed.get("kind")
    mapping = KIND_TO_SUBTYPE.get(kind, {"subtype": "unknown", "severity": 2, "layer": "crime"})

    # Build event ID
    event_hash = compute_hash(f"{title}{body[:200]}")

    # Construct datetime
    event_date = dt_parsed.get("date", datetime.now().strftime("%Y-%m-%d"))
    event_time = dt_parsed.get("time")
    if event_date and event_time:
        event_datetime = f"{event_date}T{event_time}:00+09:00"
    elif event_date:
        event_datetime = f"{event_date}T00:00:00+09:00"
    else:
        event_datetime = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00")

    # Risk score: severity weighted by recency
    severity = mapping["severity"]
    try:
        days_old = (datetime.now() - datetime.strptime(event_date, "%Y-%m-%d")).days
    except (ValueError, TypeError):
        days_old = 0
    recency_factor = max(0.3, 1.0 - (days_old * 0.05))
    risk_score = round(severity * recency_factor * 20, 1)  # 0-100 scale

    event = {
        "event_id": f"fushinsha_{event_hash}",
        "hash": event_hash,
        "source": "jaspic_nordot",
        "source_url": url,
        "feed_category": feed_category,
        "crawled_at": datetime.now().isoformat(),

        # Schema fields matching risk_space schema
        "layer": mapping["layer"],
        "type": "crime" if mapping["layer"] == "crime" else "wildlife",
        "subtype": mapping["subtype"],
        "kind_original": kind,
        "severity": severity,
        "risk_score": risk_score,
        "resolved": title_parsed.get("resolved", False),

        # Location
        "prefecture": title_parsed.get("prefecture"),
        "city": title_parsed.get("city"),
        "address": None,  # Could be extracted from body

        # Time
        "event_datetime": event_datetime,
        "event_date": event_date,
        "event_time": event_time,

        # Details
        "title": title,
        "description": body[:500] if body else None,
        **details,
    }

    # Extract address from body
    addr_match = re.search(
        r'((?:北海道|東京都|大阪府|京都府|.{2,3}県)?.{2,30}?(?:丁目|番地?|号|付近|地先|地内))',
        body
    )
    if addr_match:
        event["address"] = addr_match.group(1)

    return event


# ─── Crawl sources ────────────────────────────────────────────────────────────
def crawl_nordot_feeds():
    """Crawl JASPIC articles from nordot/news.jp feeds."""
    articles = []

    for feed_url, category in NORDOT_FEEDS:
        print(f"  Crawling feed: {category}")
        try:
            resp = requests.get(feed_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if re.search(r'/\d{10,}', href):
                    full_url = urljoin(feed_url, href)
                    title_text = a.get_text(strip=True)
                    if full_url not in [l[0] for l in links] and title_text:
                        links.append((full_url, title_text))

            print(f"    Found {len(links)} article links")

            for url, link_title in links:
                try:
                    art_resp = requests.get(url, headers=HEADERS, timeout=15)
                    art_resp.raise_for_status()
                    art_soup = BeautifulSoup(art_resp.text, "html.parser")

                    title = ""
                    h1 = art_soup.find("h1")
                    if h1:
                        title = h1.get_text(strip=True)
                    if not title:
                        title_tag = art_soup.find("title")
                        if title_tag:
                            title = title_tag.get_text(strip=True)
                    if not title:
                        title = link_title

                    body = ""
                    article_el = art_soup.find("article") or art_soup.find("div", class_=re.compile(r"article|content|body", re.I))
                    if article_el:
                        body = article_el.get_text("\n", strip=True)
                    else:
                        body = art_soup.get_text("\n", strip=True)

                    articles.append({
                        "url": url,
                        "title": title,
                        "body": body,
                        "category": category,
                    })
                except Exception as e:
                    print(f"    Error fetching {url}: {e}")

                time.sleep(0.5)

        except Exception as e:
            print(f"    Error fetching feed {feed_url}: {e}")

        time.sleep(1)

    return articles


def crawl_gaccom_recent():
    """Crawl recent safety incidents from gaccom.jp safety pages."""
    articles = []
    # Top-level safety page
    gaccom_urls = [
        "https://www.gaccom.jp/safety/",
        "https://www.gaccom.jp/safety/result-0",
    ]

    for gurl in gaccom_urls:
        print(f"  Crawling gaccom: {gurl}")
        try:
            resp = requests.get(gurl, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "/safety/detail-" in href or "/safety/incident-" in href:
                        full_url = urljoin(gurl, href)
                        title_text = a.get_text(strip=True)
                        if title_text and len(title_text) > 5:
                            articles.append({
                                "url": full_url,
                                "title": title_text,
                                "body": title_text,
                                "category": "gaccom_safety",
                            })
                print(f"    Found {len(articles)} items from gaccom")
        except Exception as e:
            print(f"    Gaccom error: {e}")
        time.sleep(1)

    return articles


# ─── Main crawl cycle ─────────────────────────────────────────────────────────
def run_crawl_cycle():
    """Execute one complete crawl cycle."""
    print(f"\n{'='*60}")
    print(f"Crawl cycle started at {datetime.now().isoformat()}")
    print(f"{'='*60}")

    seen_hashes = load_seen_hashes()
    initial_count = len(seen_hashes)
    print(f"Loaded {initial_count} seen hashes")

    # Crawl all sources
    all_articles = []

    print("\n[1/2] Crawling JASPIC / nordot feeds...")
    nordot_articles = crawl_nordot_feeds()
    all_articles.extend(nordot_articles)

    print(f"\n[2/2] Crawling gaccom safety...")
    gaccom_articles = crawl_gaccom_recent()
    all_articles.extend(gaccom_articles)

    print(f"\nTotal raw articles: {len(all_articles)}")

    # Build events, deduplicate
    new_events = []
    skipped = 0

    for article in all_articles:
        content_hash = compute_hash(f"{article['title']}{article['body'][:200]}")

        if content_hash in seen_hashes:
            skipped += 1
            continue

        event = build_event(
            title=article["title"],
            body=article["body"],
            url=article["url"],
            feed_category=article["category"],
        )

        seen_hashes.add(content_hash)
        new_events.append(event)

    print(f"New events: {new_events.__len__()}, Skipped (duplicates): {skipped}")

    # Save events
    if new_events:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        events_file = os.path.join(DATA_DIR, f"events_{timestamp}.json")

        output = {
            "crawled_at": datetime.now().isoformat(),
            "cycle_stats": {
                "sources_crawled": ["jaspic_nordot", "gaccom"],
                "raw_articles": len(all_articles),
                "new_events": len(new_events),
                "duplicates_skipped": skipped,
                "total_seen": len(seen_hashes),
            },
            "events": new_events,
        }

        with open(events_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"Saved events: {events_file}")

        # Print summary by type
        by_subtype = {}
        by_pref = {}
        by_severity = {}
        for ev in new_events:
            st = ev.get("subtype", "unknown")
            by_subtype[st] = by_subtype.get(st, 0) + 1
            pref = ev.get("prefecture", "unknown")
            by_pref[pref] = by_pref.get(pref, 0) + 1
            sev = ev.get("severity", 0)
            by_severity[sev] = by_severity.get(sev, 0) + 1

        print(f"\nBy subtype: {json.dumps(by_subtype, ensure_ascii=False)}")
        print(f"By prefecture: {json.dumps(by_pref, ensure_ascii=False)}")
        print(f"By severity: {json.dumps(by_severity, ensure_ascii=False)}")
    else:
        print("No new events this cycle.")

    # Save seen hashes
    save_seen_hashes(seen_hashes)
    print(f"Updated seen_hashes: {initial_count} -> {len(seen_hashes)}")

    return new_events


def main():
    parser = argparse.ArgumentParser(description="Fushinsha (不審者) Information Crawler")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=30, help="Interval in minutes (default: 30)")
    args = parser.parse_args()

    if args.loop:
        print(f"Starting continuous crawl (interval: {args.interval} min)")
        print("Press Ctrl+C to stop.")
        while True:
            try:
                run_crawl_cycle()
                print(f"\nSleeping {args.interval} minutes until next cycle...")
                time.sleep(args.interval * 60)
            except KeyboardInterrupt:
                print("\nStopped by user.")
                break
            except Exception as e:
                print(f"\nError in crawl cycle: {e}")
                print(f"Retrying in {args.interval} minutes...")
                time.sleep(args.interval * 60)
    else:
        events = run_crawl_cycle()
        print(f"\nDone. {len(events)} new events collected.")
        return events


if __name__ == "__main__":
    main()
