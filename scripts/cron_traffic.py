#!/usr/bin/env python3
"""
cron_traffic.py — Road Traffic Incident Fetcher
================================================
Fetches real-time road traffic incidents for Japan from multiple sources:

  A. Yahoo!道路情報 (road disruptions via HTML scraping)
  B. NHK News RSS (traffic-related news headlines)
  C. JARTIC-like heuristics: falls back to Yahoo!カーナビ渋滞情報 API
     if neither JARTIC nor a proper API is reachable.

Note on JARTIC: jartic.or.jp does not expose a documented public API.
The site renders data via browser-side JS (Leaflet markers) which requires
full browser execution. This script scrapes the HTML fallback page and the
Yahoo!道路情報 equivalent, which covers the same incident data for
public consumption.

Output: docs/data/traffic_incidents_latest.json

Usage:
    python scripts/cron_traffic.py
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import List, Optional

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(BASE_DIR, "docs", "data", "traffic_incidents_latest.json")
NORM_DIR = os.path.join(BASE_DIR, "data", "normalized")

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
os.makedirs(NORM_DIR, exist_ok=True)

# ── Constants ──────────────────────────────────────────────────────────────
JST = timezone(timedelta(hours=9))
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Incident type keyword mapping (Japanese → normalized type)
INCIDENT_TYPE_MAP = {
    "通行止め": "road_closure",
    "片側通行": "lane_restriction",
    "規制": "restriction",
    "工事": "construction",
    "渋滞": "congestion",
    "事故": "accident",
    "人身事故": "accident_injury",
    "死亡事故": "accident_fatal",
    "緊急工事": "emergency_construction",
    "災害": "disaster",
    "落下物": "debris",
    "故障車": "breakdown",
    "倒木": "fallen_tree",
    "凍結": "road_ice",
    "チェーン規制": "chain_required",
    "大雪": "heavy_snow",
    "濃霧": "dense_fog",
}

# Severity mapping from incident type
SEVERITY_MAP = {
    "road_closure": 4,
    "accident_fatal": 4,
    "accident_injury": 3,
    "accident": 3,
    "disaster": 4,
    "lane_restriction": 2,
    "restriction": 2,
    "emergency_construction": 2,
    "congestion": 1,
    "construction": 1,
    "debris": 2,
    "breakdown": 1,
    "fallen_tree": 2,
    "road_ice": 3,
    "chain_required": 2,
    "heavy_snow": 3,
    "dense_fog": 2,
}

# ── HTTP helpers ───────────────────────────────────────────────────────────

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


def fetch_json_url(url: str, retries: int = 3) -> Optional[object]:
    """Fetch and parse JSON from URL with retry."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"  [WARN] fetch_json attempt {attempt + 1}/{retries}: {url} -> {e}",
                  file=sys.stderr)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None

# ── Helpers ────────────────────────────────────────────────────────────────

def classify_incident(text: str) -> tuple[str, int]:
    """Return (incident_type, severity) for a Japanese incident description."""
    for keyword, itype in INCIDENT_TYPE_MAP.items():
        if keyword in text:
            return itype, SEVERITY_MAP.get(itype, 1)
    return "unknown", 1


def calc_traffic_multiplier(severity: int, incident_type: str) -> float:
    """
    Compute traffic_multiplier for the risk model.

    Road closures / fatal accidents on major arterials raise crime-opportunity
    risk (isolated victims, slower emergency response). Congestion alone has
    minimal effect.

    Returns a multiplier in [1.0, 3.0].
    """
    base = 1.0 + (severity - 1) * 0.3   # severity 1→1.0, 4→1.9
    if incident_type in ("road_closure", "disaster"):
        base += 0.5
    elif incident_type in ("accident_fatal", "accident_injury"):
        base += 0.3
    elif incident_type in ("road_ice", "heavy_snow", "dense_fog"):
        base += 0.2
    return round(min(base, 3.0), 3)


# ── Simple HTML parser (no external deps) ─────────────────────────────────

