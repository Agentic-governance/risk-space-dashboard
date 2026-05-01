#!/usr/bin/env python3
"""Task 3: Public Transit Disruption scraping.
Scrapes Yahoo!路線情報 and NHK RSS for disruptions.
"""

import json
import os
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parent.parent
OUT_DYNAMIC = BASE / "data" / "dynamic" / "transit"
OUT_DOCS = BASE / "docs" / "data"
OUT_DYNAMIC.mkdir(parents=True, exist_ok=True)
OUT_DOCS.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9",
}
TIMEOUT = 15
NOW = datetime.now()

disruptions = []
stats = {"yahoo_transit": 0, "nhk_rss": 0}

# Severity keywords
SEVERITY_MAP = {
    "運転見合わせ": "suspension",
    "運休": "suspension",
    "遅延": "delay",
    "ダイヤ乱れ": "disruption",
    "徐行運転": "slow",
    "運転再開": "resumed",
    "見合わせ": "suspension",
    "人身事故": "fatal_accident",
}


# ── A. Yahoo!路線情報 ────────────────────────────────────────
def scrape_yahoo_transit():
    url = "https://transit.yahoo.co.jp/diainfo/"
    print(f"[A] Scraping Yahoo!路線情報: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        results = []

        # Try to find disruption entries
        # Yahoo transit uses various selectors depending on current layout
        found = False
        for sel in [
            "div.trouble", "div.elmTblLstLine", "table.tblDiaworst",
            "div.diaInfo", "li.line", "div.routeList", "tr",
            "div.mdServiceStatus", "div.serviceInfo",
        ]:
            items = soup.select(sel)
            if items and len(items) > 1:
                print(f"  Found {len(items)} items with selector '{sel}'")
                for item in items[:100]:
                    txt = item.get_text(strip=True)
                    # Check if this contains any disruption keyword
                    severity = None
                    for kw, sev in SEVERITY_MAP.items():
                        if kw in txt:
                            severity = sev
                            break
                    if severity:
                        # Try to extract line name
                        line_el = item.select_one("a, .lineName, td:first-child")
                        line_name = line_el.get_text(strip=True) if line_el else txt[:40]
                        results.append({
                            "source": "yahoo_transit",
                            "line_name": line_name[:60],
                            "severity": severity,
                            "raw_text": txt[:200],
                            "timestamp": NOW.isoformat(),
                            "risk_multiplier": 1.3 if severity == "suspension" else 1.15,
                            "risk_category": ["transit", "crowd", "delay"],
                        })
                found = True
                break

        if not found:
            # Broader search: any text containing disruption keywords
            print("  Trying broader text search...")
            for tag in soup.find_all(["div", "li", "td", "span", "p"]):
                txt = tag.get_text(strip=True)
                if len(txt) < 5 or len(txt) > 300:
                    continue
                for kw, sev in SEVERITY_MAP.items():
                    if kw in txt:
                        # Avoid duplicates
                        if not any(d["raw_text"] == txt[:200] for d in results):
                            results.append({
                                "source": "yahoo_transit",
                                "line_name": txt[:40],
                                "severity": sev,
                                "raw_text": txt[:200],
                                "timestamp": NOW.isoformat(),
                                "risk_multiplier": 1.3 if sev == "suspension" else 1.15,
                                "risk_category": ["transit", "crowd", "delay"],
                            })
                        break

        # If still nothing, the page loaded but there are no current disruptions
        if not results:
            print("  → No current disruptions found (may be normal operation)")
            # Check if page loaded correctly
            title = soup.title.get_text(strip=True) if soup.title else ""
            print(f"  Page title: {title}")

        stats["yahoo_transit"] = len(results)
        print(f"  → {len(results)} disruptions found")
        return results
    except Exception as e:
        print(f"  ⚠ Yahoo transit scrape failed: {e}")
        traceback.print_exc()
        return []


# ── B. NHK RSS ──────────────────────────────────────────────
NHK_FEEDS = [
    "https://www.nhk.or.jp/rss/news/cat0.xml",
    "https://www.nhk.or.jp/rss/news/cat3.xml",
]
TRANSIT_KEYWORDS = ["運休", "遅延", "見合わせ", "人身事故", "脱線", "運転再開", "ダイヤ", "鉄道"]


def scrape_nhk_rss():
    print("[B] Checking NHK RSS feeds for transit news...")
    results = []
    for feed_url in NHK_FEEDS:
        print(f"  Fetching: {feed_url}")
        try:
            feed = feedparser.parse(feed_url)
            if feed.bozo and not feed.entries:
                print(f"    ⚠ Feed parse error: {feed.bozo_exception}")
                continue
            print(f"    {len(feed.entries)} entries")
            for entry in feed.entries:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                combined = title + " " + summary
                # Check for transit keywords
                matched_kw = [kw for kw in TRANSIT_KEYWORDS if kw in combined]
                if matched_kw:
                    severity = "unknown"
                    for kw, sev in SEVERITY_MAP.items():
                        if kw in combined:
                            severity = sev
                            break
                    results.append({
                        "source": "nhk_rss",
                        "title": title,
                        "summary": summary[:200],
                        "link": entry.get("link", ""),
                        "published": entry.get("published", ""),
                        "matched_keywords": matched_kw,
                        "severity": severity,
                        "timestamp": NOW.isoformat(),
                        "risk_multiplier": 1.3 if severity == "suspension" else 1.15,
                        "risk_category": ["transit", "crowd"],
                    })
        except Exception as e:
            print(f"    ⚠ Feed error: {e}")

    stats["nhk_rss"] = len(results)
    print(f"  → {len(results)} transit-related news items")
    return results


# ── Main ──────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Task 3: Public Transit Disruption Collection")
    print(f"Date: {NOW.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    disruptions.extend(scrape_yahoo_transit())
    disruptions.extend(scrape_nhk_rss())

    # Collect unique line names
    line_names = list(set(
        d.get("line_name", d.get("title", ""))[:40]
        for d in disruptions
    ))

    result = {
        "generated_at": NOW.isoformat(),
        "stats": stats,
        "total_disruptions": len(disruptions),
        "affected_lines": line_names,
        "disruptions": disruptions,
    }

    # Save to both locations
    for path in [OUT_DYNAMIC / "disruptions.json", OUT_DOCS / "transit_disruptions.json"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nSaved → {path}")

    print("\n" + "=" * 60)
    print("RESULTS:")
    print(f"  Total disruptions: {len(disruptions)}")
    print(f"  Yahoo transit:     {stats['yahoo_transit']}")
    print(f"  NHK RSS:           {stats['nhk_rss']}")
    if line_names:
        print(f"  Affected lines:    {', '.join(line_names[:15])}")
        if len(line_names) > 15:
            print(f"                     ... and {len(line_names)-15} more")
    else:
        print("  No disruptions currently reported (normal operation)")
    print("=" * 60)


if __name__ == "__main__":
    main()
