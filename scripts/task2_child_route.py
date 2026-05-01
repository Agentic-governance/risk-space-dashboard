import json, math
from pathlib import Path

Path('data/analysis/child_route').mkdir(parents=True, exist_ok=True)

with open('data/analysis/interaction/traffic_interaction_table.json', encoding='utf-8') as f:
    raw = json.load(f)
INTERACTION_TABLE = raw['table']
BASELINE = raw['baseline_fatal_rate']

def haversine(lat1,lon1,lat2,lon2):
    R=6371; dlat=math.radians(lat2-lat1); dlon=math.radians(lon2-lon1)
    a=math.sin(dlat/2)**2+math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R*2*math.asin(math.sqrt(max(0,a)))

def get_child_traffic_lift(weather,road,daynight):
    for key in [f'child+pedestrian+{weather}+{road}+{daynight}',f'child+pedestrian+{weather}+{road}',f'child+pedestrian+{weather}',f'child+{weather}+{road}',f'child+pedestrian',f'child+{road}']:
        if key in INTERACTION_TABLE: return INTERACTION_TABLE[key]['lift']
    return 5.0

grid_path = Path('dashboard/data/grid_risk.json')
if not grid_path.exists(): grid_path = Path('docs/data/grid_risk.json')
grid_data = []
if grid_path.exists():
    with open(grid_path, encoding='utf-8') as f: grid_data = json.load(f)
    print(f'グリッドデータ: {len(grid_data):,}セル')

def calc_child_route_risk(waypoints, hour, weather_type, road_surface):
    if 6<=hour<16: dn='day_light'
    elif 16<=hour<19: dn='day_dim'
    else: dn='night_lit'
    traffic_lift = get_child_traffic_lift(weather_type, road_surface, dn)
    segment_risks = []; total_dist = 0.0
    for i in range(len(waypoints)-1):
        lat1,lon1 = waypoints[i]; lat2,lon2 = waypoints[i+1]
        seg_dist = haversine(lat1,lon1,lat2,lon2); total_dist += seg_dist
        seg_lat,seg_lon = (lat1+lat2)/2, (lon1+lon2)/2
        best_cell = None; min_d = float('inf')
        for cell in grid_data[:1000]:
            d = haversine(seg_lat,seg_lon,cell.get('lat',0),cell.get('lon',0))
            if d < min_d: min_d=d; best_cell=cell
        bcr = best_cell.get('risk_score',0.1) if best_cell else 0.1
        bpe = best_cell.get('p_escape',0.5) if best_cell else 0.5
        bsv = best_cell.get('avg_severity',2.5) if best_cell else 2.5
        hc = best_cell.get('haven_count_500m',0) if best_cell else 0
        school_mult = 1.8 if 14<=hour<=18 else 1.0
        dcr = min(1.0, bcr * school_mult)
        dtr = min(1.0, 0.15 * traffic_lift)
        dpe = bpe * 0.7
        eh_crime = dcr * (bsv/5) * (1-dpe)
        eh_traffic = dtr * 0.5
        segment_risks.append({'lat':seg_lat,'lon':seg_lon,'distance_km':round(seg_dist,4),'base_crime_risk':round(bcr,4),'dynamic_traffic_risk':round(dtr,5),'traffic_lift':round(traffic_lift,2),'p_escape':round(dpe,4),'haven_count_500m':hc,'eh_crime':round(eh_crime,4),'eh_traffic':round(eh_traffic,5),'eh_total':round(min(1.0,eh_crime+eh_traffic*0.5),4)})
    if not segment_risks: return {'error':'経路データなし'}
    avg_eh = sum(s['eh_total']*s['distance_km'] for s in segment_risks)/max(total_dist,0.001)
    max_seg = max(segment_risks, key=lambda s:s['eh_total'])
    min_haven = min(s['haven_count_500m'] for s in segment_risks)
    return {'total_distance_km':round(total_dist,3),'weighted_avg_eh':round(avg_eh,4),'max_segment_eh':round(max_seg['eh_total'],4),'min_haven_count':min_haven,'traffic_lift':round(traffic_lift,2),'weather_road':f'{weather_type}x{road_surface}','highest_risk_segment':{'lat':max_seg['lat'],'lon':max_seg['lon'],'eh':max_seg['eh_total'],'haven':max_seg['haven_count_500m']},'segment_risks':segment_risks,'route_score':round(avg_eh*100,2)}

routes = {
    '最短経路（幹線道路）': [(35.6895,139.6917),(35.6910,139.6930),(35.6925,139.6945),(35.6940,139.6960)],
    '公園経由（静かな道）': [(35.6895,139.6917),(35.6905,139.6900),(35.6920,139.6920),(35.6940,139.6960)],
    '商店街経由（人通りあり）': [(35.6895,139.6917),(35.6900,139.6940),(35.6920,139.6955),(35.6940,139.6960)],
}

conditions = [
    (16,'cloudy','wet','曇×路面湿潤（実測88倍リスク）'),
    (16,'rain','wet','雨×路面湿潤'),
    (16,'sunny','dry','晴×乾燥（ベースライン）'),
    (16,'snow','snow_covered','雪×積雪'),
]

print('=== 子供向け経路リスク比較 ===\\n')
all_results = {}
for hour,weather,road,cond_label in conditions:
    print(f'\\n--- 条件: {cond_label} ---')
    results = []
    for name,wps in routes.items():
        risk = calc_child_route_risk(wps, hour, weather, road)
        risk['route_name'] = name
        results.append(risk)
    results.sort(key=lambda x: x['weighted_avg_eh'])
    best,worst = results[0], results[-1]
    reduction = (worst['weighted_avg_eh']-best['weighted_avg_eh'])/max(worst['weighted_avg_eh'],0.001)*100
    print(f"{'経路':<28} {'平均EH':>10} {'最大EH':>10} {'最少Haven':>10} {'lift':>8}")
    print('-'*70)
    for r in results:
        marker = ' ← 推奨' if r==best else (' ← 最危険' if r==worst else '')
        print(f"  {r['route_name']:<26} {r['weighted_avg_eh']:>9.4f}  {r['max_segment_eh']:>9.4f}  {r['min_haven_count']:>9}  x{r['traffic_lift']:>6.1f}{marker}")
    print(f'  リスク低減: {reduction:.1f}% ({best["route_name"]})')
    all_results[cond_label] = {'recommended':best['route_name'],'reduction_pct':round(reduction,1),'comparison':results}

# 最短経路と最安全経路が異なるか検証
print('\\n=== 核心的検証: 最短経路 ≠ 最安全経路か ===')
for cond,data in all_results.items():
    rec = data['recommended']
    is_shortest = rec == '最短経路（幹線道路）'
    print(f'  {cond}: 推奨={rec} {"← 最短と一致" if is_shortest else "← 最短と異なる ✓"}')

with open('data/analysis/child_route/route_comparison.json','w',encoding='utf-8') as f:
    json.dump(all_results,f,ensure_ascii=False,indent=2,default=str)
print('\\n保存: data/analysis/child_route/route_comparison.json')
