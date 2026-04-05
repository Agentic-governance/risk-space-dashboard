# Risk Space MCP — Data Dictionary

**Version**: 1.0.0 (2026-04-05)
**Scope**: All top-level JSON files in `docs/data/`.
**Purpose**: Enterprise procurement / data-governance review.

Conventions:
- **Type** — JSON primitive (number / string / array / object / boolean).
- **Units** — SI unless stated.
- **Range** — closed range unless "[open)".
- **Update** — Cadence of regeneration.
- **Source** — Upstream authority or derivation.

---

## grid_risk.json
Per-cell expected-harm grid at 0.01deg (~1.1 km) resolution.

| Field | Type | Units | Range | Update | Source |
|-------|------|-------|-------|--------|--------|
| cell_id | string | — | `{lat10}_{lon10}_0.01` | daily | derived |
| lat, lon | number | deg WGS84 | [20,46] / [122,154] | daily | GSI |
| expected_harm | number | fractional | [0, 1] | daily | grid aggregation |
| n_incidents | integer | count | [0, infty) | daily | NPA + MLIT |
| prefecture | string | — | 47 values | static | MIC code |

## elt_japan_v1.json
Event-loss-table from 10,000-year Monte-Carlo.

| Field | Type | Units | Range | Update | Source |
|-------|------|-------|-------|--------|--------|
| event_id | string | — | `{peril}-{year}-{seq}` | quarterly | MC sim |
| annual_rate | number | 1/year | (0, 1) | quarterly | derived |
| peril | string | enum | 7 perils | quarterly | schema |
| mean_loss_jpy | number | JPY | >=0 | quarterly | LogN fit |
| cv | number | — | [0.2, 2.0] | quarterly | historical |
| footprint_cells | array[string] | cell_id | — | quarterly | GIS |
| return_period | integer | years | [1, 10000] | quarterly | 1/rate |

## tail_risk_metrics.json
VaR / CVaR tail statistics.

| Field | Type | Units | Range | Update | Source |
|-------|------|-------|-------|--------|--------|
| var_95, var_99 | number | fractional EH | [0,1] | weekly | empirical quantile |
| cvar_99, es_99 | number | fractional EH | [0,1] | weekly | empirical |
| max, min | number | fractional EH | [0,1] | weekly | grid_risk |
| max_drawdown | number | fractional | [0,1] | weekly | derived |
| n | integer | count | >=1 | weekly | grid_risk |
| tail_distribution | string | — | "generalized_pareto" | static | schema |

## statistical_metadata.json
Cell-level statistical metadata.

| Field | Type | Units | Range | Update | Source |
|-------|------|-------|-------|--------|--------|
| cell_id | string | — | cell_id | daily | derived |
| center | array[number] | [lon,lat] | — | daily | GSI |
| n | integer | count | >=0 | daily | incidents |
| bandwidth_m | number | metres | 250 (fixed) | static | Silverman |
| expected_harm | number | — | [0,1] | daily | KDE |
| expected_harm_ci95 | array[number] | — | [0,1] | daily | bootstrap |
| poisson_rate_mle | number | 1/day | [0,inf) | daily | MLE |
| poisson_wald_ci | array[number] | 1/day | [0,inf) | daily | Wald |
| model_fit.aic, .bic | number | nats | — | daily | GLM |

## climate_scenarios_rcp.json
RCP 2.6 / 4.5 / 8.5 scenario deltas for 47 prefectures.

| Field | Type | Units | Range | Update | Source |
|-------|------|-------|-------|--------|--------|
| delta_eh | number | fractional | [-0.1, 0.5] | annual | IPCC AR6 |
| delta_crime | number | fractional | [-0.05, 0.15] | annual | elasticity |
| delta_heat_days | integer | days/year | [0, 60] | annual | downscaled |
| delta_flood_freq | number | fractional | [0, 0.3] | annual | CMIP6 |
| delta_typhoon_intensity | number | fractional | [0, 0.2] | annual | CMIP6 |
| temp_delta_c | number | Kelvin | [0, 6] | annual | IPCC AR6 |

