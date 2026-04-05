# TCFD Report — Risk Space MCP

**Version**: 1.0.0
**Reporting period**: 2026-Q1
**Frameworks**: TCFD (2017), ISSB IFRS S2, TNFD draft
**Data source**: `docs/data/climate_scenarios_rcp.json`, `docs/data/grid_risk.json`

---

## 1. Governance

Risk oversight is structured around a three-line model for climate-related
physical and transition risk stemming from the Risk Space MCP platform.

| Line | Body | Responsibility |
|------|------|----------------|
| Board | Risk & Data Ethics Committee | Quarterly review of scenario exposure, sign-off on risk appetite |
| 1st line | Data Engineering | Ingest RCP scenario deltas, maintain `climate_scenarios_rcp.json` freshness |
| 2nd line | Quant Risk | Validate elasticities (EH 0.035/degC, flood 0.08/degC) |
| 3rd line | Internal Audit | Annual review of Merkle manifest signing, audit log integrity |

- **Cadence**: Board reviews climate KPIs quarterly; management reviews monthly.
- **Escalation**: If `delta_eh` for any prefecture under RCP8.5-2050 exceeds
  +10%, an alert is raised to the Risk Committee within 5 business days.
- **Incentives**: Data Engineering bonus pool tied to manifest signature
  verification success rate (target >=99.5%).

## 2. Strategy

### 2.1 Physical risk — time-dependent
Physical-risk exposure is quantified by delta expected-harm (`delta_eh`)
applied to the baseline grid (`grid_risk.json`, 2020 baseline).

| Scenario | 2030 national mean dEH | 2050 | 2100 |
|----------|------------------------|------|------|
| RCP2.6   | +2.8%                  | +4.0% | +4.6% |
| RCP4.5   | +3.0%                  | +5.1% | +7.8% |
| RCP8.5   | +3.4%                  | +7.1% | +13.2% |

(Values from `climate_scenarios_rcp.json`, averaged across 47 prefectures.)

### 2.2 Transition risk
- **Regulatory**: Tightening of ISSB disclosure (IFRS S2) may require
  grid-level Scope 3 linkage by 2027. Our `esg_governance_metadata.json`
  already maps SASB / GRI / SDG tags.
- **Market**: Insurance re-pricing of NatCat exposure may compress
  Solvency II capital buffers; see `docs/solvency_ii_mapping.md`.
- **Reputation**: Mis-signed manifest or audit-log breach would impair
  trust. Mitigation: ed25519 signature + Merkle tree (see
  `manifest.sig`).

### 2.3 Resilience
Stress test under RCP8.5-2100 lifts national 99%-VaR of EH from
0.0756 to approximately 0.0856, still within the internal tolerance
threshold of 0.10.

## 3. Risk Management

### 3.1 Identification
- Perils enumerated in `elt_japan_v1.json`: crime_property, crime_violent,
  traffic_major, disaster_flood, disaster_quake, weather_typhoon,
  weather_heat.
- New perils added via schema-versioned pull requests.

### 3.2 Assessment
- Frequency: empirical annual-rate from 10,000-year Monte Carlo
  simulation (`elt_japan_v1.json` → 1,000 events).
- Severity: Log-Normal(mean, cv).
- Tail metrics: `tail_risk_metrics.json` (VaR/CVaR at 95%, 99%).

### 3.3 Integration
Climate deltas from `climate_scenarios_rcp.json` are injected into the
pricing pipeline via `risk * (1 + delta_eh[scenario][horizon])`.
Results flow into `impact_weighted_accounts_v1.json` for ESG reporting.

## 4. Metrics & Targets

KPIs derived directly from `climate_scenarios_rcp.json`:

| KPI | Unit | 2030 target (RCP2.6) | 2050 limit (RCP4.5) |
|-----|------|-----------------------|----------------------|
| Delta EH (national) | fractional | <= 0.030 | <= 0.055 |
| Delta crime | fractional | <= 0.015 | <= 0.025 |
| Delta heat days (Tokyo) | days/year | <= 8 | <= 15 |
| Delta flood frequency | fractional | <= 0.08 | <= 0.12 |
| Delta typhoon intensity | fractional | <= 0.05 | <= 0.09 |
| Temperature delta | degC | <= 1.0 | <= 1.8 |

**Governance targets**
- Merkle verification success rate: >= 99.5% (monthly)
- Audit-log completeness: 100% of `data_updated` events logged
- Manifest signing latency: <= 60 seconds post-build

---
_Generated 2026-04-05. Source of truth: `climate_scenarios_rcp.json` v1.0.0._