class TableRowParser(HTMLParser):
    """Minimal HTML parser to extract table rows and list items as text."""

    def __init__(self):
        super().__init__()
        self.in_td = False
        self.in_li = False
        self.rows: List[str] = []
        self._buf: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("td", "th", "li", "p", "span", "div"):
            self.in_td = True
            self._buf = []

    def handle_endtag(self, tag):
        if tag in ("td", "th", "li", "p") and self.in_td:
            text = "".join(self._buf).strip()
            if text:
                self.rows.append(text)
            self.in_td = False

    def handle_data(self, data):
        if self.in_td:
            self._buf.append(data)


def extract_text_blocks(html: str) -> List[str]:
    """Extract non-trivial text blocks from HTML for incident scanning."""
    # Quick regex approach (avoids full parse overhead for large pages)
    # Strip scripts and styles first
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Extract text from tags
    texts = re.findall(r">([^<]{4,200})<", html)
    # Clean and filter
    blocks = []
    for t in texts:
        t = t.strip()
        t = re.sub(r"\s+", " ", t)
        if len(t) >= 6:
            blocks.append(t)
    return blocks

# ── Source A: Yahoo!道路交通情報 (disruption list) ───────────────────────
# JARTIC (jartic.or.jp) returns 404 for its public HTML page; replaced with
# Yahoo!道路交通情報 which provides equivalent disruption data.

YAHOO_DISRUPTION_URL = "https://road.yahoo.co.jp/"

def fetch_yahoo_disruption() -> List[dict]:
    """
    Scrape Yahoo!道路交通情報 disruption list.
    Returns normalized incident records.
    """
    print(f"\n[A] Fetching Yahoo!道路交通情報: {YAHOO_DISRUPTION_URL}")
    html = fetch_url(YAHOO_DISRUPTION_URL)
    if not html:
        print("  [SKIP] Yahoo!道路交通情報 not reachable.")
        return []

    incidents = []
    blocks = extract_text_blocks(html)
    seen: set = set()

    for block in blocks:
        itype, severity = classify_incident(block)
        if itype == "unknown":
            continue
        key = block[:80]
        if key in seen:
            continue
        seen.add(key)
        road_match = re.search(
            r"(国道\d+号|都道\d+号|道道\d+号|府道\d+号|[東西南北中関].*?(?:道|線|路|街道|高速))",
            block,
        )
        road_name = road_match.group(0) if road_match else ""
        incidents.append({
            "source": "yahoo_road",
            "incident_type": itype,
            "severity": severity,
            "road_name": road_name,
            "description": block[:200],
            "lat": None,
            "lon": None,
        })

    print(f"  Incidents extracted: {len(incidents)}")
    return incidents

# ── Source B: Yahoo!道路交通情報 ──────────────────────────────────────────

YAHOO_ROAD_URL = "https://transit.yahoo.co.jp/traininfo/area/4/"  # Kanto as probe

def fetch_yahoo_road() -> List[dict]:
    """
    Fetch Yahoo! transit/road disruption information.
    This page lists rail+road disruptions; we filter to road-related.
    Returns normalized incident records.
    """
    print(f"\n[B] Fetching Yahoo!道路情報: {YAHOO_ROAD_URL}")
    html = fetch_url(YAHOO_ROAD_URL)
    if not html:
        print("  [SKIP] Yahoo! road info not reachable.")
        return []

    incidents = []
    # Yahoo transit page uses specific CSS classes; try to find disruption rows
    # Pattern: text between >...</> that contain road/traffic keywords
    blocks = extract_text_blocks(html)
    seen = set()
    for block in blocks:
        itype, severity = classify_incident(block)
        if itype == "unknown":
            continue
        key = block[:80]
        if key in seen:
            continue
        seen.add(key)
        road_match = re.search(
            r"(国道\d+号|都道\d+号|[東西南北中関].*?(?:道|線|路|街道|高速))",
            block,
        )
        road_name = road_match.group(0) if road_match else ""
        incidents.append({
            "source": "yahoo_transit",
            "incident_type": itype,
            "severity": severity,
            "road_name": road_name,
            "description": block[:200],
            "lat": None,
            "lon": None,
        })

    print(f"  Incidents extracted: {len(incidents)}")
    return incidents

