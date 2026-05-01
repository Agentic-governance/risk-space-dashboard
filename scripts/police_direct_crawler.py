#!/usr/bin/env python3
"""Direct crawler for suspicious/crime reports from prefectural police websites."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; RiskSpaceMCP/1.0)"
HEADERS = {"User-Agent": USER_AGENT}
REQUEST_TIMEOUT = 30
REQUEST_SLEEP_SEC = 2.0

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(BASE_DIR, "docs", "data", "police_direct_incidents.json")

PREFECTURES_ORDER = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]

PREF_DOMAIN = {
    "北海道": "hokkaido",
    "青森県": "aomori",
    "岩手県": "iwate",
    "宮城県": "miyagi",
    "秋田県": "akita",
    "山形県": "yamagata",
    "福島県": "fukushima",
    "茨城県": "ibaraki",
    "栃木県": "tochigi",
    "群馬県": "gunma",
    "埼玉県": "saitama",
    "千葉県": "chiba",
    "神奈川県": "kanagawa",
    "新潟県": "niigata",
    "富山県": "toyama",
    "石川県": "ishikawa",
    "福井県": "fukui",
    "山梨県": "yamanashi",
    "長野県": "nagano",
    "岐阜県": "gifu",
    "静岡県": "shizuoka",
    "愛知県": "aichi",
    "三重県": "mie",
    "滋賀県": "shiga",
    "京都府": "kyoto",
    "大阪府": "osaka",
    "兵庫県": "hyogo",
    "奈良県": "nara",
    "和歌山県": "wakayama",
    "鳥取県": "tottori",
    "島根県": "shimane",
    "岡山県": "okayama",
    "広島県": "hiroshima",
    "山口県": "yamaguchi",
    "徳島県": "tokushima",
    "香川県": "kagawa",
    "愛媛県": "ehime",
    "高知県": "kochi",
    "福岡県": "fukuoka",
    "佐賀県": "saga",
    "長崎県": "nagasaki",
    "熊本県": "kumamoto",
    "大分県": "oita",
    "宮崎県": "miyazaki",
    "鹿児島県": "kagoshima",
    "沖縄県": "okinawa",
}

KIND_KEYWORDS = [
    ("不審者", "不審者"),
    ("声かけ", "声かけ"),
    ("つきまとい", "つきまとい"),
    ("痴漢", "痴漢"),
    ("盗撮", "盗撮"),
    ("のぞき", "のぞき"),
    ("露出", "露出"),
    ("強盗", "強盗"),
    ("ひったくり", "ひったくり"),
    ("空き巣", "空き巣"),
    ("窃盗", "窃盗"),
    ("詐欺", "詐欺"),
    ("暴行", "暴行"),
    ("傷害", "傷害"),
    ("刃物", "刃物"),
    ("凶器", "凶器"),
]

CITY_PAT = re.compile(r"(札幌市|[\u4e00-\u9fff]{1,6}市|[\u4e00-\u9fff]{1,6}区|[\u4e00-\u9fff]{1,6}町|[\u4e00-\u9fff]{1,6}村)")
DATE_PATTERNS = [
    re.compile(r"(20\d{2}[/-]\d{1,2}[/-]\d{1,2})"),
    re.compile(r"(20\d{2}年\d{1,2}月\d{1,2}日)"),
    re.compile(r"(\d{1,2}月\d{1,2}日)"),
]


@dataclass(frozen=True)
class Source:
    prefecture: str
    method: str
    url: str
    fallback_urls: Tuple[str, ...] = ()


def build_prefecture_sources() -> Dict[str, Source]:
    sources: Dict[str, Source] = {
        "北海道": Source(
            prefecture="北海道",
            method="police_pref",
            url="https://www.police.pref.hokkaido.lg.jp/info/soumu/dekigoto/",
            fallback_urls=("https://www.police.pref.hokkaido.lg.jp/",),
        ),
        "宮城県": Source(
            prefecture="宮城県",
            method="sugumail",
            url="https://plus.sugumail.com/usr/miyagi-police/doc",
        ),
        "大阪府": Source(
            prefecture="大阪府",
            method="sugumail",
            url="https://plus.sugumail.com/usr/osaka-police-anmachi/doc",
        ),
        "東京都": Source(
            prefecture="東京都",
            method="custom",
            url="https://www.keishicho.metro.tokyo.lg.jp/",
        ),
    }

    for pref in PREFECTURES_ORDER:
        if pref in sources:
            continue
        domain = PREF_DOMAIN.get(pref)
        if not domain:
            sources[pref] = Source(prefecture=pref, method="custom", url="")
            continue
        sources[pref] = Source(
            prefecture=pref,
            method="police_pref",
            url=f"https://www.police.pref.{domain}.jp/",
            fallback_urls=(f"https://www.police.pref.{domain}.lg.jp/",),
        )

    return sources


PREFECTURE_SOURCES = build_prefecture_sources()


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def detect_kind_name(title: str, description: str) -> str:
    text = f"{title} {description}"
    for kw, kind in KIND_KEYWORDS:
        if kw in text:
            return kind
    return "不審者"


def detect_city(prefecture: str, text: str) -> str:
    if not text:
        return ""
    if text.startswith(prefecture):
        text = text[len(prefecture) :]
    m = CITY_PAT.search(text)
    return m.group(1) if m else ""


def extract_date(text: str) -> str:
    txt = normalize_space(text)
    for pat in DATE_PATTERNS:
        m = pat.search(txt)
        if m:
            return m.group(1)
    return ""


def make_dedupe_key(prefecture: str, date: str, title: str) -> str:
    raw = f"{prefecture}|{date}|{title}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def make_incident_id(prefecture: str, date: str, title: str, url: str) -> str:
    raw = f"{prefecture}|{date}|{title}|{url}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()[:16]


def fetch_html(session: requests.Session, url: str) -> Optional[str]:
    try:
        resp = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        print(f"[WARN] fetch failed: {url} ({exc})")
        return None
    finally:
        time.sleep(REQUEST_SLEEP_SEC)


def pick_prefecture_url(session: requests.Session, source: Source) -> Optional[str]:
    for candidate in (source.url,) + source.fallback_urls:
        if not candidate:
            continue
        html = fetch_html(session, candidate)
        if html:
            return candidate
    return None


def extract_sugumail_items(list_html: str, base_url: str) -> List[Tuple[str, str, str, str]]:
    soup = BeautifulSoup(list_html, "html.parser")
    items: List[Tuple[str, str, str, str]] = []

    blocks = soup.select("li.mdl-list__item") or soup.select("article") or soup.select("li")
    for block in blocks:
        title_el = block.select_one("h5.info_title") or block.find(["h5", "h4", "h3", "a"])
        date_el = block.select_one("p.info_date") or block.find("time")
        desc_el = block.select_one("p.info_description") or block.find("p")
        link_el = block.find("a", href=True)

        title = normalize_space(title_el.get_text(" ", strip=True)) if title_el else ""
        date_text = normalize_space(date_el.get_text(" ", strip=True)) if date_el else ""
        desc = normalize_space(desc_el.get_text(" ", strip=True)) if desc_el else ""
        link = urljoin(base_url, link_el["href"]) if link_el else ""

        if not title and not desc:
            continue
        if not link and block.get("data-href"):
            link = urljoin(base_url, block.get("data-href"))

        items.append((title, date_text, desc, link))

    return items


def extract_sugumail_detail(detail_html: str) -> str:
    soup = BeautifulSoup(detail_html, "html.parser")
    body = (
        soup.select_one("div.info_detail")
        or soup.select_one("div.mdl-card__supporting-text")
        or soup.select_one("article")
        or soup.select_one("main")
        or soup.body
    )
    if not body:
        return ""
    text = normalize_space(body.get_text("\n", strip=True))
    return text[:12000]


def crawl_sugumail(
    session: requests.Session,
    source: Source,
    max_pages: int,
    seen: Set[str],
) -> List[dict]:
    incidents: List[dict] = []

    for page in range(1, max_pages + 1):
        list_url = source.url if page == 1 else f"{source.url}?page={page}"
        html = fetch_html(session, list_url)
        if not html:
            continue

        items = extract_sugumail_items(html, list_url)
        if not items:
            continue

        for title, date_text, brief, detail_url in items:
            detail_text = brief
            if detail_url:
                detail_html = fetch_html(session, detail_url)
                if detail_html:
                    parsed = extract_sugumail_detail(detail_html)
                    if parsed:
                        detail_text = parsed

            date = extract_date(date_text or detail_text)
            key = make_dedupe_key(source.prefecture, date, title)
            if key in seen:
                continue
            seen.add(key)

            city = detect_city(source.prefecture, detail_text)
            kind_name = detect_kind_name(title, detail_text)
            incident_id = make_incident_id(source.prefecture, date, title, detail_url or list_url)
            incidents.append(
                {
                    "id": incident_id,
                    "date": date,
                    "prefecture": source.prefecture,
                    "city": city,
                    "title": title,
                    "description": detail_text,
                    "kind_name": kind_name,
                    "lat": None,
                    "lng": None,
                }
            )

    return incidents


def collect_candidate_links(base_url: str, html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    domain = urlparse(base_url).netloc
    out: List[str] = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("javascript:") or href.startswith("mailto:"):
            continue
        url = urljoin(base_url, href)
        parsed = urlparse(url)
        if parsed.netloc != domain:
            continue

        anchor_text = normalize_space(a.get_text(" ", strip=True))
        score_text = (url + " " + anchor_text).lower()
        if any(k in score_text for k in [
            "anzen", "bouhan", "seian", "jiken", "fushin", "dekigoto", "opendata",
            "不審", "犯罪", "防犯", "事件", "安全",
        ]):
            out.append(url)

    seen_local: Set[str] = set()
    uniq: List[str] = []
    for link in out:
        if link in seen_local:
            continue
        seen_local.add(link)
        uniq.append(link)
    return uniq


def extract_generic_incidents(prefecture: str, page_url: str, html: str, seen: Set[str]) -> List[dict]:
    soup = BeautifulSoup(html, "html.parser")
    incidents: List[dict] = []

    blocks = soup.select("article") or soup.select("li") or soup.select("div")
    for block in blocks:
        text = normalize_space(block.get_text(" ", strip=True))
        if len(text) < 20:
            continue
        if not any(k in text for k in ["不審", "犯罪", "防犯", "事件", "痴漢", "声かけ", "盗撮", "強盗"]):
            continue

        title_el = block.find(["h1", "h2", "h3", "h4", "h5", "a"])
        title = normalize_space(title_el.get_text(" ", strip=True)) if title_el else text[:80]
        date = extract_date(text)
        key = make_dedupe_key(prefecture, date, title)
        if key in seen:
            continue
        seen.add(key)

        city = detect_city(prefecture, text)
        kind_name = detect_kind_name(title, text)
        incident_id = make_incident_id(prefecture, date, title, page_url)
        incidents.append(
            {
                "id": incident_id,
                "date": date,
                "prefecture": prefecture,
                "city": city,
                "title": title,
                "description": text[:12000],
                "kind_name": kind_name,
                "lat": None,
                "lng": None,
            }
        )

    return incidents


def crawl_police_pref(
    session: requests.Session,
    source: Source,
    max_pages: int,
    seen: Set[str],
) -> List[dict]:
    incidents: List[dict] = []

    start_url = pick_prefecture_url(session, source)
    if not start_url:
        print(f"[SKIP] {source.prefecture}: unreachable source")
        return incidents

    queue: List[str] = [start_url]
    visited: Set[str] = set()

    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue

        html = fetch_html(session, url)
        if not html:
            visited.add(url)
            continue

        page_incidents = extract_generic_incidents(source.prefecture, url, html, seen)
        incidents.extend(page_incidents)
        visited.add(url)

        for link in collect_candidate_links(url, html):
            if link not in visited and link not in queue and len(visited) + len(queue) < max_pages * 4:
                queue.append(link)

    return incidents


def crawl_prefecture(
    session: requests.Session,
    source: Source,
    max_pages: int,
    seen: Set[str],
) -> List[dict]:
    if source.method == "sugumail":
        return crawl_sugumail(session, source, max_pages=max_pages, seen=seen)
    if source.method == "police_pref":
        return crawl_police_pref(session, source, max_pages=max_pages, seen=seen)

    print(f"[SKIP] {source.prefecture}: method={source.method} not implemented")
    return []


def save_incidents(path: str, incidents: List[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(incidents),
        "incidents": incidents,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Direct crawler for prefectural police incident info")
    parser.add_argument(
        "--test-only",
        action="store_true",
        help="crawl only 3 prefectures for test: 北海道, 大阪府, 宮城県",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=10,
        help="max pages per prefecture (default: 10, test mode uses min(3, this))",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.test_only:
        targets = ["北海道", "大阪府", "宮城県"]
        max_pages = min(3, max(1, args.max_pages))
    else:
        targets = list(PREFECTURES_ORDER)
        max_pages = max(1, args.max_pages)

    print(f"[INFO] targets={targets}")
    print(f"[INFO] max_pages={max_pages} sleep={REQUEST_SLEEP_SEC}s user_agent={USER_AGENT}")

    session = requests.Session()
    all_incidents: List[dict] = []
    seen_keys: Set[str] = set()

    for idx, pref in enumerate(targets, start=1):
        source = PREFECTURE_SOURCES.get(pref)
        if not source:
            print(f"[SKIP] {pref}: source not configured")
            continue

        print(f"[CRAWL] {idx}/{len(targets)} {pref} method={source.method} url={source.url}")
        incidents = crawl_prefecture(session, source, max_pages=max_pages, seen=seen_keys)
        print(f"[DONE] {pref}: incidents={len(incidents)}")
        all_incidents.extend(incidents)

    save_incidents(OUT_PATH, all_incidents)
    print(f"[WRITE] {OUT_PATH} count={len(all_incidents)}")


if __name__ == "__main__":
    main()
