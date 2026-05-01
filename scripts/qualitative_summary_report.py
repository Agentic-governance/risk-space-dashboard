#!/usr/bin/env python3
"""Generate summary report from qualitative feature extraction."""

from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import DefaultDict, Dict, Iterable, List, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
FEATURES_PATH = BASE_DIR / "docs" / "data" / "qualitative_features.json"
OUTPUT_PATH = BASE_DIR / "docs" / "data" / "qualitative_report.json"


def dominant_or_unknown(values: Iterable[str]) -> str:
    counter = Counter(v for v in values if v and v != "unknown")
    return counter.most_common(1)[0][0] if counter else "unknown"


def get_time_bucket(matched: Dict[str, List[str]]) -> str:
    env = set(matched.get("environmental_risk", []))
    temporal = set(matched.get("temporal_context", []))

    if "nighttime" in env:
        return "nighttime"
    if "after_school" in temporal:
        return "after_school"
    if "to_school" in temporal:
        return "to_school"
    if "commute_home" in temporal:
        return "commute_home"
    if "commute_work" in temporal:
        return "commute_work"
    if "shopping" in temporal:
        return "shopping"
    if "sleeping" in temporal:
        return "sleeping"
    return "other"


def top3(counter: Counter[str]) -> List[Dict[str, object]]:
    return [{"label": label, "count": count} for label, count in counter.most_common(3)]


def safe_rate(num: int, den: int) -> float:
    return num / den if den > 0 else 0.0


