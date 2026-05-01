#!/usr/bin/env python3
"""Geocode all realtime events and create dashboard/data/realtime_markers.json"""
import json, time, re, os, urllib.request, urllib.parse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Load centroid caches
pref_centroids = {}
for p in load_json(os.path.join(BASE, 'data/crime/national/pref_centroids.json')):
    name = p['prefecture']
    pref_centroids[name] = (p['lat'], p['lon'])
    # Also store without suffix
    for suffix in ['県', '都', '府']:
        if name.endswith(suffix):
            pref_centroids[name[:-1]] = (p['lat'], p['lon'])

city_centroids = {}
try:
    raw = load_json(os.path.join(BASE, 'data/crime/national/city_centroids.json'))
    if isinstance(raw, dict):
        for key, val in raw.items():
            if isinstance(val, dict) and 'lat' in val:
                city_centroids[key] = (val['lat'], val['lon'])
            elif isinstance(val, list) and len(val) >= 2:
                city_centroids[key] = (val[0], val[1])
    elif isinstance(raw, list):
        for item in raw:
            if 'city' in item and 'lat' in item:
                city_centroids[item['city']] = (item['lat'], item['lon'])
            if 'prefecture' in item and 'city' in item and 'lat' in item:
                key = item['prefecture'] + item['city']
                city_centroids[key] = (item['lat'], item['lon'])
except Exception as e:
    print(f"Warning: city_centroids load issue: {e}")

# GSI geocoder
geocode_cache = {}
def geocode_gsi(address_text):
    """Try GSI address search API"""
    if not address_text or len(address_text) < 3:
        return None
    # Clean address text - extract actual address part
    # Remove common prefixes
    addr = address_text
    for prefix in ['によると、', '県警によると、', '市によると、']:
        if prefix in addr:
            addr = addr.split(prefix)[-1]
    # Extract address-like portion (Japanese address pattern)
    m = re.search(r'([^\s,、。]{2,}[都道府県][^\s,、。]*[市区町村郡][^\s,、。]*)', addr)
    if m:
        addr = m.group(1)
    else:
        # Try to find city+district pattern
        m = re.search(r'([^\s,、。]{2,}[市区町村][^\s,、。]{0,20})', addr)
        if m:
            addr = m.group(1)
        else:
            return None
    # Trim to reasonable length
    addr = addr[:40]
    if addr in geocode_cache:
        return geocode_cache[addr]
    try:
        url = f"https://msearch.gsi.go.jp/address-search/AddressSearch?q={urllib.parse.quote(addr)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'RiskSpaceMCP/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data and len(data) > 0:
                coords = data[0].get('geometry', {}).get('coordinates', [])
                if len(coords) >= 2:
                    result = (coords[1], coords[0])  # lat, lon
                    geocode_cache[addr] = result
                    return result
    except Exception as e:
        pass
    geocode_cache[addr] = None
    return None

def find_prefecture_in_text(text):
    """Extract prefecture name from text"""
    prefs = ['北海道','青森県','岩手県','宮城県','秋田県','山形県','福島県',
             '茨城県','栃木県','群馬県','埼玉県','千葉県','東京都','神奈川県',
             '新潟県','富山県','石川県','福井県','山梨県','長野県','岐阜県',
             '静岡県','愛知県','三重県','滋賀県','京都府','大阪府','兵庫県',
             '奈良県','和歌山県','鳥取県','島根県','岡山県','広島県','山口県',
             '徳島県','香川県','愛媛県','高知県','福岡県','佐賀県','長崎県',
             '熊本県','大分県','宮崎県','鹿児島県','沖縄県']
    for p in prefs:
        if p in (text or ''):
            return p
    # Check without suffix
    short_map = {'東京':'東京都','大阪':'大阪府','京都':'京都府','北海道':'北海道'}
    for s, full in short_map.items():
        if s in (text or ''):
            return full
    return None

def find_city_in_title(title):
    """Extract city from title like （兵庫）尼崎市..."""
    m = re.search(r'[）\)]([^\s（）()]+?[市区町村郡])', title or '')
    if m:
        return m.group(1)
    m = re.search(r'([^\s（）()]+?[市区町村郡])', title or '')
    if m:
        return m.group(1)
    return None

