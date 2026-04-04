#!/usr/bin/env python3
"""
Dynamic Risk Engine for Risk Space MCP
=======================================
Combines weather, events, and temporal factors to calculate dynamic expected harm.

Usage:
    from dynamic_risk_engine import calc_dynamic_expected_harm
    result = calc_dynamic_expected_harm(
        base_p_incident=0.35, severity=3.5, base_p_escape=0.55,
        dt=datetime.now(), weather_data=weather, events_data=events,
        area_code="130000"
    )
"""

import json
import os
from datetime import datetime
from typing import Dict, Optional, Any


def get_temporal_multipliers(dt: datetime) -> Dict[str, float]:
    """Calculate temporal risk multipliers based on hour, weekday, payday."""
    hour = dt.hour
    weekday = dt.weekday()  # 0=Mon, 6=Sun
    day = dt.day

    inc = 1.0
    esc = 1.0

    # Hour-of-day
    if 22 <= hour or hour <= 4:
        inc *= 1.4; esc *= 0.7
    elif 18 <= hour < 22:
        inc *= 1.2; esc *= 0.85
    elif 6 <= hour < 9:
        inc *= 0.9; esc *= 1.1
    elif 9 <= hour < 18:
        inc *= 0.85; esc *= 1.15

    # Day-of-week
    if weekday == 4:    inc *= 1.15; esc *= 0.95
    elif weekday == 5:  inc *= 1.25; esc *= 0.9
    elif weekday == 6:  inc *= 1.1;  esc *= 0.95

    # Payday proximity
    if day in (24, 25, 26):
        inc *= 1.2

    return {"incident": round(inc, 3), "escape": round(esc, 3)}


def get_weather_multipliers(weather_data: Optional[Dict], area_code: str = "130000") -> Dict[str, float]:
    """Get weather multipliers for an area from forecast data."""
    if not weather_data:
        return {"incident": 1.0, "escape": 1.0}
    forecasts = weather_data.get("forecasts", {})
    area_forecast = forecasts.get(area_code, {})
    areas = area_forecast.get("areas", [])
    if not areas:
        return {"incident": 1.0, "escape": 1.0}
    first_area = areas[0]
    fc_list = first_area.get("forecasts", [])
    if not fc_list:
        return {"incident": 1.0, "escape": 1.0}
    return {
        "incident": fc_list[0].get("incident_multiplier", 1.0),
        "escape": fc_list[0].get("escape_multiplier", 1.0),
    }


def get_event_multipliers(events_data: Optional[Dict], dt: datetime) -> Dict[str, float]:
    """Get event multipliers for a specific date."""
    if not events_data:
        return {"incident": 1.0, "escape": 1.0}
    date_str = dt.strftime("%Y-%m-%d")
    inc = 1.0
    esc = 1.0
    holidays = events_data.get("holidays", {})
    if date_str in holidays:
        h = holidays[date_str]
        mults = h.get("risk_multipliers", {})
        inc *= mults.get("incident", 1.0)
        esc *= mults.get("escape", 1.0)
    temporal = events_data.get("temporal_events", [])
    for ev in temporal:
        if ev.get("date") == date_str:
            mults = ev.get("risk_multipliers", {})
            inc = max(inc, mults.get("incident", 1.0))
            esc = min(esc, mults.get("escape", 1.0))
    return {"incident": round(inc, 3), "escape": round(esc, 3)}


def calc_dynamic_expected_harm(
    base_p_incident: float,
    severity: float,
    base_p_escape: float,
    dt: datetime,
    weather_data: Optional[Dict] = None,
    events_data: Optional[Dict] = None,
    area_code: str = "130000",
) -> Dict[str, Any]:
    """
    Calculate dynamic expected harm.

    Formula:
        incident_mult = min(3.0, weather_inc x event_inc x temporal_inc)
        escape_mult = max(0.2, weather_esc x event_esc x temporal_esc)
        dynamic_EH = min(1.0, base_p_incident x incident_mult) x (severity/5) x
                      (1 - min(1.0, base_p_escape x escape_mult))
    """
    weather_m = get_weather_multipliers(weather_data, area_code)
    event_m = get_event_multipliers(events_data, dt)
    temporal_m = get_temporal_multipliers(dt)

    incident_mult = min(3.0,
        weather_m["incident"] * event_m["incident"] * temporal_m["incident"])
    escape_mult = max(0.2,
        weather_m["escape"] * event_m["escape"] * temporal_m["escape"])

    effective_p_incident = min(1.0, base_p_incident * incident_mult)
    effective_p_escape = min(1.0, base_p_escape * escape_mult)
    dynamic_EH = effective_p_incident * (severity / 5.0) * (1.0 - effective_p_escape)

    return {
        "input": {
            "base_p_incident": base_p_incident,
            "severity": severity,
            "base_p_escape": base_p_escape,
            "datetime": dt.isoformat(),
            "area_code": area_code,
        },
        "multipliers": {
            "weather": weather_m,
            "event": event_m,
            "temporal": temporal_m,
            "combined_incident": round(incident_mult, 4),
            "combined_escape": round(escape_mult, 4),
        },
        "effective": {
            "p_incident": round(effective_p_incident, 4),
            "p_escape": round(effective_p_escape, 4),
        },
        "dynamic_expected_harm": round(dynamic_EH, 6),
    }


def load_data(base_dir: str = None):
    """Load weather and events data from disk."""
    if base_dir is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    weather_path = os.path.join(base_dir, "data", "dynamic", "weather", "forecasts_all.json")
    events_path = os.path.join(base_dir, "data", "dynamic", "events", "all_events.json")
    weather_data = None
    events_data = None
    if os.path.exists(weather_path):
        with open(weather_path, "r", encoding="utf-8") as f:
            weather_data = json.load(f)
    if os.path.exists(events_path):
        with open(events_path, "r", encoding="utf-8") as f:
            events_data = json.load(f)
    return weather_data, events_data


if __name__ == "__main__":
    weather_data, events_data = load_data()
    result = calc_dynamic_expected_harm(
        base_p_incident=0.35, severity=3.5, base_p_escape=0.55,
        dt=datetime.now(), weather_data=weather_data, events_data=events_data,
    )
    import pprint
    pprint.pprint(result)
