# IFRS 17 Insurance Contracts — Risk Space MCP Mapping

This document describes how the Risk Space MCP datasets map to IFRS 17
(Insurance Contracts) measurement model components. It is intended for
insurer actuarial teams building the General Measurement Model (GMM) or
Premium Allocation Approach (PAA) under IFRS 17.

## 1. Contract Boundaries (IFRS 17.34)

Contract boundaries define the period during which the insurer can
compel the policyholder to pay premiums or has a substantive
obligation to provide services.

| IFRS 17 concept | Risk Space data source | Usage |
|---|---|---|
| Policy term / tenor | `elt_japan_v1.json`.term | Defines projection horizon |
| Repricing frequency | `sources.json`.update_frequency | Determines break-point for substantive rights |
| Catastrophe exposure window | `climate_scenarios_rcp.json` | RCP scenario horizon aligns contract boundaries |

## 2. Fulfilment Cash Flows (FCF) — IFRS 17.33

FCF = PV(future cash flows) + Risk Adjustment.

### 2.1 Expected Future Cash Flows

Probability-weighted mean of cash outflows for claims and expenses.

| FCF component | Risk Space source | Notes |
|---|---|---|
| Claim frequency (λ) | `glm_frequency_severity.json`.frequency | Poisson/NegBin per prefecture |
| Claim severity (μ) | `glm_frequency_severity.json`.severity | Gamma/Lognormal |
| Aggregate expected loss | `elt_japan_v1.json`.expected_loss | ELT mean |
| Expected harm (bodily) | `compound_risk_tensor.json`.expected_harm | For liability LoBs |
| CAT loss distribution | `cat_bond_pricing.json` | Tail beyond attachment |

Projection: CF_t = λ_t × μ_t × exposure_t, discounted using the
IFRS 17 yield curve (locked-in for CSM unlock, current for FCF).

### 2.2 Discount Rates (IFRS 17.36)

Bottom-up approach: risk-free (JGB curve) + illiquidity premium.
`Risk Space` does not publish yield curves — source from BOJ / JPX.

## 3. Risk Adjustment for Non-Financial Risk (IFRS 17.37)

The compensation an entity requires for bearing uncertainty about
amount and timing of cash flows arising from non-financial risk.

### 3.1 Calibration from Risk Space statistical_metadata

```
RA = VaR_α(Loss) - E(Loss)        (Value-at-Risk method)
RA = CTE_α(Loss) - E(Loss)        (Conditional Tail Expectation / TVaR)
RA = σ(Loss) × k                   (Cost-of-Capital, k ~ 6%)
```

Our `statistical_metadata` block in each dataset carries:

| Field | IFRS 17 use |
|---|---|
| `confidence_interval_95` | α=95% VaR calibration |
| `std_error` | Cost-of-capital sigma |
| `posterior_variance` (Bayesian datasets) | Full distributional RA |
| `quantiles.p75 / p90 / p99` | Confidence-level disclosure |

Target confidence level (IFRS 17.119) is typically 75-85% for P&C lines.

### 3.2 Release Pattern

RA releases over the coverage period in proportion to the expected
claim occurrence profile (from `heat_crime.json` temporal heatmaps).

## 4. Contractual Service Margin (CSM) — IFRS 17.38

CSM = Premium − FCF (at initial recognition), floored at zero.

### 4.1 Inputs from Risk Space

| CSM input | Source |
|---|---|
| Expected premium (pricing proxy) | `reinsurance_pricing.json`.rate_on_line |
| Initial FCF estimate | Sections 2 & 3 above |
| Coverage units (for CSM release) | Exposure × time from `grid_risk.json` |
| Locked-in discount rate | External (BOJ curve at recognition) |

### 4.2 CSM Unlock Triggers

Changes in non-financial assumptions (frequency/severity) unlock CSM.
Our quarterly dataset refresh provides the unlock cadence signal.

## 5. Loss Component (Onerous Contracts) — IFRS 17.47

When FCF > Premium at recognition, a Loss Component is established
and expensed immediately.

### 5.1 Identifying Onerous Groups

Use `prefecture_risk_scores` (from `grid_risk.json`) to stress-test
whether pricing covers FCF. Prefectures with `expected_harm` above
the 90th percentile and rate adequacy < 1.0 flag onerous status.

### 5.2 Subsequent Reversal

If frequency trends decline (`crime_trends.json` shows negative
slope), Loss Component reverses through P&L.

## 6. Reinsurance Held — IFRS 17.60-70

Asymmetric treatment: reinsurance recoveries are a separate asset.
Match using `reinsurance_pricing.json` treaty structures.

## 7. Disclosure Mapping (IFRS 17.93-132)

| Disclosure | Risk Space source |
|---|---|
| Confidence level of RA | `statistical_metadata.confidence_interval_95` |
| Sensitivity analysis | `eiopa_stress_test.json` |
| Risk concentrations | `grid_risk.json` prefecture breakdown |
| Claims development | `loss_triangle` (basel_iii_op_risk.json) |

## 8. Transition

For Full Retrospective Approach, historical data from 2019-onwards
available in `all_events.json` / `elt_japan_v1.json` versioning.

## References

- IFRS 17 Insurance Contracts (IASB, 2017, amended 2020)
- `methodology.md` — Risk Space statistical methodology
- `solvency_ii_mapping.md` — Parallel Solvency II mapping
- `cat_bond_pricing.json`, `reinsurance_pricing.json`, `elt_japan_v1.json`