def main() -> int:
    try:
        print(f"[1/5] Loading qualitative features: {FEATURES_PATH}")
        with FEATURES_PATH.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        incidents = payload.get("incidents", [])
        if not isinstance(incidents, list):
            raise ValueError("Invalid qualitative_features schema: incidents must be a list")

        print(f"[2/5] Processing {len(incidents):,} incidents")

        nationwide = {
            "victim_type_distribution": Counter(),
            "modus_operandi_distribution": Counter(),
            "location_type_distribution": Counter(),
        }
        pref_stats: DefaultDict[str, Dict[str, Counter[str]]] = defaultdict(
            lambda: {
                "victim_type": Counter(),
                "modus_operandi": Counter(),
                "location_type": Counter(),
                "incidents": Counter({"total": 0}),
            }
        )

        cross_modus_victim: Counter[str] = Counter()
        cross_location_time: Counter[str] = Counter()
        pattern_acc: DefaultDict[Tuple[str, str, str], Dict[str, float]] = defaultdict(
            lambda: {"count": 0, "sev_sum": 0.0, "mul_sum": 0.0}
        )

        total = len(incidents)
        for idx, inc in enumerate(incidents, start=1):
            matched = inc.get("matched", {}) if isinstance(inc.get("matched"), dict) else {}
            prefecture = str(inc.get("prefecture") or "不明")

            victim_labels = [x for x in matched.get("victim_type", []) if isinstance(x, str)]
            modus_labels = [x for x in matched.get("modus_operandi", []) if isinstance(x, str)]
            location_labels = [x for x in matched.get("location_type", []) if isinstance(x, str)]

            nationwide["victim_type_distribution"].update(victim_labels)
            nationwide["modus_operandi_distribution"].update(modus_labels)
            nationwide["location_type_distribution"].update(location_labels)

            pref_stats[prefecture]["victim_type"].update(victim_labels)
            pref_stats[prefecture]["modus_operandi"].update(modus_labels)
            pref_stats[prefecture]["location_type"].update(location_labels)
            pref_stats[prefecture]["incidents"].update(["total"])

            dom_victim = dominant_or_unknown(victim_labels)
            dom_modus = dominant_or_unknown(modus_labels)
            dom_location = dominant_or_unknown(location_labels)

            if dom_victim != "unknown" and dom_modus != "unknown":
                cross_modus_victim[f"{dom_modus}::{dom_victim}"] += 1

            time_bucket = get_time_bucket(matched)
            if dom_location != "unknown":
                cross_location_time[f"{dom_location}::{time_bucket}"] += 1

            sev = float(inc.get("qualitative_severity_adj") or 0.0)
            mul = float(inc.get("qualitative_risk_multiplier") or 1.0)
            key = (dom_victim, dom_modus, dom_location)
            pattern_acc[key]["count"] += 1
            pattern_acc[key]["sev_sum"] += sev
            pattern_acc[key]["mul_sum"] += mul

            if idx % 2000 == 0 or idx == total:
                print(f"  processed {idx:,}/{total:,}")

        print("[3/5] Building prefecture top-3 summary")
        prefecture_top3: Dict[str, Dict[str, List[Dict[str, object]]]] = {}
        for pref, stats in pref_stats.items():
            prefecture_top3[pref] = {
                "victim_type_top3": top3(stats["victim_type"]),
                "modus_operandi_top3": top3(stats["modus_operandi"]),
                "location_type_top3": top3(stats["location_type"]),
            }

        print("[4/5] Detecting anomalous (2σ) patterns")
        pref_totals = {pref: stats["incidents"]["total"] for pref, stats in pref_stats.items()}
        anomaly_flags: List[Dict[str, object]] = []

        for dimension in ["victim_type", "modus_operandi"]:
            labels = set()
            for stats in pref_stats.values():
                labels.update(stats[dimension].keys())

            for label in labels:
                rates = [safe_rate(pref_stats[p][dimension][label], pref_totals[p]) for p in pref_stats]
                mu = mean(rates) if rates else 0.0
                sigma = pstdev(rates) if len(rates) > 1 else 0.0
                threshold = mu + 2.0 * sigma

                for pref in pref_stats:
                    count = pref_stats[pref][dimension][label]
                    rate = safe_rate(count, pref_totals[pref])
                    if sigma > 0 and rate >= threshold and count >= 5:
                        anomaly_flags.append(
                            {
                                "prefecture": pref,
                                "dimension": dimension,
                                "label": label,
                                "count": count,
                                "rate": round(rate, 4),
                                "national_mean": round(mu, 4),
                                "national_std": round(sigma, 4),
                                "zscore": round((rate - mu) / sigma, 3),
                            }
                        )

        anomaly_flags.sort(key=lambda x: x["zscore"], reverse=True)

        print("[5/5] Computing top 10 dangerous patterns")
        top_patterns: List[Dict[str, object]] = []
        for (victim, modus, location), acc in pattern_acc.items():
            count = int(acc["count"])
            avg_sev = acc["sev_sum"] / count if count else 0.0
            avg_mul = acc["mul_sum"] / count if count else 1.0
            score = avg_sev * avg_mul * (1.0 + min(count, 100) / 100.0)
            top_patterns.append(
                {
                    "victim_type": victim,
                    "modus_operandi": modus,
                    "location_type": location,
                    "count": count,
                    "avg_qualitative_severity_adj": round(avg_sev, 4),
                    "avg_qualitative_multiplier": round(avg_mul, 4),
                    "danger_score": round(score, 4),
                }
            )
        top_patterns.sort(key=lambda x: x["danger_score"], reverse=True)

        report = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": str(FEATURES_PATH),
                "output": str(OUTPUT_PATH),
                "total_incidents": len(incidents),
            },
            "national_summary": {
                "victim_type_distribution": dict(nationwide["victim_type_distribution"]),
                "modus_operandi_distribution": dict(nationwide["modus_operandi_distribution"]),
                "location_type_distribution": dict(nationwide["location_type_distribution"]),
            },
            "prefecture_top3": prefecture_top3,
            "cross_tabulation": {
                "modus_x_victim_type": dict(cross_modus_victim),
                "location_type_x_time_bucket": dict(cross_location_time),
            },
            "anomalous_patterns_2sigma": anomaly_flags,
            "top10_danger_patterns": top_patterns[:10],
        }

        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_PATH.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"Done: wrote report to {OUTPUT_PATH}")
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
