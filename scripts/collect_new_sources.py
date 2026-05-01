#!/usr/bin/env python3
"""
Task 1: Collect all new data sources for Risk Space MCP.
  1-1. NHK RSS feeds (crime/disaster filtering)
  1-2. Yahoo! Realtime Search (suspicious person / crime queries)
  1-3. River flood forecast data
  1-4. Telegram schema design
  1-5. Land price schema design
"""

from __future__ import annotations
import feedparser
import requests
import json
import os
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "data" / "realtime"

# ── Helpers ──────────────────────────────────────────────────────────

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36"
}

# Crime / disaster keyword sets
CRIME_KW = [
    "事件", "犯罪", "逮捕", "容疑", "強盗", "殺人", "暴行", "傷害",
    "詐欺", "窃盗", "不審者", "ひったくり", "空き巣", "痴漢",
    "ストーカー", "脅迫", "恐喝", "誘拐", "放火", "薬物", "覚醒剤",
    "大麻", "銃", "刃物", "包丁", "ナイフ", "通り魔", "暴力団",
    "闇バイト", "特殊詐欺", "オレオレ詐欺", "還付金詐欺"
]
DISASTER_KW = [
    "地震", "津波", "台風", "豪雨", "大雨", "洪水", "浸水", "土砂崩れ",
    "土砂災害", "噴火", "火山", "竜巻", "暴風", "高潮", "避難",
    "災害", "被害", "警報", "注意報", "特別警報", "氾濫", "決壊",
    "停電", "断水", "ライフライン"
]
TRAFFIC_KW = [
    "交通事故", "死亡事故", "ひき逃げ", "飲酒運転", "あおり運転",
    "通行止め", "衝突", "横転"
]
ANIMAL_KW = [
    "クマ", "熊", "出没", "目撃", "サル", "イノシシ"
]
ALL_KW = CRIME_KW + DISASTER_KW + TRAFFIC_KW + ANIMAL_KW

PREFECTURES = [
    "北海道", "青森", "岩手", "宮城", "秋田", "山形", "福島",
    "茨城", "栃木", "群馬", "埼玉", "千葉", "東京", "神奈川",
    "新潟", "富山", "石川", "福井", "山梨", "長野", "岐阜",
    "静岡", "愛知", "三重", "滋賀", "京都", "大阪", "兵庫",
    "奈良", "和歌山", "鳥取", "島根", "岡山", "広島", "山口",
    "徳島", "香川", "愛媛", "高知", "福岡", "佐賀", "長崎",
    "熊本", "大分", "宮崎", "鹿児島", "沖縄"
]

# Regional NHK source -> prefecture mapping hint
REGION_MAP = {
    "NHK北海道": "北海道",
    "NHK東北": None,   # multi-prefecture
    "NHK関西": None,
    "NHK九州": None,
}

def classify_subtype(text: str) -> str:
    for kw in CRIME_KW:
        if kw in text:
            return "crime"
    for kw in DISASTER_KW:
        if kw in text:
            return "disaster"
    for kw in TRAFFIC_KW:
        if kw in text:
            return "traffic"
    for kw in ANIMAL_KW:
        if kw in text:
            return "animal_hazard"
    return "other"

def estimate_severity(text: str) -> int:
    """1-5 severity scale based on keyword intensity."""
    high = ["殺人", "死亡", "津波", "特別警報", "噴火", "氾濫", "決壊",
            "通り魔", "銃", "爆発", "テロ"]
    mid = ["強盗", "逮捕", "警報", "避難", "土砂災害", "洪水", "浸水",
           "暴行", "傷害", "放火", "誘拐", "死亡事故"]
    for kw in high:
        if kw in text:
            return 5
    for kw in mid:
        if kw in text:
            return 4
    return 3

def extract_prefecture(text: str, source_name: str = "") -> str | None:
    # Check regional source hint first
    if source_name in REGION_MAP and REGION_MAP[source_name]:
        return REGION_MAP[source_name]
    for pref in PREFECTURES:
        if pref in text:
            return pref
    return None


# ══════════════════════════════════════════════════════════════════════
# 1-1  NHK RSS
# ══════════════════════════════════════════════════════════════════════

