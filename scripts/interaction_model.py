import json
from pathlib import Path

_TABLE_PATH = Path(__file__).parent.parent / "data" / "analysis" / "interaction" / "traffic_interaction_table.json"
_DATA = None

def _load():
    global _DATA
    if _DATA is None:
        with open(_TABLE_PATH, encoding="utf-8") as f:
            _DATA = json.load(f)
    return _DATA

def lookup_traffic_lift(age_group, party_type, weather, road_surface, day_night):
    data = _load()
    table = data["table"]
    baseline = data["baseline_fatal_rate"]
    candidates = [
        f"{age_group}+{party_type}+{weather}+{road_surface}+{day_night}",
        f"{age_group}+{party_type}+{weather}+{road_surface}",
        f"{age_group}+{party_type}+{weather}",
        f"{age_group}+{weather}+{road_surface}",
        f"{age_group}+{party_type}+{day_night}",
        f"{party_type}+{weather}+{day_night}",
        f"{age_group}+{weather}",
        f"{age_group}+{party_type}",
        f"{party_type}+{weather}",
        f"{weather}+{road_surface}",
        f"{age_group}+{day_night}",
        f"{party_type}+{day_night}",
    ]
    for key in candidates:
        if key in table:
            e = table[key]
            return {"lift":e["lift"],"fatal_rate":e["fatal_rate"],"matched":key,"confidence":"high" if len(e["dims"])>=3 else "medium"}
    return {"lift":1.0,"fatal_rate":baseline,"matched":"default","confidence":"low"}

def personalized_risk(base, age_group, party_type, weather, road_surface, hour):
    if 6<=hour<16: dn="day_light"
    elif 16<=hour<19: dn="day_dim"
    elif 19<=hour<22: dn="night_lit"
    else: dn="night_dark"
    r = lookup_traffic_lift(age_group, party_type, weather, road_surface, dn)
    return {"risk":min(1.0, base*r["lift"]), "lift":r["lift"], "confidence":r["confidence"], "matched":r["matched"]}