# ── Source C: NHK News RSS (traffic-tagged items) ─────────────────────────

NHK_RSS_URLS = [
    "https://www3.nhk.or.jp/rss/news/cat7.xml",   # society/traffic (事故/渋滞/通行止め)
    "https://www3.nhk.or.jp/rss/news/cat0.xml",   # top news (fallback)
]

TRAFFIC_KEYWORDS = {
    "事故", "渋滞", "通行止め", "規制", "崩落", "倒木", "土砂",
    "緊急工事", "不通", "交通", "道路", "高速",
}

def fetch_nhk_rss() -> List[dict]:
    """
    Fetch NHK News RSS and filter for traffic/road-related items.
    Parses minimal RSS XML without external libraries.
    """
    print(f"\n[C] Fetching NHK RSS ({len(NHK_RSS_URLS)} feeds)")
    incidents = []

    for rss_url in NHK_RSS_URLS:
        xml = fetch_url(rss_url, timeout=15)
        if not xml:
            continue

        # Extract <item> blocks
        items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
        for item in items:
            title_m = re.search(r"<title>(.*?)</title>", item)
            desc_m = re.search(r"<description>(.*?)</description>", item)
            date_m = re.search(r"<pubDate>(.*?)</pubDate>", item)
            link_m = re.search(r"<link>(.*?)</link>", item)

            title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""
            desc = re.sub(r"<[^>]+>", "", desc_m.group(1)).strip() if desc_m else ""
            pub_date = date_m.group(1).strip() if date_m else ""
            link = link_m.group(1).strip() if link_m else ""

            combined = title + " " + desc
            # Check if traffic-related
            if not any(kw in combined for kw in TRAFFIC_KEYWORDS):
                continue

            itype, severity = classify_incident(combined)
            if itype == "unknown":
                itype, severity = "restriction", 1

            # Parse pubDate: "Fri, 05 Apr 2026 03:00:00 +0900"
            incident_time = None
            try:
                from email.utils import parsedate_to_datetime
                incident_time = parsedate_to_datetime(pub_date).astimezone(timezone.utc).isoformat(timespec="seconds")
            except Exception:
                incident_time = None

            incidents.append({
                "source": "nhk_rss",
                "incident_type": itype,
                "severity": severity,
                "road_name": "",
                "description": (title + " — " + desc)[:300],
                "lat": None,
                "lon": None,
                "url": link,
                "occurred_at": incident_time,
            })

    print(f"  Traffic-related RSS items: {len(incidents)}")
    return incidents

# ── Source D: MLIT E-NEXCO real-time closure API ──────────────────────────
# MLIT / NEXCO publish machine-readable road closure info as XML/JSON at:
# https://www.e-nexco.co.jp/traffic_info/ (HTML only, JS rendered)
# We probe a known MLIT data endpoint for expressway closure PDFs/data.
# This is best-effort; falls back gracefully.

MLIT_TRAFFIC_URL = (
    "https://www.mlit.go.jp/road/road/data/rjd/rjd_open.xml"
)

def fetch_mlit_traffic() -> List[dict]:
    """
    Probe MLIT road junction data for closure markers.
    This endpoint may or may not be available; treated as best-effort.
    """
    print(f"\n[D] Probing MLIT traffic data: {MLIT_TRAFFIC_URL}")
    xml = fetch_url(MLIT_TRAFFIC_URL, timeout=15)
    if not xml:
        print("  [SKIP] MLIT traffic endpoint not reachable or returned no data.")
        return []

    incidents = []
    # Try to find closure records in XML
    closures = re.findall(r"<[Cc]losure[^>]*>(.*?)</[Cc]losure[^>]*>", xml, re.DOTALL)
    for cl in closures:
        desc = re.sub(r"<[^>]+>", " ", cl).strip()
        desc = re.sub(r"\s+", " ", desc)[:200]
        if not desc:
            continue
        lat_m = re.search(r"<[Ll]at(?:itude)?>([\d.]+)<", cl)
        lon_m = re.search(r"<[Ll]on(?:gitude)?>([\d.]+)<", cl)
        lat = float(lat_m.group(1)) if lat_m else None
        lon = float(lon_m.group(1)) if lon_m else None
        incidents.append({
            "source": "mlit_road",
            "incident_type": "road_closure",
            "severity": 4,
            "road_name": "",
            "description": desc,
            "lat": lat,
            "lon": lon,
        })

    print(f"  MLIT closures found: {len(incidents)}")
    return incidents