def collect_nhk_rss() -> dict:
    print("\n" + "="*60)
    print("1-1. NHK RSS Collection")
    print("="*60)

    RSS_SOURCES = [
        {"name": "NHK社会",   "url": "https://www.nhk.or.jp/rss/news/cat3.xml"},
        {"name": "NHK地域",   "url": "https://www.nhk.or.jp/rss/news/cat0.xml"},
        {"name": "NHK科学",   "url": "https://www.nhk.or.jp/rss/news/cat4.xml"},
        {"name": "NHK北海道", "url": "https://www3.nhk.or.jp/sapporo-news/feed/"},
        {"name": "NHK東北",   "url": "https://www3.nhk.or.jp/tohoku-news/feed/"},
        {"name": "NHK関西",   "url": "https://www3.nhk.or.jp/kansai-news/feed/"},
        {"name": "NHK九州",   "url": "https://www3.nhk.or.jp/fukuoka-news/feed/"},
    ]

    events = []
    stats = {"total_entries": 0, "filtered_entries": 0, "sources_ok": 0, "sources_fail": 0}

    for src in RSS_SOURCES:
        name, url = src["name"], src["url"]
        print(f"\n  Fetching {name}: {url}")
        try:
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                print(f"    WARN: feed parse error: {feed.bozo_exception}")
                stats["sources_fail"] += 1
                continue

            entry_count = len(feed.entries)
            stats["total_entries"] += entry_count
            stats["sources_ok"] += 1
            matched = 0

            for entry in feed.entries:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                text = title + " " + summary

                # Filter: must match at least one keyword
                if not any(kw in text for kw in ALL_KW):
                    continue

                matched += 1
                subtype = classify_subtype(text)
                severity = estimate_severity(text)
                prefecture = extract_prefecture(text, name)

                published = entry.get("published", entry.get("updated", ""))

                events.append({
                    "source": name,
                    "title": title,
                    "url": entry.get("link", ""),
                    "published": published,
                    "subtype": subtype,
                    "severity": severity,
                    "prefecture": prefecture,
                    "summary_snippet": summary[:200] if summary else "",
                    "collected_at": datetime.now(timezone.utc).isoformat()
                })

            stats["filtered_entries"] += matched
            print(f"    Entries: {entry_count}, Matched keywords: {matched}")

        except Exception as e:
            print(f"    ERROR: {e}")
            stats["sources_fail"] += 1

    # Save
    out_dir = BASE / "news"
    ensure_dir(out_dir)
    out_path = out_dir / "nhk_events.json"
    result = {
        "metadata": {
            "collector": "nhk_rss",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "stats": stats
        },
        "events": events
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved {len(events)} events -> {out_path}")
    return stats


# ══════════════════════════════════════════════════════════════════════
# 1-2  Yahoo! Realtime Search
# ══════════════════════════════════════════════════════════════════════

def collect_yahoo_realtime() -> dict:
    print("\n" + "="*60)
    print("1-2. Yahoo! Realtime Search")
    print("="*60)

    queries = ["不審者", "強盗", "クマ出没", "ひったくり", "空き巣", "特殊詐欺"]
    all_tweets = []
    stats = {"queries": len(queries), "total_results": 0, "queries_ok": 0, "queries_fail": 0}

    for query in queries:
        print(f"\n  Query: {query}")
        url = "https://search.yahoo.co.jp/realtime/search"
        params = {"p": query, "ei": "UTF-8"}
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
            print(f"    HTTP {resp.status_code}, {len(resp.content)} bytes")

            if resp.status_code != 200:
                stats["queries_fail"] += 1
                print(f"    SKIP: non-200 status")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Yahoo Realtime uses various selectors; try multiple approaches
            items = []

            # Approach 1: look for tweet-like article elements
            for article in soup.select("article, .Tweet, .tw, [data-tweet-id]"):
                text_el = article.select_one(".tw-text, .Tweet-text, p")
                if text_el:
                    items.append({
                        "text": text_el.get_text(strip=True)[:300],
                        "source_element": "article"
                    })

            # Approach 2: look for list items in search results
            if not items:
                for li in soup.select("li.sr_normal, div.contents, section.tl"):
                    text = li.get_text(strip=True)[:300]
                    if len(text) > 20:
                        items.append({"text": text, "source_element": "li/div"})

            # Approach 3: broader - get all <p> or div with substantial text
            if not items:
                for tag in soup.select("div.tl p, section p, main p"):
                    text = tag.get_text(strip=True)
                    if len(text) > 30 and query in text:
                        items.append({"text": text[:300], "source_element": "p"})

            # Approach 4: if still nothing, save page structure note
            if not items:
                # Check if there's a CAPTCHA or redirect
                page_title = soup.title.get_text(strip=True) if soup.title else "no title"
                print(f"    No tweet items found. Page title: {page_title}")
                # Save a diagnostic note
                items.append({
                    "text": f"[NO RESULTS PARSED] Page title: {page_title}",
                    "source_element": "diagnostic",
                    "note": "Yahoo Realtime may require JS rendering or have changed layout"
                })

            for item in items[:10]:  # max 10 per query
                all_tweets.append({
                    "query": query,
                    "text": item["text"],
                    "parse_method": item.get("source_element", "unknown"),
                    "subtype": classify_subtype(item["text"]),
                    "severity": estimate_severity(item["text"]),
                    "prefecture": extract_prefecture(item["text"]),
                    "collected_at": datetime.now(timezone.utc).isoformat()
                })

            count = len(items)
            stats["total_results"] += min(count, 10)
            stats["queries_ok"] += 1
            print(f"    Parsed items: {count}")

        except Exception as e:
            print(f"    ERROR: {e}")
            stats["queries_fail"] += 1

    # Save
    out_dir = BASE / "sns"
    ensure_dir(out_dir)
    out_path = out_dir / "yahoo_realtime.json"
    result = {
        "metadata": {
            "collector": "yahoo_realtime",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "stats": stats,
            "note": "Yahoo Realtime Search results. JS-rendered content may not be available via static HTML fetch."
        },
        "items": all_tweets
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved {len(all_tweets)} items -> {out_path}")
    return stats


# ══════════════════════════════════════════════════════════════════════
# 1-3  River Flood Data
# ══════════════════════════════════════════════════════════════════════

def collect_river_flood() -> dict:
    print("\n" + "="*60)
    print("1-3. River Flood Forecast Data")
    print("="*60)

    stats = {"river_go_jp": "unknown", "jma_warnings": "unknown"}
    forecasts = []

    # Try river.go.jp XML
    RIVER_URL = "https://www.river.go.jp/kawabou/xml/out/floodForecast.xml"
    print(f"\n  Fetching: {RIVER_URL}")
    try:
        resp = requests.get(RIVER_URL, headers=HEADERS, timeout=15)
        print(f"    HTTP {resp.status_code}, {len(resp.content)} bytes")
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, "lxml-xml")
            # Try to parse XML elements
            items = soup.find_all(["item", "entry", "forecast", "river", "warning"])
            if items:
                for item in items[:50]:
                    forecasts.append({
                        "source": "river.go.jp",
                        "tag": item.name,
                        "text": item.get_text(strip=True)[:500],
                        "attrs": dict(item.attrs) if item.attrs else {}
                    })
                stats["river_go_jp"] = f"OK: {len(items)} elements"
                print(f"    Parsed {len(items)} XML elements")
            else:
                # Maybe the whole document is the data
                root_tag = soup.find()
                root_name = root_tag.name if root_tag else "none"
                stats["river_go_jp"] = f"OK but no recognized elements (root: {root_name})"
                forecasts.append({
                    "source": "river.go.jp",
                    "tag": "raw_root",
                    "text": resp.text[:2000],
                    "note": "Raw XML saved for structure analysis"
                })
                print(f"    No standard elements found, saved raw (root: {root_name})")
        else:
            stats["river_go_jp"] = f"HTTP {resp.status_code}"
            print(f"    Non-200 status")
    except Exception as e:
        stats["river_go_jp"] = f"ERROR: {e}"
        print(f"    ERROR: {e}")

    # Try alternative river.go.jp URLs
    ALT_URLS = [
        "https://www.river.go.jp/kawabou/xml/out/waterLevelWarning.xml",
        "https://www.river.go.jp/kawabou/xml/out/rainWarning.xml",
    ]
    for alt_url in ALT_URLS:
        print(f"\n  Trying alt: {alt_url}")
        try:
            resp = requests.get(alt_url, headers=HEADERS, timeout=10)
            print(f"    HTTP {resp.status_code}, {len(resp.content)} bytes")
            if resp.status_code == 200 and len(resp.content) > 100:
                forecasts.append({
                    "source": alt_url,
                    "tag": "raw",
                    "text": resp.text[:2000],
                    "note": "Alternative river data endpoint"
                })
        except Exception as e:
            print(f"    ERROR: {e}")

    # Try JMA warning RSS
    JMA_URL = "https://www.data.jma.go.jp/developer/xml/feed/extra.xml"
    print(f"\n  Fetching JMA warnings: {JMA_URL}")
    try:
        resp = requests.get(JMA_URL, headers=HEADERS, timeout=15)
        print(f"    HTTP {resp.status_code}, {len(resp.content)} bytes")
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, "lxml-xml")
            entries = soup.find_all("entry")
            flood_related = []
            for entry in entries:
                title = entry.find("title")
                title_text = title.get_text(strip=True) if title else ""
                if any(kw in title_text for kw in ["洪水", "氾濫", "河川", "浸水", "水位"]):
                    link = entry.find("link")
                    flood_related.append({
                        "source": "JMA",
                        "title": title_text,
                        "link": link.get("href", "") if link else "",
                        "updated": entry.find("updated").get_text(strip=True) if entry.find("updated") else ""
                    })
            forecasts.extend(flood_related[:20])
            stats["jma_warnings"] = f"OK: {len(entries)} entries, {len(flood_related)} flood-related"
            print(f"    Entries: {len(entries)}, Flood-related: {len(flood_related)}")
        else:
            stats["jma_warnings"] = f"HTTP {resp.status_code}"
    except Exception as e:
        stats["jma_warnings"] = f"ERROR: {e}"
        print(f"    ERROR: {e}")

    # Also try JMA regular feed
    JMA_REG_URL = "https://www.data.jma.go.jp/developer/xml/feed/regular.xml"
    print(f"\n  Fetching JMA regular: {JMA_REG_URL}")
    try:
        resp = requests.get(JMA_REG_URL, headers=HEADERS, timeout=15)
        print(f"    HTTP {resp.status_code}, {len(resp.content)} bytes")
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, "lxml-xml")
            entries = soup.find_all("entry")
            river_entries = []
            for entry in entries:
                title = entry.find("title")
                title_text = title.get_text(strip=True) if title else ""
                if any(kw in title_text for kw in ["洪水", "氾濫", "河川", "水位", "指定河川"]):
                    link = entry.find("link")
                    river_entries.append({
                        "source": "JMA_regular",
                        "title": title_text,
                        "link": link.get("href", "") if link else "",
                        "updated": entry.find("updated").get_text(strip=True) if entry.find("updated") else ""
                    })
            forecasts.extend(river_entries[:20])
            print(f"    Entries: {len(entries)}, River-related: {len(river_entries)}")
    except Exception as e:
        print(f"    ERROR: {e}")

    # Save
    out_path = BASE / "river_forecast.json"
    ensure_dir(out_path.parent)
    result = {
        "metadata": {
            "collector": "river_flood",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "stats": stats,
            "endpoints_tried": [RIVER_URL] + ALT_URLS + [JMA_URL, JMA_REG_URL]
        },
        "forecasts": forecasts
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved {len(forecasts)} forecast items -> {out_path}")
    return stats


# ══════════════════════════════════════════════════════════════════════
# 1-4  Telegram Schema (design only)
# ══════════════════════════════════════════════════════════════════════

def create_telegram_schema() -> dict:
    print("\n" + "="*60)
    print("1-4. Telegram Schema Design")
    print("="*60)

    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Telegram Risk Alert Channel Schema",
        "description": (
            "Schema for ingesting risk-related messages from Telegram channels/groups. "
            "Designed for channels like disaster alerts, crime reports, and local safety groups in Japan. "
            "Requires a Telegram Bot Token to activate (not included)."
        ),
        "type": "object",
        "properties": {
            "channel_config": {
                "type": "object",
                "description": "Configuration for Telegram channel monitoring",
                "properties": {
                    "bot_token": {"type": "string", "description": "Telegram Bot API token (NOT stored, provided at runtime)"},
                    "channels": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "chat_id": {"type": ["string", "integer"], "description": "Telegram chat/channel ID"},
                                "name": {"type": "string"},
                                "category": {
                                    "type": "string",
                                    "enum": ["disaster_alert", "crime_report", "traffic_info", "weather", "local_safety", "general"]
                                },
                                "region": {"type": "string", "description": "Prefecture or region this channel covers"},
                                "language": {"type": "string", "default": "ja"}
                            },
                            "required": ["chat_id", "name", "category"]
                        }
                    },
                    "polling_interval_sec": {"type": "integer", "default": 60},
                    "max_messages_per_poll": {"type": "integer", "default": 100}
                }
            },
            "message_schema": {
                "type": "object",
                "description": "Normalized message format after ingestion",
                "properties": {
                    "message_id": {"type": "integer"},
                    "chat_id": {"type": ["string", "integer"]},
                    "channel_name": {"type": "string"},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "text": {"type": "string"},
                    "media_type": {
                        "type": "string",
                        "enum": ["none", "photo", "video", "document", "location"],
                        "default": "none"
                    },
                    "location": {
                        "type": "object",
                        "properties": {
                            "latitude": {"type": "number"},
                            "longitude": {"type": "number"}
                        }
                    },
                    "extracted_fields": {
                        "type": "object",
                        "description": "Fields extracted via NLP/keyword matching",
                        "properties": {
                            "risk_type": {"type": "string", "enum": ["crime", "disaster", "traffic", "weather", "animal_hazard", "other"]},
                            "subtype": {"type": "string", "description": "e.g. robbery, earthquake, flood"},
                            "severity": {"type": "integer", "minimum": 1, "maximum": 5},
                            "prefecture": {"type": "string"},
                            "address": {"type": "string"},
                            "keywords_matched": {"type": "array", "items": {"type": "string"}}
                        }
                    }
                },
                "required": ["message_id", "chat_id", "timestamp", "text"]
            },
            "api_endpoints": {
                "type": "object",
                "description": "Telegram Bot API endpoints used",
                "properties": {
                    "get_updates": {"const": "https://api.telegram.org/bot{token}/getUpdates"},
                    "get_chat": {"const": "https://api.telegram.org/bot{token}/getChat"},
                    "send_message": {"const": "https://api.telegram.org/bot{token}/sendMessage"}
                }
            },
            "suggested_channels": {
                "type": "array",
                "description": "Known Japanese Telegram channels for risk monitoring (to be populated)",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "url": {"type": "string"},
                        "category": {"type": "string"},
                        "notes": {"type": "string"}
                    }
                },
                "default": [
                    {"name": "TBD", "url": "TBD", "category": "disaster_alert", "notes": "Investigate Japanese disaster alert Telegram channels"}
                ]
            }
        },
        "implementation_notes": {
            "status": "schema_only",
            "requires": ["Telegram Bot Token", "Channel IDs to monitor"],
            "recommended_approach": "Use python-telegram-bot or telethon library",
            "integration": "Messages are normalized to Risk Space event schema after ingestion",
            "privacy": "Bot token must never be committed to repository"
        }
    }

    out_dir = BASE / "telegram"
    ensure_dir(out_dir)
    out_path = out_dir / "schema.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)
    print(f"  Saved schema -> {out_path}")
    return {"status": "created", "path": str(out_path)}


