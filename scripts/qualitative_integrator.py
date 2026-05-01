#!/usr/bin/env python3
"""Integrate qualitative analysis outputs and enrich risk grid cells."""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "docs" / "data"

INPUT_FILES = {
    "qualitative_features": DATA_DIR / "qualitative_features.json",
    "crime_modus_analysis": DATA_DIR / "crime_modus_analysis.json",
    "crime_victim_analysis": DATA_DIR / "crime_victim_analysis.json",
    "crime_spatiotemporal_analysis": DATA_DIR / "crime_spatiotemporal_analysis.json",
    "traffic_qualitative_analysis": DATA_DIR / "traffic_qualitative_analysis.json",
    "police_direct_incidents": DATA_DIR / "police_direct_incidents.json",
}

GRID_PATH = DATA_DIR / "grid_risk.json"
OUT_INTEGRATED = DATA_DIR / "integrated_qualitative.json"
OUT_GRID = DATA_DIR / "grid_risk_enriched.json"
OUT_LOOKUP = DATA_DIR / "qualitative_multiplier_lookup.json"

BIN_SIZE = 0.2

LOCATION_KEYWORDS = {
    "street": ["路上", "道路", "street", "road", "歩道"],
    "park": ["公園", "park", "緑地", "広場"],
    "station_train": ["駅", "電車", "列車", "ホーム", "train", "station"],
    "school_route": ["通学路", "school route", "スクールゾーン"],
    "school": ["学校", "校門", "校庭", "school"],
    "home": ["自宅", "住宅", "マンション", "アパート", "home", "house"],
    "parking": ["駐車場", "駐輪場", "parking"],
    "commercial": ["商業", "スーパー", "ショッピング", "コンビニ", "store", "mall"],
    "hospital": ["病院", "クリニック", "hospital"],
}

MODUS_KEYWORDS = {
    "stalking": ["つきまとい", "尾行", "stalk"],
    "calling": ["声かけ", "話しかけ"],
    "groping": ["痴漢", "触", "grop"],
    "weapon": ["刃物", "包丁", "ナイフ", "凶器", "weapon"],
    "intrusion": ["侵入", "忍込み", "空き巣", "break-in"],
    "assault": ["暴行", "殴", "蹴", "assault"],
    "vehicle": ["ひったくり", "車上", "自転車盗", "オートバイ盗", "vehicle"],
}

WEATHER_ALIASES = {
    "晴": "sunny",
    "sunny": "sunny",
    "rain": "rain",
    "雨": "rain",
    "snow": "snow",
    "雪": "snow",
    "storm": "storm",
    "暴風": "storm",
    "霧": "fog",
    "fog": "fog",
    "曇": "cloudy",
    "cloud": "cloudy",
}


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_json_load(path: Path) -> Any | None:
    if not path.exists():
        print(f"[SKIP] missing input: {path}")
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        print(f"[SKIP] invalid json: {path} ({exc})")
        return None


