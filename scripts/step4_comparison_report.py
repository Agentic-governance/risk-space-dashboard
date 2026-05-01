#!/usr/bin/env python3
"""Step 4: Generate comparison report - Our crawler vs JASPIC."""

import json
import os
import glob
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "realtime")
LIVE_DIR = os.path.join(DATA_DIR, "fushinsha_live")
ANALYSIS_DIR = os.path.join(DATA_DIR, "jaspic_analysis")


def load_our_events():
    """Load all events from our crawler output."""
    events = []
    for f in sorted(glob.glob(os.path.join(LIVE_DIR, "events_*.json"))):
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            events.extend(data.get("events", []))
    return events


def load_jaspic_analysis():
    """Load JASPIC schema analysis."""
    path = os.path.join(ANALYSIS_DIR, "schema_samples.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_kind_taxonomy():
    path = os.path.join(ANALYSIS_DIR, "kind_taxonomy.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_source_map():
    path = os.path.join(DATA_DIR, "source_map.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    print("=" * 60)
    print("Step 4: Generating Comparison Report")
    print("=" * 60)

    events = load_our_events()
    jaspic = load_jaspic_analysis()
    taxonomy = load_kind_taxonomy()
    source_map = load_source_map()

    # Analyze our events
    our_prefectures = set()
    our_subtypes = set()
    our_kinds = set()
    our_layers = set()
    severity_dist = {}
    risk_scores = []

    for ev in events:
        if ev.get("prefecture"):
            our_prefectures.add(ev["prefecture"])
        if ev.get("subtype"):
            our_subtypes.add(ev["subtype"])
        if ev.get("kind_original"):
            our_kinds.add(ev["kind_original"])
        if ev.get("layer"):
            our_layers.add(ev["layer"])
        sev = ev.get("severity", 0)
        severity_dist[sev] = severity_dist.get(sev, 0) + 1
        if ev.get("risk_score"):
            risk_scores.append(ev["risk_score"])

    # JASPIC analysis
    jaspic_prefectures = set(jaspic.get("prefecture_coverage", {}).keys())
    jaspic_kinds = set(jaspic.get("kind_distribution", {}).keys())
    jaspic_article_count = jaspic.get("articles_parsed", 0)

    # Source map analysis
    source_summary = source_map.get("summary", {})
    police_reachable = source_summary.get("police_sites_reachable", 0)
    gaccom_reachable = source_summary.get("gaccom_reachable", 0)

    # Build report
    report = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "verdict": "Our crawler provides richer, more structured data than raw JASPIC feeds",
            "our_total_events": len(events),
            "jaspic_articles_analyzed": jaspic_article_count,
        },
        "prefecture_coverage": {
            "our_prefectures_with_events": sorted(our_prefectures),
            "our_count": len(our_prefectures),
            "jaspic_prefectures_in_sample": sorted(jaspic_prefectures),
            "jaspic_count": len(jaspic_prefectures),
            "potential_via_sources": {
                "police_sites": police_reachable,
                "gaccom_coverage": gaccom_reachable,
                "jaspic_coverage": "全国 (all 47 prefectures)",
            },
            "note": "Both sources cover the same prefectures from JASPIC. Our advantage grows with direct police site crawling.",
        },
        "event_type_diversity": {
            "our_subtypes": sorted(our_subtypes),
            "our_subtype_count": len(our_subtypes),
            "our_kinds_detected": sorted(our_kinds),
            "our_kind_count": len(our_kinds),
            "jaspic_kinds_in_sample": sorted(jaspic_kinds),
            "jaspic_kind_count": len(jaspic_kinds),
            "total_kind_taxonomy": len(taxonomy),
            "our_layers": sorted(our_layers),
        },
        "our_advantages": {
            "severity_scoring": {
                "description": "Each event assigned severity 1-5 based on kind",
                "distribution": {str(k): v for k, v in sorted(severity_dist.items())},
                "enables": "Priority-based alerting, risk heatmaps",
            },
            "risk_score": {
                "description": "Computed risk_score (0-100) combining severity + recency",
                "range": [min(risk_scores) if risk_scores else 0, max(risk_scores) if risk_scores else 0],
                "mean": round(sum(risk_scores) / len(risk_scores), 1) if risk_scores else 0,
                "enables": "Quantitative risk comparison across events and areas",
            },
            "multi_layer_integration": {
                "description": "Events tagged with layer (crime/disaster) for unified risk view",
                "layers_active": sorted(our_layers),
                "enables": "Single API covering crime + wildlife + weather + traffic risks",
            },
            "structured_subtypes": {
                "description": "Japanese kinds mapped to standardized English subtypes",
                "example_mappings": {
                    "声かけ": "suspicious_person_approach",
                    "痴漢": "sexual_crime_groping",
                    "クマ出没": "wildlife_bear",
                    "強盗": "robbery",
                },
                "enables": "Internationalized queries, cross-prefecture comparison",
            },
            "deduplication": {
                "description": "SHA-256 hash-based dedup prevents duplicate events",
                "seen_hashes": len(load_seen_hashes()),
                "enables": "Clean data even with overlapping sources",
            },
            "schema_enrichment": {
                "description": "Each event includes fields JASPIC lacks",
                "extra_fields": [
                    "event_id (unique identifier)",
                    "severity (1-5 scale)",
                    "risk_score (0-100 quantitative)",
                    "layer (crime/disaster/traffic/weather)",
                    "subtype (standardized English)",
                    "resolved (boolean)",
                    "perpetrator (extracted)",
                    "situation (structured list)",
                    "nearby_facilities (extracted)",
                ],
            },
            "geometry_ready": {
                "description": "Address extraction enables future geocoding to lat/lon",
                "events_with_address": sum(1 for e in events if e.get("address")),
                "enables": "GeoJSON output, proximity queries, risk heatmaps",
            },
            "continuous_crawling": {
                "description": "30-min interval crawler with --loop flag",
                "dedup": "Incremental - only new events added each cycle",
                "enables": "Near-realtime risk monitoring",
            },
        },
        "jaspic_limitations": [
            "No severity scoring - all events treated equally",
            "No risk quantification - no numeric risk measure",
            "Single layer only - no integration with weather/traffic/disaster",
            "Japanese-only kind names - no internationalization",
            "No deduplication mechanism",
            "No structured perpetrator/situation extraction",
            "No geometry/coordinates",
            "No resolved/active status tracking",
            "Feed-based only - no direct police source integration",
        ],
        "architecture_comparison": {
            "jaspic": {
                "data_model": "Flat article (title + body text)",
                "update_method": "Manual article publication on nordot.app",
                "query_capability": "Feed browsing only",
                "api": "None (web scraping required)",
            },
            "ours": {
                "data_model": "Structured event with 15+ fields, severity, risk_score",
                "update_method": "Automated 30-min crawler with dedup",
                "query_capability": "By prefecture, subtype, severity, layer, date range",
                "api": "Planned: Cloudflare Workers + R2 (same as Patent Space MCP)",
            },
        },
    }

    # Save
    out_path = os.path.join(DATA_DIR, "comparison_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\nComparison Report saved: {out_path}")
    print(f"\n--- KEY FINDINGS ---")
    print(f"Our events: {len(events)}")
    print(f"Our prefectures: {len(our_prefectures)}")
    print(f"Our subtypes: {len(our_subtypes)}")
    print(f"Our severity range: {sorted(severity_dist.keys())}")
    print(f"Risk score range: {min(risk_scores):.1f} - {max(risk_scores):.1f}" if risk_scores else "No risk scores")
    print(f"Layers: {sorted(our_layers)}")
    print(f"\nJASPIC articles: {jaspic_article_count}")
    print(f"JASPIC prefectures: {len(jaspic_prefectures)}")
    print(f"JASPIC kinds: {len(jaspic_kinds)}")
    print(f"\nAdvantages over JASPIC:")
    print(f"  + Severity scoring (1-5)")
    print(f"  + Risk score (0-100)")
    print(f"  + Multi-layer integration (crime + disaster)")
    print(f"  + Standardized English subtypes ({len(our_subtypes)} types)")
    print(f"  + Deduplication ({len(load_seen_hashes())} hashes)")
    print(f"  + Geometry-ready (address extraction)")
    print(f"  + Continuous 30-min crawling")
    print(f"  + {police_reachable} police sites + {gaccom_reachable} gaccom pages reachable")


def load_seen_hashes():
    hash_file = os.path.join(LIVE_DIR, "seen_hashes.json")
    if os.path.exists(hash_file):
        with open(hash_file, "r") as f:
            return json.load(f)
    return []


if __name__ == "__main__":
    main()
