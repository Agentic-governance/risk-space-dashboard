#!/usr/bin/env python3
"""
Task 1: Full suspicious person information crawl from all sources.
Parts A-D: Police HP crawl, nordot backfill, geocoding, save outputs.
"""

from __future__ import annotations

import json
import hashlib
import random
import re
import time
import urllib.parse
import urllib3
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Optional, Tuple

import requests
from bs4 import BeautifulSoup

# === Paths ===
BASE = Path(__file__).resolve().parent.parent
DATA_RT = BASE / "data" / "realtime"
SOURCE_MAP = DATA_RT / "source_map.json"
SEEN_HASHES = DATA_RT / "seen_hashes.json"
SEEN_HASHES_ALT = BASE / "docs" / "data" / "seen_hashes.json"
CITY_CENTROIDS = BASE / "data" / "crime" / "national" / "city_centroids.json"
CITY_CENTROIDS_ALT = BASE / "docs" / "data" / "city_centroids.json"
PREF_CENTROIDS = BASE / "data" / "crime" / "national" / "pref_centroids.json"
PREF_CENTROIDS_ALT = BASE / "docs" / "data" / "pref_centroids.json"
OUT_DIR = DATA_RT / "fushinsha_7days"
OUT_FILE = OUT_DIR / "week_events_geocoded.json"
DOCS_OUT = BASE / "docs" / "data" / "events_7days.json"

OUT_DIR.mkdir(parents=True, exist_ok=True)
DOCS_OUT.parent.mkdir(parents=True, exist_ok=True)

# === Constants ===
KEYWORDS = ["不審者", "声かけ", "つきまとい", "痴漢", "盗撮", "わいせつ", "露出",
            "ひったくり", "強盗", "暴行", "刃物", "クマ", "特殊詐欺"]

KEYWORD_TO_SUBTYPE = {
    "不審者": "suspicious_person", "声かけ": "solicitation", "つきまとい": "stalking",
    "痴漢": "groping", "盗撮": "voyeurism", "わいせつ": "indecent_act",
    "露出": "exposure", "ひったくり": "purse_snatching", "強盗": "robbery",
    "暴行": "assault", "刃物": "weapon", "クマ": "bear", "特殊詐欺": "fraud",
}

