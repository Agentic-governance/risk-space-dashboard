from datetime import datetime
import json
from pathlib import Path

def generate_child_safety_alert(school_name, school_lat, school_lon, hour, weather_type, temp_c, precip_1h_mm, hours_since_rain, road_surface_estimate, traffic_lift, haven_count_500m):
    if traffic_lift >= 50: level,level_text = 'red','注意喚起レベル：高'
    elif traffic_lift >= 15: level,level_text = 'orange','注意喚起レベル：やや高'
    elif traffic_lift >= 5: level,level_text = 'yellow','注意喚起レベル：中'
    else: level,level_text = 'green','通常'
    road_desc = {'frozen':'路面が凍結している可能性があります','snow_covered':'積雪・圧雪の可能性があります','wet':'路面が湿った状態です','dry':'路面は乾燥しています'}.get(road_surface_estimate,'路面状態を確認してください')
    special_note = ''
    if weather_type == 'cloudy' and road_surface_estimate == 'wet':
        special_note = '参考情報：曇天で路面が湿っている状況は、雨天時と比べて見落とされやすい条件です。過去の記録では、このような日に歩行中の子供の事故が増える傾向があります。'
    weather_emoji = {'sunny':'☀️','cloudy':'☁️','rain':'🌧','snow':'❄️','fog':'🌫'}.get(weather_type,'🌤')
    message = f'{level_text}\\n\\n{school_name} 本日の下校時 参考情報\\n{weather_emoji} 天候：{weather_type} / 気温：{temp_c:.0f}℃\\n\\n【路面状況】{road_desc}\\n【周辺施設】半径500m以内に{haven_count_500m}施設'
    if special_note: message += f'\\n\\n{special_note}'
    message += '\\n\\nこれは過去の記録をもとにした参考情報です。\\n登下校の判断はご家庭でお願いします。'
    return {'school':school_name,'datetime':datetime.now().isoformat(),'alert_level':level,'traffic_risk_lift':round(traffic_lift,1),'road_surface':road_surface_estimate,'weather':weather_type,'message':message,'source_note':'過去の記録に基づく傾向情報。予測・保証ではありません。'}

print('=== 子供安全アラート生成テスト ===\\n')
tests = [
    {'school_name':'○○小学校','school_lat':35.68,'school_lon':139.70,'hour':15,'weather_type':'cloudy','temp_c':8,'precip_1h_mm':0,'hours_since_rain':3,'road_surface_estimate':'wet','traffic_lift':25.0,'haven_count_500m':3},
    {'school_name':'△△小学校','school_lat':35.70,'school_lon':139.72,'hour':16,'weather_type':'snow','temp_c':-1,'precip_1h_mm':2,'hours_since_rain':0,'road_surface_estimate':'snow_covered','traffic_lift':70.0,'haven_count_500m':1},
    {'school_name':'□□小学校','school_lat':35.72,'school_lon':139.68,'hour':15,'weather_type':'sunny','temp_c':18,'precip_1h_mm':0,'hours_since_rain':72,'road_surface_estimate':'dry','traffic_lift':1.0,'haven_count_500m':8},
]
for params in tests:
    alert = generate_child_safety_alert(**params)
    print(f'【{alert["school"]}】 レベル:{alert["alert_level"]} リフト:x{alert["traffic_risk_lift"]}')
    print(alert['message'])
    print('-'*50)
    # 文言チェック
    forbidden = ['予測','確率','危険','安全です']
    for word in forbidden:
        if word in alert['message']:
            print(f'  ⚠ 禁止語検出: 「{word}」')

# 保存
code = '''from datetime import datetime

def generate_child_safety_alert(school_name, school_lat, school_lon, hour,
                                 weather_type, temp_c, precip_1h_mm,
                                 hours_since_rain, road_surface_estimate,
                                 traffic_lift, haven_count_500m):
    """子供安全アラート生成。予測・確率・危険・安全は使わない。傾向・記録・参考情報のみ使用。"""
    if traffic_lift >= 50: level, level_text = "red", "注意喚起レベル：高"
    elif traffic_lift >= 15: level, level_text = "orange", "注意喚起レベル：やや高"
    elif traffic_lift >= 5: level, level_text = "yellow", "注意喚起レベル：中"
    else: level, level_text = "green", "通常"
    road_desc = {"frozen": "路面が凍結している可能性があります",
                 "snow_covered": "積雪・圧雪の可能性があります",
                 "wet": "路面が湿った状態です",
                 "dry": "路面は乾燥しています"}.get(road_surface_estimate, "路面状態を確認してください")
    special_note = ""
    if weather_type == "cloudy" and road_surface_estimate == "wet":
        special_note = ("参考情報：曇天で路面が湿っている状況は、雨天時と比べて"
                        "見落とされやすい条件です。過去の記録では、このような日に"
                        "歩行中の子供の事故が増える傾向があります。")
    weather_emoji = {"sunny": "☀️", "cloudy": "☁️", "rain": "🌧",
                     "snow": "❄️", "fog": "🌫"}.get(weather_type, "🌤")
    message = (f"{level_text}\\n\\n{school_name} 本日の下校時 参考情報\\n"
               f"{weather_emoji} 天候：{weather_type} / 気温：{temp_c:.0f}℃\\n\\n"
               f"【路面状況】{road_desc}\\n【周辺施設】半径500m以内に{haven_count_500m}施設")
    if special_note:
        message += f"\\n\\n{special_note}"
    message += "\\n\\nこれは過去の記録をもとにした参考情報です。\\n登下校の判断はご家庭でお願いします。"
    return {"school": school_name, "datetime": datetime.now().isoformat(),
            "alert_level": level, "traffic_risk_lift": round(traffic_lift, 1),
            "road_surface": road_surface_estimate, "weather": weather_type,
            "message": message,
            "source_note": "過去の記録に基づく傾向情報。予測・保証ではありません。"}
'''
Path('scripts/child_safety_alert.py').write_text(code, encoding='utf-8')
print('\\nscripts/child_safety_alert.py 保存完了')
