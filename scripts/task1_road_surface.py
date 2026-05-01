import requests, json, time, math
from pathlib import Path

Path('data/road/anomaly').mkdir(parents=True, exist_ok=True)
headers = {'User-Agent': 'Mozilla/5.0 (compatible; RiskSpaceMCP/1.0)'}

# A. 自治体オープンデータ（道路損傷情報）
PREF_ROAD_DATA = [
    {'pref': '東京都', 'url': 'https://catalog.data.metro.tokyo.lg.jp/api/3/action/package_search?q=道路損傷&rows=20', 'type': 'ckan_api'},
    {'pref': '大阪府', 'url': 'https://odcs.bodik.jp/api/3/action/package_search?q=道路&rows=20', 'type': 'ckan_api'},
]
for source in PREF_ROAD_DATA:
    try:
        r = requests.get(source['url'], headers=headers, timeout=15)
        data = r.json()
        pkgs = data.get('result',{}).get('results',[]) if source['type']=='ckan_api' else []
        print(f"{source['pref']}: {len(pkgs)}件のデータセット")
        for pkg in pkgs[:5]:
            print(f"  - {pkg.get('title','')[:50]}")
            for res in pkg.get('resources',[]):
                url = res.get('url','')
                if url.endswith('.csv') or url.endswith('.geojson'):
                    try:
                        resp = requests.get(url, headers=headers, timeout=20)
                        fname = f"data/road/anomaly/{source['pref']}_{pkg['id'][:8]}.csv"
                        with open(fname,'wb') as f: f.write(resp.content)
                        print(f"    取得: {url.split('/')[-1]}")
                        time.sleep(1)
                    except: pass
        time.sleep(2)
    except Exception as e: print(f"{source['pref']}: {e}")

# B. OSMから道路インフラ危険情報
print('\nOSMから道路インフラ情報取得中...')
try:
    import overpy
    api = overpy.Overpass()
    result = api.query('''
    [out:json][timeout:120];
    (
      way["highway"]["surface"="unpaved"](35.5,138.9,35.9,139.9);
      way["highway"]["surface"="compacted"](35.5,138.9,35.9,139.9);
      node["barrier"="kerb"]["kerb"="raised"](35.5,138.9,35.9,139.9);
      way["highway"]["sidewalk"="no"](35.5,138.9,35.9,139.9);
    );
    out center;
    ''')
    hazards = []
    for way in result.ways:
        if hasattr(way,'center_lat') and way.center_lat:
            hazards.append({'lat':float(way.center_lat),'lon':float(way.center_lon),'type':'road_surface','surface':way.tags.get('surface',''),'highway':way.tags.get('highway',''),'source':'OSM'})
    for node in result.nodes:
        hazards.append({'lat':float(node.lat),'lon':float(node.lon),'type':'kerb_raised','source':'OSM'})
    print(f'OSM道路危険箇所: {len(hazards)}件')
    with open('data/road/anomaly/osm_road_hazards.json','w',encoding='utf-8') as f:
        json.dump(hazards,f,ensure_ascii=False)
except Exception as e: print(f'OSM取得: {e}')

# C. 路面状態推定関数
def estimate_road_surface(weather_type, temp_c, precip_1h_mm=0, precip_24h_mm=0, hours_since_rain=0):
    if weather_type in ['snow'] or precip_24h_mm > 5 and temp_c <= 2:
        if temp_c <= 0: surface,hazard = 'frozen',0.95
        else: surface,hazard = 'snow_covered',0.85
    elif temp_c <= 0 and hours_since_rain <= 6:
        surface,hazard = 'frozen',0.90
    elif weather_type in ['rain'] or precip_1h_mm >= 1:
        surface,hazard = 'wet',0.55
    elif hours_since_rain <= 2:
        surface,hazard = 'wet',0.45
    else:
        surface,hazard = 'dry',0.10
    CHILD_LIFT = {'frozen':30.0,'snow_covered':20.0,'wet':8.0,'dry':1.0}
    child_lift = CHILD_LIFT.get(surface,1.0)
    reason = '通常路面'
    if weather_type == 'cloudy' and surface == 'wet':
        child_lift = max(child_lift, 25.0)
        reason = '曇×路面湿潤：最も見落とされるリスク組み合わせ'
    elif surface == 'frozen': reason = '路面凍結：転倒・車両スリップ多発'
    elif surface == 'wet': reason = '路面湿潤：制動距離延長'
    return {'road_surface':surface,'hazard_score':round(hazard,3),'child_risk_lift':round(child_lift,1),'confidence':0.75,'reason':reason}

print('\n=== 路面状態推定テスト ===')
tests = [
    ('cloudy',8,0,2,3,'曇・8℃・2時間前に雨'),
    ('rain',12,5,10,0,'雨・12℃'),
    ('sunny',-1,0,8,12,'晴れ・-1℃・昨日雨'),
    ('snow',-3,2,20,0,'雪・-3℃'),
    ('sunny',20,0,0,72,'晴れ・20℃・乾燥'),
]
for w,t,p1,p24,sr,label in tests:
    r = estimate_road_surface(w,t,p1,p24,sr)
    print(f'  {label}')
    print(f'    路面:{r["road_surface"]} 危険度:{r["hazard_score"]} 子供リスク:x{r["child_risk_lift"]} {r["reason"]}')

# 関数を保存
code = '''import json
from pathlib import Path

def estimate_road_surface(weather_type, temp_c, precip_1h_mm=0, precip_24h_mm=0, hours_since_rain=0):
    if weather_type in ["snow"] or precip_24h_mm > 5 and temp_c <= 2:
        if temp_c <= 0: surface, hazard = "frozen", 0.95
        else: surface, hazard = "snow_covered", 0.85
    elif temp_c <= 0 and hours_since_rain <= 6:
        surface, hazard = "frozen", 0.90
    elif weather_type in ["rain"] or precip_1h_mm >= 1:
        surface, hazard = "wet", 0.55
    elif hours_since_rain <= 2:
        surface, hazard = "wet", 0.45
    else:
        surface, hazard = "dry", 0.10
    CHILD_LIFT = {"frozen": 30.0, "snow_covered": 20.0, "wet": 8.0, "dry": 1.0}
    child_lift = CHILD_LIFT.get(surface, 1.0)
    reason = "通常路面"
    if weather_type == "cloudy" and surface == "wet":
        child_lift = max(child_lift, 25.0)
        reason = "曇×路面湿潤：最も見落とされるリスク組み合わせ"
    elif surface == "frozen":
        reason = "路面凍結"
    elif surface == "wet":
        reason = "路面湿潤"
    return {"road_surface": surface, "hazard_score": round(hazard, 3),
            "child_risk_lift": round(child_lift, 1), "confidence": 0.75, "reason": reason}
'''
Path('scripts/road_surface_estimator.py').write_text(code, encoding='utf-8')
print('\nscripts/road_surface_estimator.py 保存完了')
