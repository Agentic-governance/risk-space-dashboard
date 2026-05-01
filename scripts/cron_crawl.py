#!/usr/bin/env python3
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import json
import hashlib
import time
import re
import os
from datetime import datetime
from collections import Counter
from bs4 import BeautifulSoup
import chardet

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RiskSpaceMCP/1.0)"}
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "docs", "data")

REALTIME_PATH = os.path.join(DATA_DIR, "realtime_slim.json")
SUMMARY_PATH = os.path.join(DATA_DIR, "summary.json")
SEEN_HASHES_PATH = os.path.join(DATA_DIR, "seen_hashes.json")
CITY_CENTROIDS_PATH = os.path.join(DATA_DIR, "city_centroids.json")
PREF_CENTROIDS_PATH = os.path.join(DATA_DIR, "pref_centroids.json")

PREFECTURES = {
    1: "北海道", 2: "青森県", 3: "岩手県", 4: "宮城県", 5: "秋田県", 6: "山形県", 7: "福島県",
    8: "茨城県", 9: "栃木県", 10: "群馬県", 11: "埼玉県", 12: "千葉県", 13: "東京都", 14: "神奈川県",
    15: "新潟県", 16: "富山県", 17: "石川県", 18: "福井県", 19: "山梨県", 20: "長野県", 21: "岐阜県",
    22: "静岡県", 23: "愛知県", 24: "三重県", 25: "滋賀県", 26: "京都府", 27: "大阪府", 28: "兵庫県",
    29: "奈良県", 30: "和歌山県", 31: "鳥取県", 32: "島根県", 33: "岡山県", 34: "広島県", 35: "山口県",
    36: "徳島県", 37: "香川県", 38: "愛媛県", 39: "高知県", 40: "福岡県", 41: "佐賀県", 42: "長崎県",
    43: "熊本県", 44: "大分県", 45: "宮崎県", 46: "鹿児島県", 47: "沖縄県",
}

SUBTYPE_CONFIG = {
    "不審者": {"subtype_ja": "不審者", "severity": 2},
    "声かけ": {"subtype_ja": "声かけ", "severity": 2},
    "ちかん": {"subtype_ja": "痴漢", "severity": 4},
    "痴漢": {"subtype_ja": "痴漢", "severity": 4},
    "のぞき": {"subtype_ja": "のぞき", "severity": 3},
    "盗撮": {"subtype_ja": "盗撮", "severity": 3},
    "暴行・暴力": {"subtype_ja": "暴行", "severity": 4},
    "暴行": {"subtype_ja": "暴行", "severity": 4},
    "凶器・武器": {"subtype_ja": "凶器", "severity": 4},
    "凶器": {"subtype_ja": "凶器", "severity": 4},
    "強盗・脅迫": {"subtype_ja": "強盗", "severity": 5},
    "強盗": {"subtype_ja": "強盗", "severity": 5},
    "住居侵入": {"subtype_ja": "侵入", "severity": 3},
    "侵入": {"subtype_ja": "侵入", "severity": 3},
    "子ども被害": {"subtype_ja": "子供被害", "severity": 3},
    "子供被害": {"subtype_ja": "子供被害", "severity": 3},
    "迷惑行為": {"subtype_ja": "迷惑行為", "severity": 2},
}


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] failed to load {path}: {e}")
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
    except Exception as e:
        print(f"[ERROR] failed to save {path}: {e}")