# ══════════════════════════════════════════════════════════════════════
# 1-5  Land Price Schema (design only)
# ══════════════════════════════════════════════════════════════════════

def create_land_price_schema() -> dict:
    print("\n" + "="*60)
    print("1-5. Land Price Schema Design")
    print("="*60)

    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Land Price Risk Indicator Schema",
        "description": (
            "Schema for integrating Japanese land price data as a risk/economic indicator. "
            "Primary source: MLIT (Ministry of Land, Infrastructure, Transport and Tourism) "
            "Land Price Public Announcement (地価公示) and Prefectural Land Price Survey (都道府県地価調査). "
            "API key required for real-time access via REINFOLIB API."
        ),
        "type": "object",
        "properties": {
            "data_sources": {
                "type": "object",
                "properties": {
                    "mlit_land_price_api": {
                        "type": "object",
                        "properties": {
                            "name": {"const": "国土交通省 不動産情報ライブラリ API"},
                            "base_url": {"const": "https://www.reinfolib.mlit.go.jp/ex-api/external"},
                            "endpoints": {
                                "type": "object",
                                "properties": {
                                    "land_price": {"const": "/XIT002?area={prefCode}&year={year}"},
                                    "transaction_price": {"const": "/XIT001?area={prefCode}&from={fromYear}&to={toYear}"},
                                    "appraisal": {"const": "/XIT003?area={prefCode}&year={year}"}
                                }
                            },
                            "auth": {"const": "Ocp-Apim-Subscription-Key header (requires registration)"},
                            "registration_url": {"const": "https://www.reinfolib.mlit.go.jp/ex-api/"},
                            "rate_limit": {"type": "string", "default": "unknown - check API docs"}
                        }
                    },
                    "open_data_csv": {
                        "type": "object",
                        "properties": {
                            "name": {"const": "国土数値情報 地価公示データ (CSV/GeoJSON)"},
                            "url": {"const": "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-L01-v3_0.html"},
                            "format": {"type": "string", "enum": ["CSV", "GeoJSON", "Shapefile"]},
                            "update_frequency": {"const": "annual (March)"},
                            "no_api_key_required": {"const": True}
                        }
                    }
                }
            },
            "record_schema": {
                "type": "object",
                "description": "Normalized land price record for risk integration",
                "properties": {
                    "point_id": {"type": "string", "description": "Standard land price point ID"},
                    "year": {"type": "integer"},
                    "prefecture": {"type": "string"},
                    "municipality": {"type": "string"},
                    "address": {"type": "string"},
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                    "land_use": {
                        "type": "string",
                        "enum": ["residential", "commercial", "industrial", "forest", "agricultural"]
                    },
                    "price_per_sqm": {"type": "integer", "description": "Yen per square meter"},
                    "yoy_change_pct": {"type": "number", "description": "Year-over-year change percentage"},
                    "risk_indicators": {
                        "type": "object",
                        "description": "Derived risk indicators from land price data",
                        "properties": {
                            "price_decline_flag": {"type": "boolean", "description": "True if price declining > 2% YoY"},
                            "anomaly_score": {"type": "number", "description": "Statistical anomaly score vs. regional average"},
                            "flood_zone_overlap": {"type": "boolean", "description": "Cross-referenced with flood hazard map"},
                            "crime_rate_correlation": {"type": "number", "description": "Correlation with local crime rate (-1 to 1)"},
                            "depopulation_risk": {"type": "boolean", "description": "Area identified as depopulation risk zone"}
                        }
                    }
                },
                "required": ["point_id", "year", "prefecture", "latitude", "longitude", "price_per_sqm"]
            },
            "integration_notes": {
                "risk_space_usage": [
                    "Land price decline as proxy for neighborhood deterioration risk",
                    "Cross-reference with crime hotspots - areas with rapid price decline may indicate safety concerns",
                    "Flood zone overlap: land price reflects long-term disaster risk perception",
                    "Depopulation areas: reduced surveillance, potentially higher crime risk"
                ],
                "update_strategy": "Annual bulk update (CSV) + quarterly API check for major cities",
                "spatial_join": "Use latitude/longitude to join with 500m mesh crime/disaster data"
            }
        },
        "implementation_notes": {
            "status": "schema_only",
            "requires": ["REINFOLIB API key for real-time access", "OR use open CSV data (no key needed)"],
            "priority": "medium - annual data, integrate after real-time sources are stable",
            "csv_fallback": "Download from https://nlftp.mlit.go.jp without API key"
        }
    }

    out_dir = BASE / "land_price"
    ensure_dir(out_dir)
    out_path = out_dir / "schema.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)
    print(f"  Saved schema -> {out_path}")
    return {"status": "created", "path": str(out_path)}


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("Risk Space MCP - Task 1: Collect New Data Sources")
    print(f"Started at: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    results = {}

    # 1-1
    results["nhk_rss"] = collect_nhk_rss()

    # 1-2
    results["yahoo_realtime"] = collect_yahoo_realtime()

    # 1-3
    results["river_flood"] = collect_river_flood()

    # 1-4
    results["telegram_schema"] = create_telegram_schema()

    # 1-5
    results["land_price_schema"] = create_land_price_schema()

    # ── Summary ──
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for task, res in results.items():
        print(f"\n  {task}:")
        if isinstance(res, dict):
            for k, v in res.items():
                print(f"    {k}: {v}")

    print(f"\nCompleted at: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