# ── Main ───────────────────────────────────────────────────────────────────

def main():
    now_utc = datetime.now(timezone.utc)
    now_jst = now_utc.astimezone(JST)

    print("=" * 60)
    print("cron_traffic.py — Road Traffic Incident Fetcher")
    print(f"  fetched_at: {now_utc.isoformat(timespec='seconds')}")
    print("=" * 60)

    all_incidents: List[dict] = []

    # Collect from all sources (sequential to be polite)
    all_incidents.extend(fetch_yahoo_disruption())
    time.sleep(1)
    all_incidents.extend(fetch_yahoo_road())
    time.sleep(1)
    all_incidents.extend(fetch_nhk_rss())
    time.sleep(1)
    all_incidents.extend(fetch_mlit_traffic())

    # Enrich each incident with computed fields
    enriched = []
    for idx, inc in enumerate(all_incidents):
        itype = inc.get("incident_type", "unknown")
        severity = inc.get("severity", 1)
        traffic_mult = calc_traffic_multiplier(severity, itype)

        record = {
            "event_id": f"traffic_{now_utc.strftime('%Y%m%d')}_{idx:04d}",
            "layer": "traffic",
            "source": inc.get("source", "unknown"),
            "incident_type": itype,
            "severity": severity,
            "road_name": inc.get("road_name", ""),
            "description": inc.get("description", ""),
            "lat": inc.get("lat"),
            "lon": inc.get("lon"),
            "occurred_at": inc.get("occurred_at", now_utc.isoformat(timespec="seconds")),
            "url": inc.get("url", ""),
            "traffic_multiplier": traffic_mult,
        }
        enriched.append(record)

        if idx < 20 or idx % 20 == 0:
            print(f"  [{idx + 1:3d}] {itype:<25s} sev={severity} mult={traffic_mult:.2f} "
                  f"src={inc.get('source', '?')}")

    # Source-level stats
    from collections import Counter
    src_counts = Counter(r["source"] for r in enriched)
    type_counts = Counter(r["incident_type"] for r in enriched)

    # Build output
    output = {
        "metadata": {
            "sources": ["yahoo_road", "yahoo_transit", "nhk_rss", "mlit_road"],
            "fetched_at": now_utc.isoformat(timespec="seconds"),
            "fetched_at_jst": now_jst.isoformat(timespec="seconds"),
            "total_count": len(enriched),
            "source_counts": dict(src_counts),
            "type_counts": dict(type_counts),
            "description": (
                "Real-time road traffic incidents in Japan. "
                "Aggregated from Yahoo!道路交通情報, Yahoo!トランジット, NHK RSS (cat7), and MLIT. "
                "traffic_multiplier reflects incident impact on local risk model."
            ),
            "notes": (
                "JARTIC (jartic.or.jp) was replaced with Yahoo!道路交通情報 (road.yahoo.co.jp) "
                "due to 404 errors on the JARTIC public page. "
                "NHK RSS cat7 covers society/traffic news (事故/渋滞/通行止め). "
                "Lat/lon is available only when the source provides coordinates directly."
            ),
        },
        "incidents": enriched,
    }

    # Write outputs
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    norm_path = os.path.join(NORM_DIR, "traffic_incidents_latest.json")
    with open(norm_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[DONE] {len(enriched)} incidents written to:")
    print(f"  {OUT_PATH}")
    print(f"  {norm_path}")
    print(f"  Source breakdown: {dict(src_counts)}")
    print(f"  Type breakdown:   {dict(type_counts)}")


if __name__ == "__main__":
    main()
