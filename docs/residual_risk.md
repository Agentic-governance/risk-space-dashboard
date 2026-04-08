# Residual Risk Statement (ISO 31000)

Version: 1.0 (2026-04-09)
Status: Approved for publication

---

## 1. Risk Appetite Statement

This system identifies **relative risk**, not absolute safety. A low Expected
Harm (EH) value does **not** guarantee the absence of danger; it indicates
that, based on available historical and real-time data, the location has a
lower observed risk profile compared to other measured locations.

**Risk Space MCP is an informational tool, not a safety guarantee.**

Users should:
- Treat all risk scores as relative rankings, not absolute probabilities
- Continue to exercise personal judgement regardless of displayed risk levels
- Not rely solely on this system for safety-critical decisions
- Understand that "safe" areas can still experience incidents

---

## 2. Residual Risks

The following risks remain after all implemented controls and cannot be fully
mitigated by the current system:

### 2.1 Data Coverage Gaps

| Gap | Impact | Mitigation |
|-----|--------|------------|
| **25 prefectures** report only municipality-level aggregates | Point locations are synthetic (sampled uniformly within municipality polygon), inflating local uncertainty | Cells flagged `synthetic: true`; users warned in methodology |
| **Unreported crimes** (chikan, DV, sexual crimes) | True risk underestimated; NPA estimates ~14% reporting rate for chikan | Documented bias; cannot correct without survey data |
| **Rural areas** with few events | Low density -> model shows low risk, which may reflect lack of reporting rather than true safety | Confidence intervals widen; noted in data dictionary |
| **Night-time hours** (00:00-05:00) | Fewer reports but not necessarily fewer incidents (victims asleep, reduced witnesses) | Temporal multiplier partially compensates but is literature-based |

### 2.2 Emerging Threats

| Threat | Description |
|--------|-------------|
| **Novel crime patterns** | New MO (modus operandi) not present in historical data will not appear until reported and ingested |
| **Infrastructure changes** | New construction, road closures, or demolished safe havens not reflected until next data refresh |
| **Policy shifts** | Changes in patrol routes, police staffing, or reporting practices cause sudden model drift |
| **Seasonal anomalies** | Unusual weather events or unprecedented crowd gatherings exceed historical ranges |
| **Cyber-physical threats** | GPS spoofing, fake reports, or coordinated misinformation campaigns |

### 2.3 Model Limitations

| Limitation | Residual Impact |
|------------|----------------|
| KDE bandwidth mismatch (250m documented vs ~1km implemented) | Hotspot resolution is coarser than documented; may under-detect micro-scale risk clusters |
| Expert-estimated P(escape) weights | Haven effectiveness not empirically validated; actual escape probability may differ |
| No formal hold-out validation (v1.0) | PAI, PEI, hit rate, and Brier score are targets, not measured values |
| Static severity mapping | Severity scores do not account for context (time, location, victim profile) |

---

## 3. Risk Acceptance Criteria

| Criterion | Threshold | Current Status |
|-----------|-----------|----------------|
| Data freshness | Realtime events < 24 hours old | Met (30-min scrape cycle) |
| Geographic coverage | >= 22 prefectures with chome-level data | Met (22 prefectures) |
| Model transparency | Methodology publicly documented | Met (methodology.md) |
| Bias disclosure | All known biases documented | Met (this document + methodology.md) |
| Confidence intervals | 95% CI published for grid cells | Partially met (statistical_metadata.json) |
| User warnings | Dashboard displays data limitations | Met (freshness banner, methodology link) |
| Version control | Model version + data version tracked | Met (_version.json + CHANGELOG.md) |

---

## 4. Residual Risk Monitoring

The following processes are in place to monitor and reduce residual risk:

1. **Data freshness banner** -- Dashboard displays warning when data exceeds 7 days
2. **Version tracking** -- `_version.json` and `CHANGELOG.md` record all data updates
3. **Audit log** -- `audit_log_sample.ndjson` provides cryptographically chained event history
4. **Signed manifests** -- `manifest.sig` enables integrity verification of all data files
5. **Community reporting** -- Dashboard includes incident reporting mechanism

---

## 5. Disclaimer

This risk assessment tool is provided "as is" without warranty of any kind.
The operators, contributors, and data providers accept no liability for
decisions made based on this system's outputs. Users assume full
responsibility for their interpretation and use of the displayed information.

For safety-critical applications (e.g., child safety route planning, insurance
underwriting, urban planning), this system should be used as **one input among
many**, supplemented by professional judgement, local knowledge, and
on-the-ground verification.

---

*Last reviewed: 2026-04-09*
*Next review: 2026-07-09 (quarterly)*
