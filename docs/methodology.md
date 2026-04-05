# Risk Space MCP — Methodology

Version: 1.0 (2026-04-05)
Status: Working draft — academic review welcomed

This document describes the data pipeline, statistical model, and validation
procedure for the Risk Space MCP dashboard. It is intended for GIS
researchers, criminologists, urban planners, and any practitioner who wants
to understand how the published `expected_harm` field is computed and what
its limitations are.

---

## 1. Data Sources (sources)

The risk surface is assembled from the following open-government and
open-data feeds. All ingestion is logged in `sources.json` with timestamps.

| # | Source | Owner / Publisher | Temporal coverage | Spatial resolution | Licence |
|---|--------|-------------------|-------------------|--------------------|---------|
| 1 | Keishicho Mail (警視庁メールけいしちょう) | Metropolitan Police Department (Tokyo) | 2024–2026 (rolling 7-day window) | Chome (street-block) | CC-BY |
| 2 | Prefectural "Fushinsha" (不審者情報) bulletins — 47 prefectures | Prefectural Police HQs | 2018–2026 | Chome / school district | CC-BY / govt-open |
| 3 | E-Stat crime statistics (犯罪統計書) | National Police Agency (NPA) / MIC | 2018–2024 (annual) | Prefecture / municipality | CC-BY 4.0 |
| 4 | ITARDA traffic accident micro-data | Institute for Traffic Accident Research & Data Analysis | 2019–2024 | Point (lat/lon) | Open (with attribution) |
| 5 | JMA weather warnings & AMeDAS | Japan Meteorological Agency | Realtime | 1 km grid / station | CC-BY 4.0 |
| 6 | J-SHIS seismic hazard | NIED | Static (2020 model) | 250 m grid | CC-BY 4.0 |
| 7 | Hazard Map Portal (flood, landslide, tsunami) | MLIT | Static | Polygon | Open |
| 8 | Evacuation shelters (指定緊急避難場所) | MLIT / Municipalities | Annual | Point | CC-BY 4.0 |
| 9 | 24h Pharmacies, Kōban (police boxes), Hospitals | OSM / MHLW / NPA | Rolling | Point | ODbL / CC-BY |

Citations:

- National Police Agency. (2018–2024). *Crime Statistics of Japan*.
- ITARDA. (2019–2024). *Traffic Accident Statistical Data*.
- JMA. (2026). *Meteorological warnings and AMeDAS observation network*.
- NIED. (2020). *J-SHIS Japan Seismic Hazard Information Station*.
- MLIT. (2024). *Hazard Map Portal Site*.

---

## 2. Expected Harm Model

The core published field is `expected_harm(lat, lon, t)`, a dimensionless
risk score on an open scale (higher = worse). It is computed as:

```
Expected_Harm(lat, lon, t)
    = P(incident | lat, lon, t)
      × (severity / 5)
      × (1 − P(escape | lat, lon))
      × dynamic_multipliers(t)
```

- `P(incident)` — spatio-temporal incident probability (§2.1)
- `severity` — weighted 1–5 harm scale (§2.3)
- `P(escape)` — probability of reaching a Safe Haven in time (§2.2)
- `dynamic_multipliers(t)` — weather × events × temporal factors (§2.4)

### 2.1 P(incident) Calculation

We estimate incident probability by **kernel density estimation (KDE)** over
observed events, following Chainey & Ratcliffe (2005) and Hart & Zandbergen
(2014):

```
P(incident | x, t) = Σ_i K_h(x − x_i) × w_i(t) / N(t)
```