def geocode_event(event):
    """Try to geocode an event, return (lat, lon) or None"""
    pref = event.get('prefecture')
    city = event.get('city')
    address = event.get('address')
    title = event.get('title', '')
    text = event.get('text', '')
    desc = event.get('description', '')

    # 1. Try GSI geocode with address text
    addr_text = address or desc or title or text
    if addr_text and len(addr_text) > 5:
        result = geocode_gsi(addr_text)
        if result:
            return result, 'gsi'
        time.sleep(0.5)

    # 2. Try city centroids
    if pref and city:
        key = pref + city
        if key in city_centroids:
            return city_centroids[key], 'city_centroid'
        if city in city_centroids:
            return city_centroids[city], 'city_centroid'

    # 3. Try to extract city from title
    if not city and title:
        city = find_city_in_title(title)
        if city:
            if pref:
                key = pref + city
                if key in city_centroids:
                    return city_centroids[key], 'city_centroid'
            if city in city_centroids:
                return city_centroids[city], 'city_centroid'

    # 4. Try prefecture centroids
    if not pref:
        pref = find_prefecture_in_text(title or text or desc)
    if pref:
        if pref in pref_centroids:
            return pref_centroids[pref], 'pref_centroid'

    return None, None

# Collect all events
markers = []
stats = {'total': 0, 'geocoded_gsi': 0, 'geocoded_city': 0, 'geocoded_pref': 0, 'skipped': 0}

# 1. fushinsha_live events
print("Loading fushinsha_live events...")
live_data = load_json(os.path.join(BASE, 'data/realtime/fushinsha_live/events_20260403_0836.json'))
live_events = live_data.get('events', [])
print(f"  {len(live_events)} events")

for ev in live_events:
    stats['total'] += 1
    pref = ev.get('prefecture')
    city = ev.get('city')
    title = ev.get('title', '')

    # Skip the first event which is just the JASPIC header
    if not pref and not city and '日本不審者情報センター' in title:
        stats['skipped'] += 1
        continue

    coords, method = geocode_event(ev)
    if coords:
        if method == 'gsi': stats['geocoded_gsi'] += 1
        elif method == 'city_centroid': stats['geocoded_city'] += 1
        elif method == 'pref_centroid': stats['geocoded_pref'] += 1
        markers.append({
            'lat': round(coords[0], 5),
            'lon': round(coords[1], 5),
            'type': 'fushinsha',
            'subtype': ev.get('subtype', 'suspicious_person'),
            'severity': ev.get('severity', 2),
            'title': title,
            'date': ev.get('event_date'),
            'source': 'JASPIC',
            'geocode_method': method
        })
    else:
        stats['skipped'] += 1
        if pref or city:
            print(f"  MISSED: {title[:40]}... (pref={pref}, city={city})")

# 2. all_fushinsha
print("\nLoading all_fushinsha events...")
fushinsha_all = load_json(os.path.join(BASE, 'data/realtime/fushinsha/all_fushinsha.json'))
print(f"  {len(fushinsha_all)} events")

for ev in fushinsha_all:
    stats['total'] += 1
    text = ev.get('text', '')
    address = ev.get('address')

    # Skip navigation/menu junk entries
    if not address and (not text or len(text) < 20 or
        'メニュー' in text or '事件種別' in text or '不審者の特徴' in text or
        'すべて選択' in text or '都道府県から探す' in text or
        '安全ナビ' in text[:20] or 'ガッコム安全ナビとは' in text or
        '条件で探す' in text or 'セリフ集' in text or
        '全国共通形式' in text or 'LINE公式' in text or
        '詳細をみる' in text or '特徴種別' in text or
        '事件種別から探す' in text[:20]):
        stats['skipped'] += 1
        continue

    coords, method = geocode_event(ev)
    if coords:
        if method == 'gsi': stats['geocoded_gsi'] += 1
        elif method == 'city_centroid': stats['geocoded_city'] += 1
        elif method == 'pref_centroid': stats['geocoded_pref'] += 1
        markers.append({
            'lat': round(coords[0], 5),
            'lon': round(coords[1], 5),
            'type': 'fushinsha',
            'subtype': ev.get('subtype', 'suspicious_person'),
            'severity': ev.get('severity', 2),
            'title': (text[:50] + '...' if len(text) > 50 else text) if text else 'N/A',
            'date': ev.get('date'),
            'source': ev.get('source', 'unknown'),
            'geocode_method': method
        })
    else:
        stats['skipped'] += 1