def fetch_html(url, retries=2):
    for attempt in range(retries + 1):
        try:
            res = requests.get(url, headers=HEADERS, timeout=(5, 20), verify=False)
            res.raise_for_status()
            enc = chardet.detect(res.content).get("encoding")
            if enc:
                res.encoding = enc
            return res.text
        except Exception as e:
            print(f"[ERROR] fetch failed (attempt {attempt+1}/{retries+1}): {url} -> {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)
    return ""


def normalize_space(s):
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def split_pref_city(location_text, fallback_pref):
    m = re.match(r"^(北海道|東京都|大阪府|京都府|.{2,3}県)(.*)$", location_text or "")
    if m:
        pref = m.group(1)
        city = normalize_space(m.group(2))
        return pref, city
    return fallback_pref, normalize_space(location_text or "")


def _as_latlon_pair(value):
    if isinstance(value, dict):
        lat = value.get("lat")
        lon = value.get("lon")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return float(lat), float(lon)
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        if isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
            return float(value[0]), float(value[1])
    return None


def lookup_centroid(pref, city, city_centroids, pref_centroids):
    city_key_1 = f"{pref}{city}"
    city_key_2 = f"{pref}_{city}"

    for key in (city_key_1, city_key_2, city):
        if key in city_centroids:
            pair = _as_latlon_pair(city_centroids[key])
            if pair:
                return pair

    if pref in pref_centroids:
        pair = _as_latlon_pair(pref_centroids[pref])
        if pair:
            return pair

    return None, None


def extract_incidents(pref_name, html):
    soup = BeautifulSoup(html, "html.parser")
    incidents = []

    container_candidates = soup.select("li.mdl-list__item")
    if not container_candidates:
        container_candidates = soup.select("li")

    for li in container_candidates:
        title_el = li.select_one("h5.info_title") or li.find("h5")
        desc_el = li.select_one("p.info_description") or li.find("p", class_=re.compile(r"description", re.I))
        date_el = li.select_one("p.info_date")
        place_el = li.select_one("p.info-place") or li.select_one("p.info_place")

        title = normalize_space(title_el.get_text(" ", strip=True)) if title_el else ""
        desc = normalize_space(desc_el.get_text(" ", strip=True)) if desc_el else ""
        date_text = normalize_space(date_el.get_text(" ", strip=True)) if date_el else ""
        place = normalize_space(place_el.get_text(" ", strip=True)) if place_el else ""

        if not (title or desc):
            continue

        kind_name = ""
        img = li.find("img")
        if img and img.get("src"):
            src = img.get("src")
            if "suspicious" in src:
                kind_name = "不審者"
            elif "talk" in src:
                kind_name = "声かけ"
            elif "molester" in src:
                kind_name = "痴漢"
            elif "peeping" in src:
                kind_name = "のぞき"
            elif "photo" in src:
                kind_name = "盗撮"
            elif "assault" in src:
                kind_name = "暴行"
            elif "knife" in src:
                kind_name = "凶器"
            elif "robbery" in src:
                kind_name = "強盗"
            elif "burglar" in src:
                kind_name = "侵入"
            elif "children" in src:
                kind_name = "子供被害"
            elif "nuisance" in src:
                kind_name = "迷惑行為"

        if not kind_name:
            combined = f"{title} {desc}"
            for k in SUBTYPE_CONFIG.keys():
                if k in combined:
                    kind_name = k
                    break

        if not kind_name:
            kind_name = "不審者"

        prefecture, city = split_pref_city(place, pref_name)

        incidents.append(
            {
                "date": date_text,
                "prefecture": prefecture,
                "city": city,
                "location": place,
                "kind_name": kind_name,
                "title": title,
                "description": desc,
            }
        )

    return incidents


def to_event_row(incident, city_centroids, pref_centroids):
    cfg = SUBTYPE_CONFIG.get(incident["kind_name"], {"subtype_ja": incident["kind_name"], "severity": 2})
    subtype = cfg["subtype_ja"]
    severity = int(cfg["severity"])

    lat, lon = lookup_centroid(incident["prefecture"], incident["city"], city_centroids, pref_centroids)
    if lat is None or lon is None:
        return None

    date = incident["date"] or datetime.now().strftime("%Y年%m月%d")
    return [round(float(lat), 4), round(float(lon), 4), subtype, severity, date]


def make_hash(incident):
    raw = "|".join(
        [
            incident.get("date", ""),
            incident.get("prefecture", ""),
            incident.get("city", ""),
            incident.get("location", ""),
            incident.get("kind_name", ""),
            incident.get("title", ""),
            incident.get("description", ""),
        ]
    )
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    city_centroids = load_json(CITY_CENTROIDS_PATH, {})
    pref_centroids = load_json(PREF_CENTROIDS_PATH, {})
    seen_hashes = set(load_json(SEEN_HASHES_PATH, []))
    existing_rows = load_json(REALTIME_PATH, [])

    # Guard: don't overwrite non-empty data with empty
    if not existing_rows and os.path.exists(REALTIME_PATH) and os.path.getsize(REALTIME_PATH) > 10:
        print("[WARN] existing data loaded as empty but file is non-empty - aborting to prevent data loss")
        return

    print(f"[INFO] loaded existing rows: {len(existing_rows)}")
    print(f"[INFO] loaded seen hashes: {len(seen_hashes)}")
    print(f"[INFO] city centroids: {len(city_centroids)}, pref centroids: {len(pref_centroids)}")

    new_rows = []
    kind_counter = Counter()
    skipped_no_geo = 0

    for pref_id in range(1, 48):
        pref_name = PREFECTURES[pref_id]
        added_this_pref = 0

        for page in range(1, 4):  # pages 1-3
            url = f"https://www.gaccom.jp/safety/search?prefecture_id={pref_id}&page={page}&k=8191"
            if page == 1:
                print(f"[CRAWL] {pref_id:02d}/47 {pref_name}: {url}")

            html = fetch_html(url)
            if not html:
                break

            incidents = extract_incidents(pref_name, html)
            if not incidents:
                break  # No more results

            for inc in incidents:
                digest = make_hash(inc)
                if digest in seen_hashes:
                    continue

                row = to_event_row(inc, city_centroids, pref_centroids)
                if row is None:
                    skipped_no_geo += 1
                    continue

                seen_hashes.add(digest)
                new_rows.append(row)
                kind_counter[row[2]] += 1
                added_this_pref += 1

            time.sleep(1.5)

        print(f"[MERGE] {pref_name}: new_rows={added_this_pref}")

    merged = list(existing_rows) + new_rows
    save_json(REALTIME_PATH, merged)
    # Cap seen_hashes to prevent unbounded growth
    if len(seen_hashes) > 50000:
        seen_hashes = set(sorted(seen_hashes)[-50000:])
        print(f"[WARN] trimmed seen_hashes to 50000 entries")
    save_json(SEEN_HASHES_PATH, sorted(seen_hashes))

    summary = load_json(SUMMARY_PATH, {})
    summary["generated_at"] = datetime.now().isoformat(timespec="seconds")
    summary["total_rows"] = len(merged)
    summary["new_rows_this_run"] = len(new_rows)
    summary["seen_hashes_count"] = len(seen_hashes)
    summary["by_subtype"] = dict(kind_counter)
    summary["skipped_no_geo"] = skipped_no_geo
    save_json(SUMMARY_PATH, summary)

    print(f"[DONE] appended rows: {len(new_rows)}")
    print(f"[DONE] merged rows: {len(merged)}")
    print(f"[DONE] skipped (no geo): {skipped_no_geo}")
    print(f"[DONE] by subtype: {dict(kind_counter)}")


if __name__ == "__main__":
    main()