## esg_governance_metadata.json
Per-prefecture ESG mapping.

| Field | Type | Units | Range | Update | Source |
|-------|------|-------|-------|--------|--------|
| governance_safety_score | integer | index | [0,100] | annual | derived |
| crime_rate_per_1000 | number | per 1000 | [0, 20] | annual | NPA |
| sasb_mapping | array[string] | SASB code | — | static | SASB Foundation |
| gri_mapping | array[string] | GRI code | — | static | GRI |
| sdg_targets | array[string] | SDG id | 1-17 | static | UN |
| percentile_vs_oecd | integer | percentile | [0,100] | annual | OECD |
| tcfd_pillar | string | enum | 4 values | static | TCFD |

## loss_triangle_2018_2024.json
Non-life claims loss-development triangle.

| Field | Type | Units | Range | Update | Source |
|-------|------|-------|-------|--------|--------|
| accident_years | array[int] | — | 2018-2024 | annual | sim |
| development_years | array[int] | — | 0-6 | annual | schema |
| triangle_jpy | matrix[number] | JPY | >=0 | annual | sim |
| currency | string | ISO 4217 | "JPY" | static | schema |

## manifest.json / manifest.sig
Integrity manifest.

| Field | Type | Units | Range | Update | Source |
|-------|------|-------|-------|--------|--------|
| merkle_root | string | sha256 | 64 hex | every build | tree hash |
| algorithm | string | — | "sha256" | static | schema |
| files[].sha256 | string | sha256 | 64 hex | every build | CI |
| files[].size | integer | bytes | >=0 | every build | fs |
| signature_scheme | string | — | "ed25519" | static | schema |

## compound_risk_tensor.json
Joint distributions (multi-peril).

| Field | Type | Units | Range | Update | Source |
|-------|------|-------|-------|--------|--------|
| correlation_matrix | matrix[number] | Pearson r | [-1,1] | quarterly | empirical |
| joint_counts | matrix[int] | count | >=0 | quarterly | empirical |
| conditional_p_* | object | probability | [0,1] | quarterly | derived |

## audit_log_sample.ndjson
Append-only audit log (NDJSON).

| Field | Type | Units | Range | Update | Source |
|-------|------|-------|-------|--------|--------|
| ts | string | ISO 8601 | RFC3339 | every event | CI |
| event | string | enum | data_updated / manifest_signed / verified | every event | CI |
| file | string | path | — | every event | CI |
| prev_hash, hash | string | sha256 | 64 hex | every event | chain |
| actor | string | — | ci_pipeline / audit_verifier | every event | RBAC |
| merkle_root | string | sha256 | 64 hex | on sign | tree |

## Other top-level files (summary)
| File | Update | Source |
|------|--------|--------|
| all_events.json / all_events_v2.json | hourly | aggregation |
| amedas_current.json | 10-min | JMA AMeDAS |
| chikan_stats.json | annual | NPA |
| crime_safety_guide.json | static | editorial |
| crime_trends.json | monthly | NPA |
| earthquakes_latest.json | 5-min | JMA |
| events_7days.json | hourly | aggregation |
| flood_risk.json | annual | MLIT |
| glm_frequency_severity.json | quarterly | GLM fit |
| heat_*.json | daily | aggregation |
| hotspots_expected_harm.json | weekly | derived |
| impact_weighted_accounts_v1.json | annual | IWAI schema |
| jshis_hazard.json | annual | NIED J-SHIS |
| lloyds_risk_code_map.json | static | Lloyd's |
| ngfs_pathway_map.json | annual | NGFS |
| parking_tokyo.json | quarterly | MLIT |
| realtime_markers.json | 5-min | aggregation |
| sdg_mapping.json | static | UN |
| sovereign_risk_scorecard_japan.json | annual | OECD |
| tourist_areas.json | quarterly | JNTO |
| transit_disruptions.json | hourly | ODPT |
| university_presets.json | static | editorial |
| weather_warnings.json | hourly | JMA |

---
_Procurement contact: see `sources.json` for upstream licences._
