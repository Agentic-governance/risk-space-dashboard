#!/usr/bin/env python3
"""Aggregate qualitative features into risk grid cells."""

from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import DefaultDict, Dict, Iterable, List, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
FEATURES_PATH = BASE_DIR / "docs" / "data" / "qualitative_features.json"
GRID_PATH = BASE_DIR / "docs" / "data" / "grid_risk.json"
OUTPUT_PATH = BASE_DIR / "docs" / "data" / "grid_qualitative.json"

BIN_SIZE = 0.2


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def bin_key(lat: float, lon: float) -> Tuple[int, int]:
    return (int(math.floor(lat / BIN_SIZE)), int(math.floor(lon / BIN_SIZE)))


def dominant_or_unknown(values: Iterable[str]) -> str:
    counter = Counter(v for v in values if v and v != "unknown")
    return counter.most_common(1)[0][0] if counter else "unknown"


def assign_label(count: int, avg_sev: float, avg_mul: float) -> str:
    if count == 0:
        return "質的情報なし"
    if avg_sev >= 0.75 or avg_mul >= 1.4:
        return "質的高リスク"
    if avg_sev >= 0.45 or avg_mul >= 1.15:
        return "質的中リスク"
    return "質的低リスク"


def nearest_cell_index(
    lat: float,
    lon: float,
    cells: List[Dict[str, object]],
    binned: Dict[Tuple[int, int], List[int]],
) -> int:
    origin = bin_key(lat, lon)
    candidates: List[int] = []

    for radius in range(0, 4):
        for di in range(-radius, radius + 1):
            for dj in range(-radius, radius + 1):
                candidates.extend(binned.get((origin[0] + di, origin[1] + dj), []))
        if candidates:
            break

    if not candidates:
        candidates = list(range(len(cells)))

    best_idx = candidates[0]
    best_dist = float("inf")
    for idx in candidates:
        cell = cells[idx]
        clat = float(cell["lat"])
        clon = float(cell["lon"])
        lat_mid = math.radians((lat + clat) / 2.0)
        dx = (lon - clon) * math.cos(lat_mid)
        dy = lat - clat
        dist = dx * dx + dy * dy
        if dist < best_dist:
            best_dist = dist
            best_idx = idx
    return best_idx


def main() -> int:
    try:
        print(f"[1/5] Loading qualitative features: {FEATURES_PATH}")
        with FEATURES_PATH.open("r", encoding="utf-8") as f:
            features = json.load(f)

        incidents = features.get("incidents", [])
        if not isinstance(incidents, list):
            raise ValueError("Invalid qualitative_features schema: incidents must be a list")

        print(f"[2/5] Loading grid: {GRID_PATH}")
        with GRID_PATH.open("r", encoding="utf-8") as f:
            grid = json.load(f)
        if not isinstance(grid, list):
            raise ValueError("Invalid grid_risk schema: expected top-level list")

        print("[3/5] Building spatial index")
        binned: DefaultDict[Tuple[int, int], List[int]] = defaultdict(list)
        for idx, cell in enumerate(grid):
            lat = cell.get("lat")
            lon = cell.get("lon")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                binned[bin_key(float(lat), float(lon))].append(idx)

        per_cell_items: DefaultDict[int, List[Dict[str, object]]] = defaultdict(list)
        geo_count = 0
        total = len(incidents)

        print(f"[4/5] Mapping {total:,} incidents to nearest cells")
        for idx, inc in enumerate(incidents, start=1):
            lat = inc.get("lat")
            lon = inc.get("lng")
            if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
                continue
            cell_idx = nearest_cell_index(float(lat), float(lon), grid, binned)
            per_cell_items[cell_idx].append(inc)
            geo_count += 1
            if idx % 2000 == 0 or idx == total:
                print(f"  mapped {idx:,}/{total:,}")

        print("[5/5] Building output cells")
        out_cells: List[Dict[str, object]] = []
        for idx, cell in enumerate(grid):
            items = per_cell_items.get(idx, [])

            victim_labels: List[str] = []
            modus_labels: List[str] = []
            location_labels: List[str] = []
            sev_values: List[float] = []
            mul_values: List[float] = []

            victim_counter: Counter[str] = Counter()
            modus_counter: Counter[str] = Counter()
            location_counter: Counter[str] = Counter()

            for inc in items:
                matched = inc.get("matched", {}) if isinstance(inc.get("matched"), dict) else {}
                v_labels = [v for v in matched.get("victim_type", []) if isinstance(v, str)]
                m_labels = [v for v in matched.get("modus_operandi", []) if isinstance(v, str)]
                l_labels = [v for v in matched.get("location_type", []) if isinstance(v, str)]

                victim_labels.extend(v_labels)
                modus_labels.extend(m_labels)
                location_labels.extend(l_labels)
                victim_counter.update(v_labels)
                modus_counter.update(m_labels)
                location_counter.update(l_labels)

                sev = inc.get("qualitative_severity_adj")
                mul = inc.get("qualitative_risk_multiplier")
                if isinstance(sev, (int, float)):
                    sev_values.append(float(sev))
                if isinstance(mul, (int, float)):
                    mul_values.append(float(mul))

            avg_sev = round(mean(sev_values), 4) if sev_values else 0.0
            avg_mul = round(mean(mul_values), 4) if mul_values else 1.0

            out_cells.append(
                {
                    "cell_index": idx,
                    "lat": cell.get("lat"),
                    "lon": cell.get("lon"),
                    "resolution": cell.get("resolution"),
                    "risk_score": cell.get("risk_score"),
                    "dominant_victim_type": dominant_or_unknown(victim_labels),
                    "dominant_modus": dominant_or_unknown(modus_labels),
                    "dominant_location": dominant_or_unknown(location_labels),
                    "victim_profile": dict(victim_counter),
                    "modus_profile": dict(modus_counter),
                    "location_profile": dict(location_counter),
                    "avg_qualitative_severity_adj": avg_sev,
                    "avg_qualitative_multiplier": avg_mul,
                    "qualitative_label": assign_label(len(items), avg_sev, avg_mul),
                    "qualitative_incident_count": len(items),
                }
            )

        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        output = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source_features": str(FEATURES_PATH),
                "source_grid": str(GRID_PATH),
                "output": str(OUTPUT_PATH),
                "cells": len(out_cells),
                "geo_incidents_mapped": geo_count,
            },
            "cells": out_cells,
        }

        with OUTPUT_PATH.open("w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"Done: wrote {len(out_cells):,} cells ({geo_count:,} incidents mapped)")
        return 0
    except FileNotFoundError as exc:
        print(f"ERROR: file not found: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pylint: disable=broad-except
        print(f"ERROR: unexpected failure: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