PREF_NAMES = [
    "", "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

TODAY = datetime.now()
WEEK_AGO = TODAY - timedelta(days=7)

# === Load reference data ===
print("Loading reference data...")
try:
    with open(SOURCE_MAP, "r") as f:
        source_map = json.load(f)
except FileNotFoundError:
    print(f"[FATAL] source_map not found: {SOURCE_MAP}")
    sys.exit(1)

if SEEN_HASHES.exists():
    with open(SEEN_HASHES, "r") as f:
        seen_hashes = set(json.load(f))
elif SEEN_HASHES_ALT.exists():
    with open(SEEN_HASHES_ALT, "r") as f:
        seen_hashes = set(json.load(f))
    print(f"  Loaded seen_hashes from fallback: {SEEN_HASHES_ALT}")
else:
    seen_hashes = set()

city_centroids = {}
for _path in [CITY_CENTROIDS, CITY_CENTROIDS_ALT]:
    if _path.exists():
        with open(_path, "r") as f:
            city_centroids = json.load(f)
        print(f"  Loaded city_centroids from: {_path}")
        break
else:
    print(f"[WARN] city_centroids not found in any location, using empty")

pref_centroids_list = []
for _path in [PREF_CENTROIDS, PREF_CENTROIDS_ALT]:
    if _path.exists():
        with open(_path, "r") as f:
            pref_centroids_list = json.load(f)
        print(f"  Loaded pref_centroids from: {_path}")
        break
else:
    print(f"[WARN] pref_centroids not found in any location, using empty")

# Build pref centroid lookup by name
pref_centroids = {}
for p in pref_centroids_list:
    pref_centroids[p["prefecture"]] = {"lat": p["lat"], "lon": p["lon"]}

print(f"  Loaded {len(city_centroids)} city centroids, {len(pref_centroids)} pref centroids")
print(f"  Existing seen_hashes: {len(seen_hashes)}")


def make_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def extract_date(text: str) -> str | None:
    """Try to extract a date from Japanese text."""
    # 令和X年Y月Z日
    m = re.search(r'令和(\d+)年(\d+)月(\d+)日', text)
    if m:
        year = 2018 + int(m.group(1))
        return f"{year}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 2026年4月1日 or 2026/4/1
    m = re.search(r'(\d{4})[年/](\d{1,2})[月/](\d{1,2})', text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 4月1日 (current year)
    m = re.search(r'(\d{1,2})月(\d{1,2})日', text)
    if m:
        return f"{TODAY.year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


def extract_address(text: str, pref_name: str) -> str | None:
    """Try to extract an address from Japanese text."""
    # Pattern: prefecture + city + detail
    patterns = [
        # Full address with prefecture
        r'(' + re.escape(pref_name) + r'[^\s、。，]{3,30})',
        # City/ward patterns
        r'(\S{1,5}(?:市|区|町|村)\S{0,20}(?:丁目|番地?|号)?)',
        # 〜付近, 〜において, 〜で
        r'(\S{2,15}(?:付近|において|路上))',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            addr = m.group(1)
            if len(addr) >= 4:
                return addr
    return None


def extract_time(text: str) -> str | None:
    """Extract time from text."""
    m = re.search(r'(\d{1,2})[時:](\d{2})', text)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    m = re.search(r'午([前後])(\d{1,2})時', text)
    if m:
        h = int(m.group(2))
        if m.group(1) == '後' and h < 12:
            h += 12
        return f"{h:02d}:00"
    return None


# Column header patterns that indicate an incident table
_TABLE_DATE_HDRS  = re.compile(r'日時?|発生日|年月日')
_TABLE_PLACE_HDRS = re.compile(r'場所|住所|発生場所|地区')
_TABLE_TYPE_HDRS  = re.compile(r'概要|種別|内容|事案')


def extract_structured_data(soup: BeautifulSoup, pref_name: str) -> list[dict]:
    """
    Extract events from structured content that keyword-context windows miss:
      1. RSS feeds declared in <link rel="alternate" type="application/rss+xml">
      2. HTML tables whose column headers look like incident lists
      3. Links to .csv / .pdf download files (noted for future processing)

    Returns a list of event dicts using the same schema as the keyword extraction.
    """
    events: list[dict] = []
    scraped_at = datetime.now().isoformat()

    # ------------------------------------------------------------------
    # 1. RSS feed detection
    # ------------------------------------------------------------------
    rss_links = soup.find_all(
        "link",
        rel=lambda r: isinstance(r, list) and "alternate" in r,
        type="application/rss+xml",
    )
    for rss_link in rss_links:
        rss_url = rss_link.get("href", "").strip()
        if not rss_url:
            continue
        try:
            time.sleep(1.0)
            rss_resp = session.get(rss_url, timeout=10, allow_redirects=True)
            rss_resp.encoding = rss_resp.apparent_encoding or "utf-8"
            rss_soup = BeautifulSoup(rss_resp.text, "xml")

            for item in rss_soup.find_all("item"):
                title_tag = item.find("title")
                desc_tag  = item.find("description")
                link_tag  = item.find("link")
                pub_tag   = item.find("pubDate")

                title = title_tag.get_text(strip=True) if title_tag else ""
                desc  = desc_tag.get_text(strip=True)  if desc_tag  else ""
                link  = link_tag.get_text(strip=True)  if link_tag  else rss_url
                combined = f"{title}\n{desc}"

                # Check relevance
                matched_kw = next(
                    (kw for kw in KEYWORDS if kw in combined), None
                )
                if matched_kw is None:
                    continue

                # Date: prefer pubDate, then extract from text
                date_str = None
                if pub_tag:
                    pub_text = pub_tag.get_text(strip=True)
                    # RFC-822 format: "Thu, 01 May 2026 12:00:00 +0900"
                    m_rfc = re.search(r'(\d{1,2})\s+(\w{3})\s+(\d{4})', pub_text)
                    MONTHS = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
                              "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
                    if m_rfc:
                        mon = MONTHS.get(m_rfc.group(2), 0)
                        if mon:
                            date_str = f"{m_rfc.group(3)}-{mon:02d}-{int(m_rfc.group(1)):02d}"
                if not date_str:
                    date_str = extract_date(combined)

                # Skip items older than 7 days
                if date_str:
                    try:
                        if datetime.strptime(date_str, "%Y-%m-%d") < WEEK_AGO:
                            continue
                    except ValueError:
                        pass

                h = make_hash(combined[:400])
                if h in seen_hashes:
                    continue

                events.append({
                    "source": f"rss_{pref_name}",
                    "source_url": link,
                    "prefecture": pref_name,
                    "prefecture_code": None,
                    "date": date_str,
                    "time": extract_time(combined),
                    "address_raw": extract_address(combined, pref_name),
                    "layer": "crime",
                    "subtype": KEYWORD_TO_SUBTYPE.get(matched_kw, "other"),
                    "keyword_matched": matched_kw,
                    "text_snippet": combined[:300],
                    "hash": h,
                    "scraped_at": scraped_at,
                    "lat": None,
                    "lon": None,
                    "geocode_method": None,
                    "extraction_method": "rss",
                })
                seen_hashes.add(h)

        except Exception as e:
            print(f"    [RSS] Error fetching {rss_url}: {e}")

    # ------------------------------------------------------------------
    # 2. HTML table extraction
    # ------------------------------------------------------------------
    for table in soup.find_all("table"):
        headers = []
        header_row = table.find("tr")
        if not header_row:
            continue
        for th in header_row.find_all(["th", "td"]):
            headers.append(th.get_text(strip=True))

        if not headers:
            continue

        # Detect which columns map to date / place / description
        date_col = place_col = desc_col = None
        for idx, h in enumerate(headers):
            if date_col  is None and _TABLE_DATE_HDRS.search(h):
                date_col = idx
            if place_col is None and _TABLE_PLACE_HDRS.search(h):
                place_col = idx
            if desc_col  is None and _TABLE_TYPE_HDRS.search(h):
                desc_col = idx

        # Need at least a date or description column that hints at incidents
        if date_col is None and desc_col is None:
            continue

        for row in table.find_all("tr")[1:]:  # skip header row
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if not cells:
                continue

            date_text  = cells[date_col]  if date_col  is not None and date_col  < len(cells) else ""
            place_text = cells[place_col] if place_col is not None and place_col < len(cells) else ""
            desc_text  = cells[desc_col]  if desc_col  is not None and desc_col  < len(cells) else ""
            row_text   = " ".join(cells)

            matched_kw = next(
                (kw for kw in KEYWORDS if kw in row_text), None
            )
            if matched_kw is None:
                continue

            date_str = extract_date(date_text) or extract_date(row_text)
            if date_str:
                try:
                    if datetime.strptime(date_str, "%Y-%m-%d") < WEEK_AGO:
                        continue
                except ValueError:
                    pass

            addr = place_text or extract_address(row_text, pref_name)
            h = make_hash(row_text[:300])
            if h in seen_hashes:
                continue

            events.append({
                "source": f"table_{pref_name}",
                "source_url": "",
                "prefecture": pref_name,
                "prefecture_code": None,
                "date": date_str,
                "time": extract_time(date_text + " " + row_text),
                "address_raw": addr if addr else None,
                "layer": "crime",
                "subtype": KEYWORD_TO_SUBTYPE.get(matched_kw, "other"),
                "keyword_matched": matched_kw,
                "text_snippet": row_text[:300],
                "hash": h,
                "scraped_at": scraped_at,
                "lat": None,
                "lon": None,
                "geocode_method": None,
                "extraction_method": "table",
            })
            seen_hashes.add(h)

    # ------------------------------------------------------------------
    # 3. CSV / PDF download link detection
    # ------------------------------------------------------------------
    _DOWNLOAD_PAT = re.compile(
        r'\.(csv|pdf)$|download|dl=|file=|attachment', re.IGNORECASE
    )
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if _DOWNLOAD_PAT.search(href):
            link_text = a_tag.get_text(strip=True)
            # Only note links that sound crime-related
            if any(kw in link_text or kw in href for kw in
                   ["不審者", "声かけ", "犯罪", "防犯", "事件", "安全"]):
                print(f"    [DOWNLOAD] {pref_name}: {href!r} ({link_text!r})")

    return events


session = requests.Session()
session.headers.update(HEADERS)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
session.verify = False

all_events = []
stats = {"police_pages_checked": 0, "police_events": 0,
         "nordot_articles": 0, "nordot_events": 0,
         "geocoded_gsi": 0, "geocoded_city": 0, "geocoded_pref": 0,
         "skipped_dup": 0, "errors": 0}
pref_counts = defaultdict(int)


# ================================================================
# PART A: 47 Prefecture Police HP Crawl
# ================================================================
print("\n" + "=" * 60)
print("PART A: Prefecture Police HP Crawl")
print("=" * 60)

prefectures = source_map["prefectures"]

for code in sorted(prefectures.keys()):
    # Skip non-prefecture keys
    if not code.isdigit():
        continue
    info = prefectures[code]
    pref_name = info.get("prefecture", "")
    if not pref_name:
        continue

    police_sources = [s for s in info.get("sources", []) if s.get("type") == "police" and s.get("reachable")]
    if not police_sources:
        print(f"  [{code}] {pref_name}: No reachable police site, skipping")
        continue

    base_url = police_sources[0]["url"]
    print(f"  [{code}] {pref_name}: {base_url}")

    try:
        resp = session.get(base_url, timeout=10, allow_redirects=True)
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        # Find links that might contain suspicious person info
        candidate_links = []
        for a_tag in soup.find_all("a", href=True):
            link_text = a_tag.get_text(strip=True)
            href = a_tag["href"]
            if any(kw in link_text or kw in href for kw in ["不審者", "声かけ", "安全", "犯罪", "事件",
                                                              "安心", "防犯", "情報", "お知らせ",
                                                              "子ども", "女性", "メール"]):
                full_url = urllib.parse.urljoin(base_url, href)
                if full_url.startswith("http"):
                    candidate_links.append((full_url, link_text))

        # Deduplicate and limit
        seen_urls = set()
        unique_links = []
        for url, text in candidate_links:
            if url not in seen_urls:
                seen_urls.add(url)
                unique_links.append((url, text))
        unique_links = unique_links[:5]  # Max 5 sub-pages per prefecture

        # Also check main page text
        pages_to_check = [(base_url, soup)]

        for link_url, link_text in unique_links:
            time.sleep(1.5)
            try:
                r2 = session.get(link_url, timeout=10, allow_redirects=True)
                r2.encoding = r2.apparent_encoding or "utf-8"
                pages_to_check.append((link_url, BeautifulSoup(r2.text, "html.parser")))
                stats["police_pages_checked"] += 1
            except Exception as e:
                print(f"    Sub-page error: {link_url} -> {e}")
                stats["errors"] += 1

        # Extract events from all pages
        for page_url, page_soup in pages_to_check:
            page_text = page_soup.get_text(separator="\n")

            # --- Method 1: keyword context windows (original approach) ---
            for keyword in KEYWORDS:
                if keyword not in page_text:
                    continue

                # Find all occurrences and extract surrounding context
                for m in re.finditer(re.escape(keyword), page_text):
                    start = max(0, m.start() - 200)
                    end = min(len(page_text), m.end() + 200)
                    context = page_text[start:end].strip()

                    h = make_hash(context)
                    if h in seen_hashes:
                        stats["skipped_dup"] += 1
                        continue

                    date_str = extract_date(context)
                    if date_str:
                        try:
                            evt_date = datetime.strptime(date_str, "%Y-%m-%d")
                            if evt_date < WEEK_AGO:
                                continue
                        except ValueError:
                            pass

                    addr = extract_address(context, pref_name)
                    evt_time = extract_time(context)

                    event = {
                        "source": f"police_{code}",
                        "source_url": page_url,
                        "prefecture": pref_name,
                        "prefecture_code": f"{int(code):02d}",
                        "date": date_str,
                        "time": evt_time,
                        "address_raw": addr,
                        "layer": "crime",
                        "subtype": KEYWORD_TO_SUBTYPE.get(keyword, "other"),
                        "keyword_matched": keyword,
                        "text_snippet": context[:300],
                        "hash": h,
                        "scraped_at": datetime.now().isoformat(),
                        "lat": None,
                        "lon": None,
                        "geocode_method": None,
                        "extraction_method": "keyword",
                    }
                    all_events.append(event)
                    seen_hashes.add(h)
                    # Periodic flush of seen_hashes
                    if len(seen_hashes) % 100 == 0:
                        with open(SEEN_HASHES, "w", encoding="utf-8") as _f:
                            json.dump(sorted(list(seen_hashes)), _f)
                    stats["police_events"] += 1
                    pref_counts[pref_name] += 1

            # --- Method 2: structured data (RSS / tables / download links) ---
            structured_events = extract_structured_data(page_soup, pref_name)
            for ev in structured_events:
                # Back-fill fields that extract_structured_data leaves blank
                if not ev.get("source_url"):
                    ev["source_url"] = page_url
                if not ev.get("prefecture_code"):
                    ev["prefecture_code"] = f"{int(code):02d}"
                all_events.append(ev)
                stats["police_events"] += 1
                pref_counts[pref_name] += 1
                if len(seen_hashes) % 100 == 0:
                    with open(SEEN_HASHES, "w", encoding="utf-8") as _f:
                        json.dump(sorted(list(seen_hashes)), _f)

    except Exception as e:
        print(f"    ERROR: {e}")
        stats["errors"] += 1

    time.sleep(2.0)

print(f"\n  Part A complete: {stats['police_events']} events from {stats['police_pages_checked']} pages")


# ================================================================
# PART B: nordot.app / news.jp Backfill (past 7 days)
# ================================================================
print("\n" + "=" * 60)
print("PART B: nordot.app / news.jp Backfill")
print("=" * 60)

NORDOT_UNITS = {
    "fushinsha": "https://news.jp/i/-/units/133089874031904245",
    "kiken_doubutsu": "https://news.jp/i/-/units/402299803402830945",
}

# nordot/news.jp uses dynamic loading - try API patterns
# The units page lists articles. We'll try multiple page patterns.

def crawl_nordot_unit(unit_name: str, unit_url: str, max_pages: int = 10, max_articles: int = 150):
    """Crawl a nordot/news.jp unit for articles."""
    articles = []
    article_urls = set()

    for page_num in range(1, max_pages + 1):
        if len(article_urls) >= max_articles:
            break

        # Try page parameter patterns
        if page_num == 1:
            url = unit_url
        else:
            url = f"{unit_url}?page={page_num}"

        try:
            time.sleep(1.5)
            resp = session.get(url, timeout=15, allow_redirects=True)
            resp.encoding = "utf-8"

            if resp.status_code != 200:
                print(f"    Page {page_num}: HTTP {resp.status_code}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")

            # Find article links
            found_on_page = 0
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                # nordot article URLs typically contain numeric IDs
                full_url = urllib.parse.urljoin(url, href)
                if re.search(r'/i/\d{10,}', full_url) and full_url not in article_urls:
                    article_urls.add(full_url)
                    articles.append({"url": full_url, "link_text": a_tag.get_text(strip=True)})
                    found_on_page += 1

            print(f"    Page {page_num}: found {found_on_page} article links (total: {len(article_urls)})")

            if found_on_page == 0:
                break

        except Exception as e:
            print(f"    Page {page_num} error: {e}")
            break

    return articles


for unit_name, unit_url in NORDOT_UNITS.items():
    print(f"\n  Crawling unit: {unit_name}")
    print(f"  URL: {unit_url}")

    articles = crawl_nordot_unit(unit_name, unit_url)
    print(f"  Found {len(articles)} article links")

    for i, article in enumerate(articles[:150]):
        if stats["nordot_articles"] >= 300:
            break

        time.sleep(1.5)
        try:
            resp = session.get(article["url"], timeout=15, allow_redirects=True)
            resp.encoding = "utf-8"
            stats["nordot_articles"] += 1

            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            title = (soup.title.string or "").strip() if soup.title else article.get("link_text", "")

            # Get article body
            body_elem = soup.find("article") or soup.find("div", class_=re.compile(r"article|body|content"))
            body_text = body_elem.get_text(separator="\n") if body_elem else soup.get_text(separator="\n")

            full_text = title + "\n" + body_text
            h = make_hash(full_text[:500])

            if h in seen_hashes:
                stats["skipped_dup"] += 1
                continue

            # Parse title format: "（県名）市区町村で種別　月日"
            pref_match = re.search(r'[（(]([^）)]+)[）)]', title)
            detected_pref = pref_match.group(1) if pref_match else None

            # Also try to detect prefecture from body
            if not detected_pref:
                for pn in PREF_NAMES[1:]:
                    if pn in full_text[:200]:
                        detected_pref = pn
                        break

            date_str = extract_date(full_text)
            addr = None
            if detected_pref:
                addr = extract_address(full_text, detected_pref)

            # Determine subtype
            subtype = "other"
            matched_kw = None
            for kw in KEYWORDS:
                if kw in full_text:
                    subtype = KEYWORD_TO_SUBTYPE.get(kw, "other")
                    matched_kw = kw
                    break

            if unit_name == "kiken_doubutsu":
                subtype = "dangerous_animal"
                if "クマ" in full_text:
                    subtype = "bear"
                    matched_kw = "クマ"
                elif "サル" in full_text:
                    subtype = "monkey"
                elif "イノシシ" in full_text:
                    subtype = "boar"

            pref_code = None
            if detected_pref:
                for idx, pn in enumerate(PREF_NAMES):
                    if pn == detected_pref:
                        pref_code = f"{idx:02d}"
                        break

            event = {
                "source": f"nordot_{unit_name}",
                "source_url": article["url"],
                "prefecture": detected_pref,
                "prefecture_code": pref_code,
                "date": date_str,
                "time": extract_time(full_text),
                "address_raw": addr,
                "layer": "crime" if unit_name == "fushinsha" else "wildlife",
                "subtype": subtype,
                "keyword_matched": matched_kw,
                "text_snippet": (title + " " + body_text[:200]).strip()[:300],
                "hash": h,
                "scraped_at": datetime.now().isoformat(),
                "lat": None,
                "lon": None,
                "geocode_method": None,
            }
            all_events.append(event)
            seen_hashes.add(h)
            # Periodic flush of seen_hashes
            if len(seen_hashes) % 100 == 0:
                with open(SEEN_HASHES, "w", encoding="utf-8") as _f:
                    json.dump(sorted(list(seen_hashes)), _f)
            stats["nordot_events"] += 1
            if detected_pref:
                pref_counts[detected_pref] += 1

            if (i + 1) % 20 == 0:
                print(f"    Processed {i + 1}/{len(articles)} articles...")

        except Exception as e:
            print(f"    Article error: {article.get('url', '?')} -> {e}")
            stats["errors"] += 1
            continue

print(f"\n  Part B complete: {stats['nordot_events']} events from {stats['nordot_articles']} articles")


# ================================================================
# PART C: Geocode All Events
# ================================================================
print("\n" + "=" * 60)
print("PART C: Geocoding Events")
print("=" * 60)

GSI_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch"
geocode_cache = {}

def geocode_gsi(address: str) -> tuple | None:
    """Geocode via GSI API. Returns (lat, lon) or None."""
    if address in geocode_cache:
        return geocode_cache[address]

    try:
        time.sleep(random.uniform(0.2, 0.5))
        resp = session.get(GSI_URL, params={"q": address}, timeout=10)
        if resp.status_code == 200:
            results = resp.json()
            if results and len(results) > 0:
                coords = results[0].get("geometry", {}).get("coordinates", [])
                if len(coords) == 2:
                    # GSI returns [lon, lat]
                    result = (coords[1], coords[0])
                    geocode_cache[address] = result
                    return result
    except Exception:
        pass

    geocode_cache[address] = None
    return None


def find_city_centroid(address: str, pref_name: str) -> tuple | None:
    """Look up city centroid from address."""
    if not address or not pref_name:
        return None

    # Try to extract city name
    city_match = re.search(r'(\S{1,5}(?:市|区|町|村))', address)
    if city_match:
        city = city_match.group(1)
        # Try exact key: "県名_市名"
        key = f"{pref_name}_{city}"
        if key in city_centroids:
            c = city_centroids[key]
            return (c["lat"], c["lon"])

        # Try partial match
        for k, v in city_centroids.items():
            if k.startswith(pref_name + "_") and city in k:
                return (v["lat"], v["lon"])

    return None


def find_pref_centroid(pref_name: str) -> tuple | None:
    """Look up prefecture centroid."""
    if pref_name and pref_name in pref_centroids:
        c = pref_centroids[pref_name]
        return (c["lat"], c["lon"])
    return None


total_to_geocode = len(all_events)
print(f"  Total events to geocode: {total_to_geocode}")

for i, event in enumerate(all_events):
    if event.get("lat") is not None and event.get("lon") is not None:
        continue

    pref_name = event.get("prefecture", "")
    addr = event.get("address_raw", "")

    # Try GSI geocoding
    if addr:
        full_addr = addr
        if pref_name and not addr.startswith(pref_name):
            full_addr = pref_name + addr

        result = geocode_gsi(full_addr)
        if result:
            event["lat"], event["lon"] = result
            event["geocode_method"] = "gsi"
            stats["geocoded_gsi"] += 1
            continue

        # Try shorter address
        result = geocode_gsi(addr)
        if result:
            event["lat"], event["lon"] = result
            event["geocode_method"] = "gsi"
            stats["geocoded_gsi"] += 1
            continue

    # Fallback: city centroid
    if addr and pref_name:
        result = find_city_centroid(addr, pref_name)
        if result:
            event["lat"], event["lon"] = result
            event["geocode_method"] = "city_centroid"
            stats["geocoded_city"] += 1
            continue

    # Fallback: prefecture centroid
    if pref_name:
        result = find_pref_centroid(pref_name)
        if result:
            event["lat"], event["lon"] = result
            event["geocode_method"] = "pref_centroid"
            stats["geocoded_pref"] += 1
            continue

    if (i + 1) % 50 == 0:
        print(f"    Geocoded {i + 1}/{total_to_geocode}...")

geocoded_total = stats["geocoded_gsi"] + stats["geocoded_city"] + stats["geocoded_pref"]
print(f"  Geocoding complete: {geocoded_total}/{total_to_geocode} geocoded")
print(f"    GSI: {stats['geocoded_gsi']}, City centroid: {stats['geocoded_city']}, Pref centroid: {stats['geocoded_pref']}")


# ================================================================
# PART D: Save Outputs
# ================================================================
print("\n" + "=" * 60)
print("PART D: Saving Outputs")
print("=" * 60)

output = {
    "generated_at": datetime.now().isoformat(),
    "period": {
        "from": WEEK_AGO.strftime("%Y-%m-%d"),
        "to": TODAY.strftime("%Y-%m-%d"),
    },
    "stats": {
        "total_events": len(all_events),
        "geocoded": geocoded_total,
        "geocoded_gsi": stats["geocoded_gsi"],
        "geocoded_city": stats["geocoded_city"],
        "geocoded_pref": stats["geocoded_pref"],
        "police_events": stats["police_events"],
        "nordot_events": stats["nordot_events"],
        "skipped_duplicates": stats["skipped_dup"],
        "errors": stats["errors"],
    },
    "events": all_events,
}

# Save main output
with open(OUT_FILE, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"  Saved: {OUT_FILE}")
print(f"    Size: {OUT_FILE.stat().st_size / 1024:.1f} KB")

# Save docs copy
with open(DOCS_OUT, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"  Saved: {DOCS_OUT}")

# Update seen_hashes
with open(SEEN_HASHES, "w", encoding="utf-8") as f:
    json.dump(sorted(list(seen_hashes)), f)
print(f"  Updated seen_hashes: {len(seen_hashes)} entries")

# === Summary ===
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"  Total events:       {len(all_events)}")
print(f"  From police sites:  {stats['police_events']}")
print(f"  From nordot:        {stats['nordot_events']}")
print(f"  Geocoded (total):   {geocoded_total}")
print(f"    - GSI API:        {stats['geocoded_gsi']}")
print(f"    - City centroid:  {stats['geocoded_city']}")
print(f"    - Pref centroid:  {stats['geocoded_pref']}")
print(f"  Skipped (dup):      {stats['skipped_dup']}")
print(f"  Errors:             {stats['errors']}")
print(f"\n  Per-prefecture breakdown:")
for pref in PREF_NAMES[1:]:
    count = pref_counts.get(pref, 0)
    if count > 0:
        print(f"    {pref}: {count}")
print(f"\n  Prefectures with 0 events: {47 - min(len(pref_counts), 47)}")
print("\nDone.")
