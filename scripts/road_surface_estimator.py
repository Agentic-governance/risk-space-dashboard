import json
from pathlib import Path

def estimate_road_surface(weather_type, temp_c, precip_1h_mm=0, precip_24h_mm=0, hours_since_rain=0):
    if weather_type in ["snow"] or precip_24h_mm > 5 and temp_c <= 2:
        if temp_c <= 0: surface, hazard = "frozen", 0.95
        else: surface, hazard = "snow_covered", 0.85
    elif temp_c <= 0 and hours_since_rain <= 6:
        surface, hazard = "frozen", 0.90
    elif weather_type in ["rain"] or precip_1h_mm >= 1:
        surface, hazard = "wet", 0.55
    elif hours_since_rain <= 4:
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
    hazard = max(hazard, 0.35)
    return {"road_surface": surface, "hazard_score": round(hazard, 3),
            "child_risk_lift": round(child_lift, 1), "confidence": 0.75, "reason": reason}