def iter_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("incidents", "records", "events", "items", "data", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def flatten_text(*values: Any) -> str:
    return " ".join(str(v) for v in values if v is not None).strip().lower()


def parse_hour_key(text: str) -> int | None:
    lowered = text.lower().strip()
    if lowered in {"am", "pm"}:
        return None
    m = re.search(r"(?<!\d)([01]?\d|2[0-3])(?!\d)", lowered)
    if not m:
        return None
    hour = int(m.group(1))
    if 0 <= hour <= 23:
        return hour
    return None


def parse_hour(value: Any) -> int | None:
    if isinstance(value, int) and 0 <= value <= 23:
        return value
    if isinstance(value, float) and 0 <= int(value) <= 23:
        return int(value)
    if isinstance(value, str):
        m = re.search(r"(?:t|\s|^)([01]?\d|2[0-3]):[0-5]\d", value)
        if m:
            return int(m.group(1))
        return parse_hour_key(value)
    return None


def parse_hour_from_record(record: dict[str, Any]) -> int | None:
    for key in (
        "hour",
        "incident_hour",
        "time",
        "time_slot",
        "timestamp",
        "datetime",
        "occurred_at",
        "date",
    ):
        if key in record:
            hour = parse_hour(record.get(key))
            if hour is not None:
                return hour
    temporal = None
    if isinstance(record.get("matched"), dict):
        temporal = record["matched"].get("temporal_context")
    if isinstance(temporal, list):
        tags = set(str(t) for t in temporal)
        if "to_school" in tags:
            return 8
        if "after_school" in tags:
            return 16
        if "commute_work" in tags:
            return 8
        if "commute_home" in tags:
            return 18
        if "sleeping" in tags:
            return 1
    return None


def to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def parse_lat_lon(record: dict[str, Any]) -> tuple[float | None, float | None]:
    lat = None
    lon = None
    for k in ("lat", "latitude", "緯度"):
        if k in record:
            lat = to_float(record.get(k))
            break
    for k in ("lon", "lng", "longitude", "経度"):
        if k in record:
            lon = to_float(record.get(k))
            break
    return lat, lon


def normalize_location_label(text: str) -> str:
    t = text.lower()
    for canonical, keys in LOCATION_KEYWORDS.items():
        if any(k.lower() in t for k in keys):
            return canonical
    return "other"


def parse_location_labels(record: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    matched = record.get("matched")
    if isinstance(matched, dict):
        raw = matched.get("location_type")
        if isinstance(raw, list):
            labels.extend(str(x) for x in raw if x)
    for key in ("location_type", "location", "place", "場所", "発生場所"):
        value = record.get(key)
        if isinstance(value, str):
            labels.append(normalize_location_label(value))
        elif isinstance(value, list):
            labels.extend(normalize_location_label(str(x)) for x in value if x)
    if not labels:
        return ["other"]
    return labels


def parse_modus_labels(record: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    matched = record.get("matched")
    if isinstance(matched, dict):
        raw = matched.get("modus_operandi")
        if isinstance(raw, list):
            labels.extend(str(x) for x in raw if x)
    for key in ("modus", "modus_operandi", "手口", "category", "type"):
        value = record.get(key)
        if isinstance(value, str):
            labels.append(value)
        elif isinstance(value, list):
            labels.extend(str(x) for x in value if x)
    if not labels:
        text = flatten_text(record.get("title"), record.get("description"), record.get("detail"))
        for canonical, keys in MODUS_KEYWORDS.items():
            if any(k.lower() in text for k in keys):
                labels.append(canonical)
    return labels or ["unknown"]


def normalize_gender(value: Any) -> str:
    text = flatten_text(value)
    if not text:
        return "unknown"
    if any(token in text for token in ("female", "女性", "女")):
        return "female"
    if any(token in text for token in ("male", "男性", "男")):
        return "male"
    return "unknown"


def normalize_age_bucket(value: Any) -> str:
    if isinstance(value, (int, float)):
        age = int(value)
        if age < 13:
            return "child"
        if age < 20:
            return "teen"
        if age < 65:
            return "adult"
        return "elderly"
    text = flatten_text(value)
    if not text:
        return "unknown"
    if any(token in text for token in ("child", "児童", "園児", "小学生", "中学生", "高校生", "teen")):
        return "child_teen"
    if any(token in text for token in ("高齢", "elder", "老人")):
        return "elderly"
    if any(token in text for token in ("adult", "成人", "女性", "男性", "woman", "man")):
        return "adult"
    return "unknown"


def parse_victim_profiles(record: dict[str, Any], location_labels: list[str]) -> list[str]:
    victim_labels: list[str] = []
    matched = record.get("matched")
    if isinstance(matched, dict):
        raw = matched.get("victim_type")
        if isinstance(raw, list):
            victim_labels.extend(str(x) for x in raw if x)
    if victim_labels:
        combos = [f"{v}@{location_labels[0]}" for v in victim_labels]
        return combos

    age = None
    gender = None
    for key in ("victim_age", "age", "年齢"):
        if key in record:
            age = record.get(key)
            break
    for key in ("victim_gender", "gender", "sex", "性別"):
        if key in record:
            gender = record.get(key)
            break
    age_bucket = normalize_age_bucket(age)
    gender_bucket = normalize_gender(gender)
    return [f"{age_bucket}_{gender_bucket}@{location_labels[0]}"]


def normalize_weather(value: Any) -> str:
    text = flatten_text(value)
    if not text:
        return "unknown"
    for key, norm in WEATHER_ALIASES.items():
        if key in text:
            return norm
    return "other"


def parse_weather_label(record: dict[str, Any]) -> str:
    for key in ("weather", "天候", "condition", "気象"):
        if key in record:
            return normalize_weather(record.get(key))
    return "unknown"


def bin_key(lat: float, lon: float) -> tuple[int, int]:
    return (int(math.floor(lat / BIN_SIZE)), int(math.floor(lon / BIN_SIZE)))


def build_grid_index(grid: list[dict[str, Any]]) -> dict[tuple[int, int], list[int]]:
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, cell in enumerate(grid):
        lat = to_float(cell.get("lat"))
        lon = to_float(cell.get("lon"))
        if lat is None or lon is None:
            continue
        buckets[bin_key(lat, lon)].append(i)
    return buckets


def nearest_cell_index(
    lat: float,
    lon: float,
    grid: list[dict[str, Any]],
    buckets: dict[tuple[int, int], list[int]],
) -> int | None:
    origin = bin_key(lat, lon)
    candidates: list[int] = []
    for radius in range(0, 4):
        for di in range(-radius, radius + 1):
            for dj in range(-radius, radius + 1):
                candidates.extend(buckets.get((origin[0] + di, origin[1] + dj), []))
        if candidates:
            break
    if not candidates:
        return None

    best_idx = None
    best_dist = float("inf")
    for idx in candidates:
        c_lat = to_float(grid[idx].get("lat"))
        c_lon = to_float(grid[idx].get("lon"))
        if c_lat is None or c_lon is None:
            continue
        lat_mid = math.radians((lat + c_lat) / 2.0)
        dx = (lon - c_lon) * math.cos(lat_mid)
        dy = lat - c_lat
        dist = dx * dx + dy * dy
        if dist < best_dist:
            best_dist = dist
            best_idx = idx
    return best_idx


def distribution_to_multipliers(
    counter: Counter[str],
    low: float = 0.7,
    high: float = 1.8,
) -> dict[str, float]:
    if not counter:
        return {}
    mean_val = sum(counter.values()) / max(1, len(counter))
    if mean_val <= 0:
        return {}
    out: dict[str, float] = {}
    for key, value in counter.items():
        rel = value / mean_val
        out[key] = round(clip(math.sqrt(rel), low, high), 4)
    return out


def hourly_multipliers(hour_counts: list[float]) -> list[float]:
    total = sum(hour_counts)
    if total <= 0:
        return [1.0] * 24
    mean_hour = total / 24.0
    result: list[float] = []
    for val in hour_counts:
        rel = (val + 1e-9) / (mean_hour + 1e-9)
        result.append(round(clip(math.sqrt(rel), 0.7, 1.8), 4))
    return result


def weighted_lookup_multiplier(counter: Counter[str], lookup: dict[str, float], default: float = 1.0) -> float:
    if not counter:
        return default
    total = sum(counter.values())
    if total <= 0:
        return default
    score = 0.0
    for key, cnt in counter.items():
        score += cnt * lookup.get(key, default)
    return score / total


def dominant(counter: Counter[str], fallback: str = "unknown") -> str:
    return counter.most_common(1)[0][0] if counter else fallback


def try_extract_hour_distribution(payload: Any, hours: list[float]) -> int:
    extracted = 0

    def walk(obj: Any) -> None:
        nonlocal extracted
        if isinstance(obj, dict):
            parsed: dict[int, float] = {}
            for k, v in obj.items():
                hour = parse_hour_key(str(k))
                val = to_float(v)
                if hour is not None and val is not None:
                    parsed[hour] = parsed.get(hour, 0.0) + val
            if len(parsed) >= 4:
                for h, val in parsed.items():
                    hours[h] += val
                extracted += len(parsed)
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(payload)
    return extracted


def try_extract_location_distribution(payload: Any, location_counter: Counter[str]) -> int:
    extracted = 0

    def walk(obj: Any) -> None:
        nonlocal extracted
        if isinstance(obj, dict):
            for key, val in obj.items():
                lowered = str(key).lower()
                if any(token in lowered for token in ("location", "place", "場所")) and isinstance(val, dict):
                    for lk, lv in val.items():
                        f = to_float(lv)
                        if f is not None:
                            location_counter[normalize_location_label(str(lk))] += f
                            extracted += 1
                walk(val)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(payload)
    return extracted


def try_extract_weather_distribution(payload: Any, weather_counter: Counter[str]) -> int:
    extracted = 0

    def walk(obj: Any) -> None:
        nonlocal extracted
        if isinstance(obj, dict):
            for key, val in obj.items():
                lowered = str(key).lower()
                if any(token in lowered for token in ("weather", "天候", "気象")):
                    if isinstance(val, dict):
                        for wk, wv in val.items():
                            f = to_float(wv)
                            if f is not None:
                                weather_counter[normalize_weather(wk)] += f
                                extracted += 1
                    elif isinstance(val, list):
                        for item in val:
                            if isinstance(item, dict):
                                label = normalize_weather(
                                    item.get("weather") or item.get("condition") or item.get("label")
                                )
                                score = to_float(item.get("count") or item.get("value") or item.get("risk") or 1)
                                if score is not None:
                                    weather_counter[label] += score
                                    extracted += 1
                walk(val)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(payload)
    return extracted


def main() -> int:
    grid_payload = safe_json_load(GRID_PATH)
    if not isinstance(grid_payload, list):
        print(f"ERROR: grid file missing or invalid: {GRID_PATH}", file=sys.stderr)
        return 1
    grid: list[dict[str, Any]] = [c for c in grid_payload if isinstance(c, dict)]
    if not grid:
        print("ERROR: grid is empty", file=sys.stderr)
        return 1

    buckets = build_grid_index(grid)
    cell_stats: dict[int, dict[str, Any]] = defaultdict(
        lambda: {
            "location": Counter(),
            "modus": Counter(),
            "victim": Counter(),
            "hours": [0.0] * 24,
            "weather": Counter(),
            "incident_mul": [],
            "records": 0,
        }
    )

    location_counter: Counter[str] = Counter()
    modus_counter: Counter[str] = Counter()
    victim_counter: Counter[str] = Counter()
    weather_counter: Counter[str] = Counter()
    regional_modus: dict[str, Counter[str]] = defaultdict(Counter)
    hour_counts = [0.0] * 24

    loaded_sources: list[str] = []
    source_record_counts: dict[str, int] = {}
    mapped_records = 0

    def ingest_records(records: list[dict[str, Any]], source_name: str) -> None:
        nonlocal mapped_records
        rec_count = 0
        for rec in records:
            rec_count += 1
            locations = parse_location_labels(rec)
            moduses = parse_modus_labels(rec)
            victims = parse_victim_profiles(rec, locations)
            weather = parse_weather_label(rec)
            hour = parse_hour_from_record(rec)

            location_counter.update(locations)
            modus_counter.update(moduses)
            victim_counter.update(victims)
            weather_counter[weather] += 1
            if hour is not None:
                hour_counts[hour] += 1

            lat, lon = parse_lat_lon(rec)
            if lat is None or lon is None:
                continue
            idx = nearest_cell_index(lat, lon, grid, buckets)
            if idx is None:
                continue
            mapped_records += 1
            cs = cell_stats[idx]
            cs["records"] += 1
            cs["location"].update(locations)
            cs["modus"].update(moduses)
            cs["victim"].update(victims)
            cs["weather"][weather] += 1
            if hour is not None:
                cs["hours"][hour] += 1
            incident_mul = to_float(rec.get("qualitative_risk_multiplier"))
            if incident_mul is not None:
                cs["incident_mul"].append(incident_mul)
        source_record_counts[source_name] = rec_count

    for source_name, path in INPUT_FILES.items():
        payload = safe_json_load(path)
        if payload is None:
            continue
        loaded_sources.append(source_name)

        if source_name == "crime_modus_analysis" and isinstance(payload, dict):
            national = payload.get("national_modus_top100")
            if isinstance(national, list):
                for item in national:
                    if isinstance(item, dict):
                        label = str(item.get("value", "")).strip()
                        cnt = to_float(item.get("count")) or 0.0
                        if label:
                            modus_counter[label] += cnt

            pref_data = payload.get("prefecture_modus_top10")
            if isinstance(pref_data, dict):
                for pref, items in pref_data.items():
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                label = str(item.get("value", "")).strip()
                                cnt = to_float(item.get("count")) or 0.0
                                if label:
                                    regional_modus[str(pref)][label] += cnt

        records = iter_records(payload)
        if records:
            ingest_records(records, source_name)
        else:
            source_record_counts[source_name] = 0

        if source_name in {"crime_spatiotemporal_analysis", "traffic_qualitative_analysis"}:
            try_extract_hour_distribution(payload, hour_counts)
            try_extract_location_distribution(payload, location_counter)
        if source_name == "traffic_qualitative_analysis":
            try_extract_weather_distribution(payload, weather_counter)

    location_multiplier = distribution_to_multipliers(location_counter, low=0.7, high=1.8)
    hour_multiplier = hourly_multipliers(hour_counts)
    victim_multiplier = distribution_to_multipliers(victim_counter, low=0.75, high=2.2)
    weather_multiplier = distribution_to_multipliers(weather_counter, low=0.8, high=1.8)

    global_dominant_modus = dominant(modus_counter, fallback="unknown")
    global_dominant_victim = dominant(victim_counter, fallback="unknown")
    global_weather_sensitivity = (
        sum(abs(v - 1.0) for v in weather_multiplier.values()) / len(weather_multiplier)
        if weather_multiplier
        else 0.0
    )

    enriched_grid: list[dict[str, Any]] = []
    q_mult_values: list[float] = []

    for i, cell in enumerate(grid):
        cs = cell_stats.get(i)
        if cs is None:
            cs = {
                "location": Counter(),
                "modus": Counter(),
                "victim": Counter(),
                "hours": [0.0] * 24,
                "weather": Counter(),
                "incident_mul": [],
                "records": 0,
            }

        loc_score = weighted_lookup_multiplier(cs["location"], location_multiplier, default=1.0)
        vic_score = weighted_lookup_multiplier(cs["victim"], victim_multiplier, default=1.0)
        wea_score = weighted_lookup_multiplier(cs["weather"], weather_multiplier, default=1.0)
        inc_score = (
            sum(cs["incident_mul"]) / len(cs["incident_mul"]) if cs["incident_mul"] else None
        )

        components: list[tuple[float, float]] = []
        if inc_score is not None:
            components.append((inc_score, 0.45))
        if cs["location"]:
            components.append((loc_score, 0.25))
        if cs["victim"]:
            components.append((vic_score, 0.15))
        if cs["weather"]:
            components.append((wea_score, 0.15))

        if components:
            numerator = sum(score * w for score, w in components)
            denominator = sum(w for _, w in components)
            q_mult = clip(numerator / denominator, 0.7, 2.5)
        else:
            q_mult = 1.0

        if sum(cs["hours"]) > 0:
            cell_hour_mult = hourly_multipliers(cs["hours"])
            time_profile = [
                round(0.6 * hour_multiplier[h] + 0.4 * cell_hour_mult[h], 4) for h in range(24)
            ]
        else:
            time_profile = list(hour_multiplier)

        if cs["weather"]:
            total_w = sum(cs["weather"].values())
            w_sens = 0.0
            if total_w > 0:
                for w_label, cnt in cs["weather"].items():
                    m = weather_multiplier.get(w_label, 1.0)
                    w_sens += (cnt / total_w) * abs(m - 1.0)
        else:
            w_sens = global_weather_sensitivity

        dominant_region_modus = dominant(cs["modus"], fallback=global_dominant_modus)
        dominant_victim_profile = dominant(cs["victim"], fallback=global_dominant_victim)

        row = dict(cell)
        row["qualitative_risk_multiplier"] = round(q_mult, 4)
        row["dominant_crime_modus"] = dominant_region_modus
        row["dominant_victim_profile"] = dominant_victim_profile
        row["time_risk_profile"] = time_profile
        row["weather_sensitivity"] = round(clip(w_sens, 0.0, 1.0), 4)
        enriched_grid.append(row)
        q_mult_values.append(float(row["qualitative_risk_multiplier"]))

    integrated = {
        "metadata": {
            "generated_at": now_iso(),
            "input_files": {k: str(v) for k, v in INPUT_FILES.items()},
            "grid_file": str(GRID_PATH),
            "sources_loaded": loaded_sources,
            "source_record_counts": source_record_counts,
            "mapped_records_to_grid": mapped_records,
            "grid_cells": len(grid),
            "schema_version": "1.0.0",
        },
        "location_risk_multiplier": dict(sorted(location_multiplier.items())),
        "time_risk_multiplier_24h": hour_multiplier,
        "victim_vulnerability_multiplier": dict(sorted(victim_multiplier.items())),
        "weather_risk_multiplier": dict(sorted(weather_multiplier.items())),
        "regional_crime_modus_patterns": {
            region: dict(counter.most_common(10))
            for region, counter in sorted(regional_modus.items(), key=lambda x: x[0])
        },
        "global_dominant_crime_modus": global_dominant_modus,
        "global_dominant_victim_profile": global_dominant_victim,
    }

    lookup = {
        "metadata": {
            "generated_at": now_iso(),
            "source_grid": str(GRID_PATH),
            "source_enriched_grid": str(OUT_GRID),
            "cells": len(enriched_grid),
        },
        "lookup": [
            {
                "cell_index": idx,
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "qualitative_risk_multiplier": row.get("qualitative_risk_multiplier"),
                "dominant_crime_modus": row.get("dominant_crime_modus"),
                "dominant_victim_profile": row.get("dominant_victim_profile"),
                "weather_sensitivity": row.get("weather_sensitivity"),
            }
            for idx, row in enumerate(enriched_grid)
        ],
    }

    OUT_INTEGRATED.parent.mkdir(parents=True, exist_ok=True)
    with OUT_INTEGRATED.open("w", encoding="utf-8") as f:
        json.dump(integrated, f, ensure_ascii=False, indent=2)
    with OUT_GRID.open("w", encoding="utf-8") as f:
        json.dump(enriched_grid, f, ensure_ascii=False, indent=2)
    with OUT_LOOKUP.open("w", encoding="utf-8") as f:
        json.dump(lookup, f, ensure_ascii=False, indent=2)

    min_mult = min(q_mult_values) if q_mult_values else 1.0
    max_mult = max(q_mult_values) if q_mult_values else 1.0
    avg_mult = (sum(q_mult_values) / len(q_mult_values)) if q_mult_values else 1.0

    print("=== qualitative integrator summary ===")
    print(f"loaded_sources: {len(loaded_sources)} -> {', '.join(loaded_sources) if loaded_sources else 'none'}")
    print(f"source_record_counts: {source_record_counts}")
    print(f"mapped_records_to_grid: {mapped_records:,}")
    print(f"grid_cells_enriched: {len(enriched_grid):,}")
    print(f"qualitative_multiplier(min/avg/max): {min_mult:.4f} / {avg_mult:.4f} / {max_mult:.4f}")
    print(f"output_integrated: {OUT_INTEGRATED}")
    print(f"output_grid_enriched: {OUT_GRID}")
    print(f"output_lookup: {OUT_LOOKUP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