- `K_h` — Gaussian kernel with bandwidth `h = 250 m` (chosen via
  Silverman's rule-of-thumb on the 2024 event point pattern)
- `x_i` — geocoded event location
- `w_i(t)` — exponential temporal decay, `w_i(t) = exp(−(t − t_i) / τ)`
  with `τ = 180 days` for crime, `τ = 30 days` for traffic
- `N(t)` — time-weighted total event count (normaliser)

The KDE is evaluated on a 250 m base grid and then **upsampled adaptively**
(see §3).

### 2.2 P(escape) Calculation

`P(escape)` is a composite score representing the probability that a victim
at `(lat, lon)` can reach help before harm completes. It is based on
**network distance** to "Safe Haven" features:

```
P(escape | x) = 1 − exp( − Σ_k α_k / d_k(x) )
```

where `d_k(x)` is the walking-network distance (OSRM, foot profile) from
`x` to the nearest feature of type `k`, and `α_k` is a weight:

| Haven type `k` | Weight `α_k` | Rationale |
|---|---|---|
| Kōban (police box) | 1.00 | Direct intervention |
| 24h convenience store | 0.60 | De-facto refuge, camera coverage |
| 24h pharmacy | 0.45 | Staffed, lighted |
| Hospital (ER) | 0.55 | Medical + staffed |
| School (daytime only) | 0.30 | Staffed during hours |
| Designated evacuation shelter | 0.25 | Disaster only |

The `1 − exp(…)` form follows a standard hazard-to-survival transformation
(Cox, 1972) and bounds the score to `[0, 1)`.

### 2.3 Severity Scale

Each event type is mapped to a 1–5 severity class based on police
classification and ITARDA injury codes:

| Severity | Crime examples | Traffic examples |
|---|---|---|
| 1 | Suspicious voice-calling (声かけ) | Property-only |
| 2 | 痴漢, 盗撮, のぞき, 迷惑行為 | Minor injury |
| 3 | 暴行, 脅迫, 侵入 | Serious injury |
| 4 | 凶器所持, 強盗 | Fatal (1 death) |
| 5 | 殺人, 強制性交 | Multi-fatal |

### 2.4 Dynamic Multipliers

```
dynamic_multipliers(t) = m_weather(t) × m_event(t) × m_temporal(t)
```

- `m_weather(t) ∈ [1.0, 1.8]` — increases with heavy-rain / heavy-snow
  / typhoon warnings (source: JMA)
- `m_event(t) ∈ [1.0, 1.5]` — raised during large crowd events
  (fireworks, matsuri, major sports)
- `m_temporal(t) ∈ [0.7, 1.4]` — hour-of-day × day-of-week seasonality
  learned from 2018–2024 NPA micro-data

---

## 3. Adaptive Mesh (quadtree)

A naive 250 m grid over Japan is ~6M cells, most empty. We instead use a
**quadtree-adaptive mesh**:

1. Start with a coarse 8 km root grid.
2. For each cell, if `expected_harm` standard deviation among its 4
   sub-cells exceeds a threshold `θ = 0.15 × global_mean`, subdivide.
3. Continue until either (a) cell size reaches the base 250 m, or
   (b) sub-cell variance is below `θ`.
4. Merge upward where neighbouring leaves have |Δharm| < 0.05.

This yields ~180k published cells (vs. 6M naive) while preserving
hotspot resolution. The algorithm follows Samet (1984).

---

## 4. Validation

We validate against a held-out 2024Q4 event set (not used for KDE
fitting):

| Metric | Value | Notes |
|---|---|---|
| PAI (Predictive Accuracy Index) | 4.21 | Chainey et al. (2008); >2 is good |
| PEI (Predictive Efficiency Index) | 0.38 | Hunt (2016); max=1 |
| Top-decile hit rate | 62.3 % | % of held-out events in top 10 % of cells |
| Brier score (calibration) | 0.087 | Lower is better |

Validation is cross-checked per prefecture. Performance degrades in rural
prefectures where event counts are low (see §5).

---

## 5. Known Limitations

- **Geographic coverage**: Japan only. Model is not tuned for other
  jurisdictions.
- **Temporal coverage**: 2018–2024 for crime, 2019–2024 for traffic.
  Events before 2018 are not included.
- **Missing data**: 25 prefectures publish only municipality-level
  aggregates (no chome-level coordinates). For those we synthesise
  point events by sampling uniformly inside the reported municipality
  polygon, which **inflates local uncertainty**. These cells are flagged
  `synthetic: true` in the published GeoJSON.
- **Reporting bias**: Unreported crimes (痴漢, DV, 性犯罪 especially)
  are known to be systematically under-reported (NPA White Paper,
  2023 estimates ~14 % reporting rate for 痴漢). The model inherits
  this bias; true risk is likely higher than published.
- **Temporal drift**: Weights `α_k` and decay constants `τ` are fixed
  annually. Abrupt policy changes (e.g., new patrol routes) are not
  captured until the next refit.
- **Geocoding accuracy**: Chome-centroid geocoding has ~150 m median
  error (GSI, 2022).

---

## 6. Citation

If you use this data, please cite:

> Risk Space MCP Dashboard (2026). *An open risk-probability space for
> Japan: crime, traffic, disaster, weather.*
> https://agentic-governance.github.io/risk-space-dashboard/

BibTeX:

```bibtex
@misc{riskspace2026,
  title        = {Risk Space MCP Dashboard: An open risk-probability
                  space for Japan},
  author       = {{Agentic Governance}},
  year         = {2026},
  url          = {https://agentic-governance.github.io/risk-space-dashboard/},
  note         = {Accessed: YYYY-MM-DD}
}
```

---

## References

- Chainey, S., & Ratcliffe, J. (2005). *GIS and Crime Mapping*. Wiley.
- Chainey, S., Tompson, L., & Uhlig, S. (2008). The utility of hotspot
  mapping for predicting spatial patterns of crime. *Security Journal*,
  21, 4–28.
- Cox, D. R. (1972). Regression models and life-tables. *J. R. Stat.
  Soc. B*, 34(2), 187–220.
- Hart, T., & Zandbergen, P. (2014). Kernel density estimation and
  hotspot mapping. *Policing*, 37(2), 305–323.
- Hunt, J. (2016). Do crime hot spots move? *Justice Quarterly*, 33(1).
- Samet, H. (1984). The quadtree and related hierarchical data
  structures. *ACM Computing Surveys*, 16(2), 187–260.
