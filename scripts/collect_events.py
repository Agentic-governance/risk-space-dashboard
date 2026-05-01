#!/usr/bin/env python3
"""Task 2: Full event calendar collection.
Scrapes じゃらん, J-League, NPB, holidays-jp API, and generates calendar events.
"""

import json
import os
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parent.parent
OUT_DYNAMIC = BASE / "data" / "dynamic" / "events"
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
YEAR = NOW.year

all_events = []
stats = {"jalan": 0, "jleague": 0, "npb": 0, "holidays": 0, "generated": 0}


# ── A. じゃらんnet ──────────────────────────────────────────────
def scrape_jalan():
    url = "https://www.jalan.net/event/"
    print(f"[A] Scraping じゃらんnet: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        events = []
        # Try multiple selectors for event listings
        for sel in [
            "div.item-event", "li.item-event", "div.event-list-item",
            "div.cassette_wrap", "article", "div.item_wrap",
        ]:
            items = soup.select(sel)
            if items:
                print(f"  Found {len(items)} items with selector '{sel}'")
                for item in items[:50]:
                    name_el = item.select_one("h2, h3, .item_name, .event_name, a.event_name")
                    date_el = item.select_one(".date, .event_date, time, .item_date")
                    loc_el = item.select_one(".area, .place, .location, .item_area")
                    name = name_el.get_text(strip=True) if name_el else item.get_text(strip=True)[:80]
                    date_str = date_el.get_text(strip=True) if date_el else ""
                    loc_str = loc_el.get_text(strip=True) if loc_el else ""
                    if name:
                        events.append({
                            "source": "jalan",
                            "type": "festival_event",
                            "name": name,
                            "date_raw": date_str,
                            "location": loc_str,
                            "risk_multiplier": 1.15,
                            "risk_category": ["crowd", "traffic"],
                        })
                break
        if not events:
            # Fallback: grab any links that look event-ish
            for a in soup.select("a[href*='/event/']")[:30]:
                txt = a.get_text(strip=True)
                if len(txt) > 4:
                    events.append({
                        "source": "jalan",
                        "type": "festival_event",
                        "name": txt,
                        "date_raw": "",
                        "location": "",
                        "risk_multiplier": 1.15,
                        "risk_category": ["crowd", "traffic"],
                    })
        stats["jalan"] = len(events)
        print(f"  → {len(events)} events extracted")
        return events
    except Exception as e:
        print(f"  ⚠ じゃらん scrape failed (expected): {e}")
        return []


# ── B-1. J-League ──────────────────────────────────────────────
def scrape_jleague():
    url = "https://www.jleague.jp/match/"
    print(f"[B-1] Scraping J-League: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        events = []
        # Try match schedule selectors
        for sel in [
            "div.matchCard", "div.match-card", "tr.match", "li.match",
            "div.matchListWrap", "section.matchList", "div.scheduleList",
            "div.match-data", "article.match",
        ]:
            items = soup.select(sel)
            if items:
                print(f"  Found {len(items)} items with selector '{sel}'")
                for item in items[:50]:
                    teams = [t.get_text(strip=True) for t in item.select(".team, .teamName, .club-name, td.team")]
                    date_el = item.select_one(".date, time, .matchDate, .schedule-date")
                    venue_el = item.select_one(".stadium, .venue, .place, .matchVenue")
                    match_name = " vs ".join(teams[:2]) if teams else item.get_text(strip=True)[:60]
                    date_str = date_el.get_text(strip=True) if date_el else ""
                    venue = venue_el.get_text(strip=True) if venue_el else ""
                    if match_name.strip():
                        events.append({
                            "source": "jleague",
                            "type": "sports_match",
                            "name": f"J-League: {match_name}",
                            "date_raw": date_str,
                            "venue": venue,
                            "risk_multiplier": 1.2,
                            "risk_category": ["crowd", "traffic", "public_order"],
                        })
                break
        if not events:
            # Fallback: look for text patterns
            for tag in soup.find_all(["div", "td", "span"], string=lambda s: s and "vs" in str(s)):
                txt = tag.get_text(strip=True)
                if 5 < len(txt) < 80:
                    events.append({
                        "source": "jleague",
                        "type": "sports_match",
                        "name": f"J-League: {txt}",
                        "date_raw": "",
                        "venue": "",
                        "risk_multiplier": 1.2,
                        "risk_category": ["crowd", "traffic", "public_order"],
                    })
        stats["jleague"] = len(events)
        print(f"  → {len(events)} matches extracted")
        return events
    except Exception as e:
        print(f"  ⚠ J-League scrape failed: {e}")
        return []


# ── B-2. NPB ──────────────────────────────────────────────────
def scrape_npb():
    url = "https://npb.jp/games/2026/"
    print(f"[B-2] Scraping NPB: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        events = []
        for sel in [
            "div.game_tbl", "table.game", "div.gameCard", "tr",
            "div.score_box", "div.game-card",
        ]:
            items = soup.select(sel)
            if items and len(items) > 2:
                print(f"  Found {len(items)} items with selector '{sel}'")
                for item in items[:60]:
                    txt = item.get_text(strip=True)
                    if len(txt) > 3 and len(txt) < 200:
                        events.append({
                            "source": "npb",
                            "type": "sports_match",
                            "name": f"NPB: {txt[:80]}",
                            "date_raw": "",
                            "venue": "",
                            "risk_multiplier": 1.2,
                            "risk_category": ["crowd", "traffic"],
                        })
                break
        # Also try main page
        if not events:
            r2 = requests.get("https://npb.jp/", headers=HEADERS, timeout=TIMEOUT)
            soup2 = BeautifulSoup(r2.text, "html.parser")
            for a in soup2.select("a[href*='/games/']")[:20]:
                txt = a.get_text(strip=True)
                if len(txt) > 3:
                    events.append({
                        "source": "npb",
                        "type": "sports_match",
                        "name": f"NPB: {txt[:80]}",
                        "date_raw": "",
                        "venue": "",
                        "risk_multiplier": 1.2,
                        "risk_category": ["crowd", "traffic"],
                    })
        stats["npb"] = len(events)
        print(f"  → {len(events)} matches extracted")
        return events
    except Exception as e:
        print(f"  ⚠ NPB scrape failed: {e}")
        return []


# ── C. Holidays ──────────────────────────────────────────────
HOLIDAY_RISK = {
    "default": 1.15,
    "元日": 1.3,
    "成人の日": 1.2,
    "建国記念の日": 1.1,
    "天皇誕生日": 1.15,
    "春分の日": 1.1,
    "昭和の日": 1.25,
    "憲法記念日": 1.25,
    "みどりの日": 1.25,
    "こどもの日": 1.25,
    "海の日": 1.2,
    "山の日": 1.2,
    "敬老の日": 1.1,
    "秋分の日": 1.1,
    "スポーツの日": 1.15,
    "文化の日": 1.1,
    "勤労感謝の日": 1.1,
}


def load_holidays():
    url = "https://holidays-jp.github.io/api/v1/date.json"
    print(f"[C] Loading holidays: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        events = []
        for date_str, name in data.items():
            # Filter to current/next year
            if date_str.startswith(str(YEAR)) or date_str.startswith(str(YEAR + 1)):
                mult = HOLIDAY_RISK.get(name, HOLIDAY_RISK["default"])
                events.append({
                    "source": "holidays-jp",
                    "type": "public_holiday",
                    "name": name,
                    "date": date_str,
                    "risk_multiplier": mult,
                    "risk_category": ["traffic", "crowd", "incident"],
                })
        stats["holidays"] = len(events)
        print(f"  → {len(events)} holidays loaded ({YEAR}-{YEAR+1})")
        return events
    except Exception as e:
        print(f"  ⚠ Holiday load failed: {e}")
        return []


# ── D. Generated Calendar Events ─────────────────────────────
def generate_calendar_events():
    print("[D] Generating calendar events...")
    events = []

    # Payday: 25th and month-end
    for y in [YEAR, YEAR + 1]:
        for m in range(1, 13):
            # 25th
            events.append({
                "source": "generated",
                "type": "payday",
                "name": f"給料日 ({y}/{m:02d}/25)",
                "date": f"{y}-{m:02d}-25",
                "risk_multiplier": 1.25,
                "risk_category": ["incident", "nightlife", "traffic"],
                "note": "payday effect: increased spending, drinking, incidents",
            })
            # Month-end
            import calendar
            last_day = calendar.monthrange(y, m)[1]
            if last_day != 25:
                events.append({
                    "source": "generated",
                    "type": "payday",
                    "name": f"月末給料日 ({y}/{m:02d}/{last_day})",
                    "date": f"{y}-{m:02d}-{last_day:02d}",
                    "risk_multiplier": 1.25,
                    "risk_category": ["incident", "nightlife", "traffic"],
                    "note": "month-end payday effect",
                })

    # School term end: March 20, July 20, December 20 (14-day window)
    for y in [YEAR, YEAR + 1]:
        for m, label in [(3, "春休み開始"), (7, "夏休み開始"), (12, "冬休み開始")]:
            start = datetime(y, m, 20)
            events.append({
                "source": "generated",
                "type": "school_break",
                "name": f"{label} ({y})",
                "date_start": start.strftime("%Y-%m-%d"),
                "date_end": (start + timedelta(days=14)).strftime("%Y-%m-%d"),
                "duration_days": 14,
                "risk_multiplier": 1.15,
                "risk_category": ["juvenile", "traffic", "crowd"],
                "note": "school term end: increased juvenile activity, family travel",
            })

    # Golden Week: April 29 - May 6
    for y in [YEAR, YEAR + 1]:
        events.append({
            "source": "generated",
            "type": "holiday_period",
            "name": f"ゴールデンウィーク ({y})",
            "date_start": f"{y}-04-29",
            "date_end": f"{y}-05-06",
            "duration_days": 8,
            "risk_multiplier": 1.3,
            "risk_category": ["traffic", "crowd", "incident", "tourism"],
            "note": "GW: peak travel, highway congestion, tourist area crowding",
        })

    # Obon: August 13-17
    for y in [YEAR, YEAR + 1]:
        events.append({
            "source": "generated",
            "type": "holiday_period",
            "name": f"お盆 ({y})",
            "date_start": f"{y}-08-13",
            "date_end": f"{y}-08-17",
            "duration_days": 5,
            "risk_multiplier": 1.2,
            "risk_category": ["burglary", "traffic", "urban_crime"],
            "note": "Obon: urban areas emptied → increased burglary risk; highway congestion",
        })

    # Year-end / New Year: Dec 28 - Jan 3
    for y in [YEAR, YEAR + 1]:
        events.append({
            "source": "generated",
            "type": "holiday_period",
            "name": f"年末年始 ({y}-{y+1})",
            "date_start": f"{y}-12-28",
            "date_end": f"{y+1}-01-03",
            "duration_days": 7,
            "risk_multiplier": 1.25,
            "risk_category": ["burglary", "traffic", "incident", "fire"],
            "note": "year-end: drinking, fire risk, empty homes → burglary",
        })

    stats["generated"] = len(events)
    print(f"  → {len(events)} generated events")
    return events


# ── Main ──────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Task 2: Event Calendar Collection")
    print(f"Date: {NOW.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    all_events.extend(scrape_jalan())
    all_events.extend(scrape_jleague())
    all_events.extend(scrape_npb())
    all_events.extend(load_holidays())
    all_events.extend(generate_calendar_events())

    result = {
        "generated_at": NOW.isoformat(),
        "stats": stats,
        "total_events": len(all_events),
        "events": all_events,
    }

    # Save to both locations
    for path in [OUT_DYNAMIC / "all_events.json", OUT_DOCS / "all_events.json"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nSaved → {path}")

    print("\n" + "=" * 60)
    print("STATS:")
    for k, v in stats.items():
        print(f"  {k:>12}: {v}")
    print(f"  {'TOTAL':>12}: {len(all_events)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
