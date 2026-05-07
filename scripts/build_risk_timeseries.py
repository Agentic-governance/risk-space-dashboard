#!/usr/bin/env python3
"""Build pref x month risk score timeseries with dynamic current-month update."""
import json
import math
import os
from datetime import datetime, timezone
from typing import Optional

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INP = os.path.join(BASE, "docs", "data", "integrated_risk_profile.json")
EVENTS = os.path.join(BASE, "docs", "data", "events_7days.json")
OUT = os.path.join(BASE, "docs", "data", "risk_timeseries.json")

ZSCORE_WEIGHT = 0.02
MIN_STD = 1e-9


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize_pref_name(name: str, pref_names: set[str], short_to_full: dict[str, str]) -> Optional[str]:
    if not name:
        return None
    n = str(name).strip()
    if n in pref_names:
        return n
    if n in short_to_full:
        return short_to_full[n]
    if n.endswith(("都", "道", "府", "県")):
        return n if n in pref_names else None
    return short_to_full.get(n)


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


profile = load_json(INP)
pref = profile.get("prefectures", {})
now = datetime.now(timezone.utc)
current_month = now.strftime("%Y-%m")

existing = {}
if os.path.exists(OUT):
    try:
        existing = load_json(OUT)
    except Exception:
        existing = {}

existing_months = existing.get("months", []) if isinstance(existing, dict) else []
months = [m for m in existing_months if isinstance(m, str)]
if not months:
    months = sorted({k for v in profile.get("timeseries", {}).values() for k in v.keys()})
if not months:
    months = [f"{now.year}-{m:02d}" for m in range(1, 13)]
if current_month not in months:
    months.append(current_month)
months = sorted(set(months))

pref_names = set(pref.keys())
short_to_full = {}
for p in pref_names:
    short_to_full[p.rstrip("都道府県")] = p

counts = {p: 0 for p in pref_names}
dynamic_ready = False
try:
    e7 = load_json(EVENTS)
    events = e7.get("events", []) if isinstance(e7, dict) else []
    for ev in events:
        p = normalize_pref_name(ev.get("prefecture"), pref_names, short_to_full)
        if p:
            counts[p] += 1
    values = list(counts.values())
    if values and sum(values) > 0:
        mean = sum(values) / len(values)
        var = sum((x - mean) ** 2 for x in values) / len(values)
        std = math.sqrt(var)
        dynamic_ready = std > MIN_STD
except Exception:
    dynamic_ready = False

if dynamic_ready:
    values = list(counts.values())
    mean = sum(values) / len(values)
    var = sum((x - mean) ** 2 for x in values) / len(values)
    std = math.sqrt(var)

result = {}
existing_pref = existing.get("prefectures", {}) if isinstance(existing, dict) else {}
profile_ts = profile.get("timeseries", {})
for name, v in pref.items():
    base = float(v.get("composite_risk_score", 0))
    ts = {}
    seed = existing_pref.get(name) or v.get("timeseries") or profile_ts.get(name) or {}
    for m in months:
        if m in seed:
            ts[m] = round(float(seed[m]), 4)
        else:
            ts[m] = round(base, 4)

    if dynamic_ready:
        z = (counts.get(name, 0) - mean) / std
        ts[current_month] = round(clamp01(base + (z * ZSCORE_WEIGHT)), 4)
    else:
        # fallback: keep static value if data is insufficient
        ts[current_month] = round(float(ts.get(current_month, base)), 4)
    result[name] = ts

out = {
    "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "months": months,
    "prefectures": result,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"Wrote {OUT}")
