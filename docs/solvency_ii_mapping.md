# Solvency II QRT Mapping — Risk Space MCP

**Version**: 1.0.0
**Regulatory framework**: Solvency II Directive 2009/138/EC, QRT 2023 taxonomy
**Purpose**: Map Risk Space MCP data assets to Solvency II Quantitative
Reporting Templates for non-life (re)insurance users.

---

## Template-level mapping

### S.26.01 — SCR Non-Life Catastrophe Risk
**Coverage**: Natural catastrophe sub-module.

| QRT line | Peril | Risk Space MCP source | Notes |
|----------|-------|-----------------------|-------|
| C0020 (Windstorm) | Typhoon | `elt_japan_v1.json` peril=weather_typhoon | Use `annual_rate` x `mean_loss_jpy` |
| C0030 (Earthquake) | Quake | `elt_japan_v1.json` peril=disaster_quake; `jshis_hazard.json` | PGA-consistent footprint cells |
| C0040 (Flood) | Flood | `elt_japan_v1.json` peril=disaster_flood; `flood_risk.json` | Depth bands drive severity curve |
| C0050 (Hail) | Heat / convective | `heat_weather.json` | Proxy — hail not explicit |
| C0060 (Subsidence) | n/a | — | Not modelled |
| C0070 (Man-made: Fire) | — | — | Outside scope |
| Aggregate 200-year loss | All NatCat | `tail_risk_metrics.json` `var_99`, `cvar_99` | National and prefectural |

**SCR formula link**: For EEA-equivalent stress at 200y return,
use `return_period >= 200` filter on ELT + CVaR99 aggregation.

### S.27.01 — SCR Operational Risk (proxies)
Although S.27.01 is a formula-based module, the platform supplies
operational-loss-frequency proxies derived from crime and traffic data.

| Proxy | Source file | Field |
|-------|-------------|-------|
| External fraud frequency | `crime_trends.json` | trend by prefecture |
| Physical-asset damage freq | `heat_car_breakin.json` | cell counts |
| Traffic incidents (fleet) | `heat_traffic.json` | counts, severity |
| Business disruption index | `transit_disruptions.json` | duration-weighted |

These proxies feed the **BSCR Op-Risk loading** as a scale multiplier
when the undertaking carries material automobile / property portfolios.

### S.28.01 — MCR Life Underwriting
**NOT APPLICABLE.** Risk Space MCP is a non-life, perils-oriented
dataset and contains no biometric, longevity, or morbidity data.

### S.19.01 — Non-Life Insurance Claims (Loss Triangles)
| QRT column | MCP file | Field |
|------------|----------|-------|
| Accident year | `loss_triangle_2018_2024.json` | `accident_years` |
| Development year | same | `development_years` |
| Gross incurred (JPY) | same | `triangle_jpy` matrix |
| Currency | same | `metadata.currency` = JPY |

**Chain-ladder**: Apply CL factors to `triangle_jpy` to derive
ultimate losses; feed into S.19.01.01.01 (Gross Claims Paid Triangle).

## Data lineage & audit
- Input provenance: `manifest.json`, signed via `manifest.sig`
  (ed25519 placeholder, SHA-256 Merkle root).
- Audit trail: `docs/data/audit_log_sample.ndjson`.
- Reproducibility: every QRT cell computed from MCP files is
  reconstructable via the hash recorded in the audit log.

## Implementation notes
1. Undertakings should reconcile `currency=JPY` conversion before
   integrating into Solvency II QRTs (reported in local reporting
   currency, typically EUR).
2. The "Aggregate 200-year loss" figure from `tail_risk_metrics.json`
   is computed at 99% CVaR and assumes empirical GPD tail fit — adjust
   if a heavier-tailed distribution is used internally.
3. S.27.01 proxies are **not a substitute** for the standard-formula
   op-risk calculation; they are advisory.

---
_Generated 2026-04-05. For regulatory use validate against
EIOPA Taxonomy 2.8.x._