# 3. NHK events
print("\nLoading NHK events...")
nhk_data = load_json(os.path.join(BASE, 'data/realtime/news/nhk_events.json'))
nhk_events = nhk_data.get('events', []) if isinstance(nhk_data, dict) else nhk_data
print(f"  {len(nhk_events)} events")

for ev in nhk_events:
    stats['total'] += 1
    pref = ev.get('prefecture')
    title = ev.get('title', '')

    # Parse date from published field
    pub = ev.get('published', '')
    date_str = None
    if pub:
        m = re.search(r'(\d{1,2}) (\w{3}) (\d{4})', pub)
        if m:
            months = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06',
                      'Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
            date_str = f"{m.group(3)}-{months.get(m.group(2),'01')}-{m.group(1).zfill(2)}"

    coords, method = geocode_event(ev)
    if coords:
        if method == 'gsi': stats['geocoded_gsi'] += 1
        elif method == 'city_centroid': stats['geocoded_city'] += 1
        elif method == 'pref_centroid': stats['geocoded_pref'] += 1
        markers.append({
            'lat': round(coords[0], 5),
            'lon': round(coords[1], 5),
            'type': 'news',
            'subtype': ev.get('subtype', 'crime'),
            'severity': ev.get('severity', 3),
            'title': title,
            'date': date_str,
            'source': ev.get('source', 'NHK'),
            'geocode_method': method
        })
    else:
        stats['skipped'] += 1
        if pref:
            print(f"  MISSED NHK: {title[:40]}... (pref={pref})")

# 4. Crime news
print("\nLoading crime_news events...")
crime_news = load_json(os.path.join(BASE, 'data/realtime/news/crime_news.json'))
print(f"  {len(crime_news)} events")

for ev in crime_news:
    stats['total'] += 1
    title = ev.get('title', '')
    body = ev.get('body_excerpt', '')

    # Skip generic category pages
    if not title or '許すな' in title[:10]:
        stats['skipped'] += 1
        continue

    # Try to extract location from title
    pref_from_title = find_prefecture_in_text(title + ' ' + body[:200])

    coords, method = geocode_event({
        'prefecture': pref_from_title,
        'city': find_city_in_title(title),
        'address': ev.get('address'),
        'title': title,
        'description': body[:300] if body else '',
    })
    if coords:
        if method == 'gsi': stats['geocoded_gsi'] += 1
        elif method == 'city_centroid': stats['geocoded_city'] += 1
        elif method == 'pref_centroid': stats['geocoded_pref'] += 1
        markers.append({
            'lat': round(coords[0], 5),
            'lon': round(coords[1], 5),
            'type': 'crime_report',
            'subtype': ev.get('subtype', 'crime_other'),
            'severity': ev.get('severity', 3) if ev.get('severity') else 3,
            'title': title,
            'date': ev.get('date'),
            'source': ev.get('source', 'news'),
            'geocode_method': method
        })
    else:
        stats['skipped'] += 1

# Deduplicate by approximate location + title
seen = set()
deduped = []
for m in markers:
    key = (round(m['lat'], 3), round(m['lon'], 3), m['title'][:30])
    if key not in seen:
        seen.add(key)
        deduped.append(m)
markers = deduped

# Save
out1 = os.path.join(BASE, 'dashboard/data/realtime_markers.json')
out2 = os.path.join(BASE, 'docs/data/realtime_markers.json')
save_json(out1, markers)
save_json(out2, markers)

print(f"\n=== GEOCODING SUMMARY ===")
print(f"Total events processed: {stats['total']}")
print(f"Geocoded via GSI API:   {stats['geocoded_gsi']}")
print(f"Geocoded via city centroid: {stats['geocoded_city']}")
print(f"Geocoded via pref centroid: {stats['geocoded_pref']}")
print(f"Total geocoded:         {stats['geocoded_gsi'] + stats['geocoded_city'] + stats['geocoded_pref']}")
print(f"Skipped (no location):  {stats['skipped']}")
print(f"Output markers:         {len(markers)} (after dedup)")
print(f"Saved to: {out1}")
print(f"Saved to: {out2}")
