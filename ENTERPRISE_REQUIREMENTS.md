# Risk Space MCP -- Enterprise Requirements Analysis

10 demanding professionals evaluated the 3,876-line dashboard (`dashboard/index.html`) for enterprise/business use. This document captures what works, what is critically missing, data quality concerns, and prioritized action items for each persona.

---

## Part A: Business Personas (B1--B5) -- Child Safety Service Providers

---

### B1: SECOM -- Head of Mimamori Service Planning (50M)

**Use Case**: API integration with existing SECOM safety confirmation services; GPS device data mashup with risk fields.

#### What Currently Works
1. **Mimamori mode** exists with location registration, route evaluation, and EH scoring for each registered point.
2. **EH (Expected Harm) formula** `P(incident) x Severity x (1 - P(escape))` provides a quantifiable risk metric that could be relayed to parents.
3. **Safe Haven data** (koban, convenience stores, hospitals, fire stations) with 24H flags enables "nearest safe place" functionality useful for GPS-linked alerting.
4. **Real-time suspicious person layer** with 5-minute auto-refresh gives live situational awareness.
5. **Morning briefing** feature generates route-level safety summaries with fushinsha counts.

#### What Is CRITICALLY Missing
1. **No REST API / MCP endpoint exists.** The dashboard is a standalone HTML file loading local JSON files. There is no `GET /api/v1/risk_field?lat=...&lon=...` endpoint. SECOM cannot integrate without an API.
2. **No SLA definition.** Zero documentation on uptime commitments, response time guarantees, or failover architecture. The `schema.md` mentions Cloudflare Workers + R2 but nothing is deployed.
3. **No data reliability attestation.** The Merkle verification (`manifest.sig`) is a good start but (a) it only checks file integrity, not data accuracy, and (b) there is no third-party audit trail or chain-of-custody documentation.
4. **No fallback mechanism.** If the data source (JMA, NPA, etc.) is down, the dashboard shows nothing. No cached-last-known-good, no degraded-mode, no health endpoint.
5. **Cannot say "your child is safe right now."** The EH value is a statistical estimate based on historical crime counts + time/weather multipliers. It is NOT a real-time safety confirmation. There is no GPS track integration, no geofencing API, no push notification backend.

#### Data Quality / Completeness Concerns
- Crime data is yearly CSV from Keishicho (Tokyo only). National coverage requires 47 prefectural sources -- `prefectural_sources.json` exists but most are flagged as unacquired.
- `source.missing_rate` field exists in schema but is never populated in the dashboard computation.
- Weather multiplier is a hardcoded heuristic (`TM()` function), not a validated statistical model.
- Suspicious person data comes from scraping (Gakkom Navi / police HP) -- no guaranteed update latency SLA.

#### Top 3 Action Items
1. **Build a production REST API** on Cloudflare Workers with documented endpoints matching `schema.md` MCP tools (`get_risk_field`, `get_hotspots`, `get_signals`). Include rate limiting, API key auth, and health check endpoint.
2. **Define and publish SLA document**: uptime target (99.9% minimum, 99.99% aspirational), p95/p99 latency targets, data freshness guarantees per layer, and incident response procedures.
3. **Implement GPS integration protocol**: WebSocket or Server-Sent Events endpoint that accepts device position streams and returns real-time risk assessment + nearest haven + alert triggers.

---

### B2: ALSOK -- School Safety DX Team (40F)

**Use Case**: SaaS for 3,000 contracted schools; multi-tenant with per-school views; education board reporting.

#### What Currently Works
1. **School radius filter** (500m/1km) counts suspicious person reports near selected schools.
2. **School data integration** (`schools_tokyo.json`) with Overpass format parsing.
3. **CSV/JSON/GeoJSON/PDF export** enables basic reporting workflows.
4. **Commute path safety evaluation** with fushinsha overlay along home-school routes.
5. **Time-window scheduling** for routes (e.g., 07:00-08:30 Mon-Fri "commute") with notification triggers.

#### What Is CRITICALLY Missing
1. **No multi-tenancy.** The entire app runs in a single browser with localStorage. There is no user authentication, no school-level access control, no tenant isolation.
2. **No server-side data persistence.** All mimamori data (locations, routes, settings) is in `localStorage`. If a teacher clears their browser, everything is lost. No database, no sync.
3. **No automated reporting.** PDF generation is minimal (jsPDF with 4 lines of text). No monthly safety report template, no education board format compliance, no scheduled delivery.
4. **No administrative dashboard.** No way for ALSOK to see aggregated stats across 3,000 schools, identify highest-risk schools, or track improvement trends.
5. **National coverage is incomplete.** School data exists only for Tokyo (`schools_tokyo.json`). ALSOK operates nationwide.

#### Data Quality / Completeness Concerns
- Grid tile data (`grid_tiles/`) coverage is unclear -- only certain lat/lon tiles may exist.
- Update frequency for realtime data is "5 minutes" but this is client-side polling, not server-push.
- No data versioning -- if a tile file is updated, there's no way to know without refetching.

#### Top 3 Action Items
1. **Design multi-tenant architecture**: school ID-based data partitioning, role-based access (teacher, principal, education board), SSO integration (SAML/OIDC for education systems).
2. **Build server-side persistence layer**: PostgreSQL/PostGIS backend for school profiles, registered routes, alert history, and reporting data. Migrate from localStorage.
3. **Create automated reporting pipeline**: Monthly PDF/Excel report per school with trend analysis, incident counts, risk delta, compliance checklist. Scheduled delivery via email/webhook.

---

### B3: SoftBank -- IoT Platform (35M)

**Use Case**: Real-time risk overlay for 10M Mimamori Keitai / Kids Phone devices; sub-100ms latency; 5G MEC.

#### What Currently Works
1. **Lightweight client architecture** -- single HTML file with Leaflet.js, no heavy framework dependencies.
2. **Tile-based data loading** (`haven_tiles/`, `grid_tiles/`) enables spatial partitioning that could map to edge caching.
3. **Geolocation API integration** (`geolocateUser()`) with instant safety check overlay.
4. **Real-time data refresh** (5-minute interval) with incremental updates (`realtime_slim.json`).

#### What Is CRITICALLY Missing
1. **No server-side API.** Everything is client-side file fetching. Cannot handle 10M concurrent device queries against JSON files.
2. **No edge computing architecture.** No CDN strategy, no MEC deployment plan, no gRPC/protobuf for low-overhead transport.
3. **Latency is undefined.** The dashboard loads entire tile JSONs (potentially hundreds of KB). No spatial indexing at the API level (S2 cells, geohash). p99 < 100ms is impossible with current architecture.
4. **No device protocol support.** Kids phones use proprietary positioning protocols. No MQTT, CoAP, or lightweight binary protocol support.
5. **No batch/streaming API.** For 10M devices, individual HTTP requests are not viable. Need bulk position evaluation endpoint or streaming protocol.

#### Data Quality / Completeness Concerns
- Grid cell resolution varies (`resolution` field in data). Some cells are 250m, some are adaptive. Inconsistent precision for sub-100ms queries.
- Haven data is loaded lazily per tile. A device at a tile boundary may get incomplete results.
- No load testing data. Unknown behavior at scale.

#### Top 3 Action Items
1. **Design edge-native API**: S2 cell-indexed risk lookup with precomputed risk values at multiple zoom levels. Deploy to Cloudflare Workers (296+ edge locations) or MEC nodes. Target: single GET returns risk in <50ms.
2. **Implement binary protocol**: Protocol Buffers schema for risk field responses. Support bulk evaluation (POST array of lat/lon, return array of risk scores). Target: 1000 evaluations per request.
3. **Build capacity planning model**: Load test with simulated 10M device positions. Determine shard/partition strategy, cache TTL, and write-through invalidation for real-time data updates.

---

### B4: Sompo Japan -- School Insurance Product Design (38F)

**Use Case**: Regional risk scores for insurance premium differentiation; actuarial-level statistical validation; 10-year claims correlation.

#### What Currently Works
1. **EH (Expected Harm) value** provides a continuous risk metric suitable as an insurance rating factor input.
2. **Safety rank (S/A/B/C/D)** creates natural risk tiers for premium bands.
3. **Monte Carlo 5-year forecast** with GBM (geometric Brownian motion) shows probabilistic future risk paths.
4. **Enterprise overlay** includes ELT (Event Loss Table), VaR/CVaR tail risk metrics, and Basel III ORC data -- all directly relevant to actuarial work.
5. **Statistical metadata** (`statistical_metadata.json`) with confidence intervals (`expected_harm_ci95`) exists.
6. **Cat bond pricing data** and sovereign risk scorecard provide macro risk context.

#### What Is CRITICALLY Missing
1. **No backtesting.** The Monte Carlo model uses hardcoded parameters (drift=-3%, vol=10%). No comparison against actual historical outcomes. No model validation report.
2. **No actuarial certification.** No credentialed actuary has reviewed the models. No peer review. No SOA/IAJ sign-off.
3. **No claims data integration.** Schema has no field for insurance claim/loss data. Cannot correlate risk scores with actual claim frequencies without this.
4. **No regulatory documentation.** FSA (Financial Services Agency) requires documented model governance for any pricing model. No Model Risk Management (MRM) documentation, no SR 11-7 compliance artifacts.
5. **GBM model is naive.** Crime rates don't follow log-normal distributions. Need Poisson/negative binomial for count data, regime-switching for structural breaks (e.g., COVID impact on crime).

#### Data Quality / Completeness Concerns
- Only 1 year of granular crime data (2024 Keishicho CSV). Actuaries need 10+ years minimum.
- e-Stat data exists for national trends but not at the granularity (chome level) needed for insurance rating.
- The `severity` mapping (1-5) is a rough heuristic, not an insured loss severity curve.
- No exposure data (population counts by age group per mesh) to normalize risk rates.

#### Top 3 Action Items
1. **Build actuarial data package**: 10-year crime/accident data at city/ward level, normalized by population and exposure. Include loss development triangles and claim frequency/severity distributions.
2. **Implement proper statistical models**: Replace GBM with Poisson regression for crime frequency, generalized Pareto for severity tail. Add backtest framework comparing predicted vs. actual over holdout periods.
3. **Prepare FSA submission package**: Model documentation per SR 11-7 guidelines, independent validation report, sensitivity analysis, and stress test results. Engage credentialed actuary for sign-off.

---

### B5: Benesse -- Commute Safety Information Service (42M)

**Use Case**: Widget for 6M household parent app; age-filtered risk; "weekly safety news" content generation.

#### What Currently Works
1. **4-language support** (JA/EN/ZH/KO) covers major parent demographics including foreign residents.
2. **Tourist area safety cards** provide content-ready area-level safety summaries.
3. **Advice panel** generates contextual safety text (safe/caution/warning/danger with specific guidance).
4. **24H risk chart** and donut chart (suspicious activity types) are embeddable visualizations.
5. **Simplified mode** (grandparent-friendly) with large UI, voice readout, and SOS button demonstrates content adaptability.
6. **Share/QR code** functionality enables easy distribution.

#### What Is CRITICALLY Missing
1. **No widget/embed API.** The dashboard is a full-page application. No iframe-embeddable component, no Web Component, no JavaScript SDK for embedding a risk badge in a third-party app.
2. **No age-based risk filtering.** All risk is computed identically regardless of whether the subject is a 6-year-old first-grader or a 15-year-old high-schooler. Schema has no `victim_age_group` field. Risk profiles differ dramatically by age.
3. **No content generation pipeline.** "Weekly safety news" requires NLG (natural language generation) from data. The advice panel uses static template strings, not dynamic analysis.
4. **No subscription/push infrastructure.** 6M households need server-side push notifications (FCM/APNs), email digest scheduling, and preference management. None exists.
5. **No privacy compliance.** Handling children's data requires APPI (Japan's Act on Protection of Personal Information) compliance for minors, parental consent workflows, and data retention policies. None are documented.

#### Data Quality / Completeness Concerns
- Crime subtypes are property crimes (bicycle theft, car break-in). Child-specific crimes (声かけ, 連れ去り) come only from the unstructured fushinsha data.
- No school zone data beyond Tokyo. Benesse is nationwide.
- Content staleness: if data is >7 days old, the freshness banner warns, but for a content product, even 24-hour staleness may be unacceptable.

#### Top 3 Action Items
1. **Build embeddable widget SDK**: Lightweight JavaScript component (`<risk-space-widget lat="..." lon="..." mode="compact">`) that renders a safety badge, EH score, and nearest haven. Support responsive sizing for app embedding.
2. **Implement age-stratified risk model**: Create risk profiles for elementary (6-12), junior high (12-15), and high school (15-18) students. Weight fushinsha subtypes differently (声かけ is high-severity for young children, lower for high schoolers). Add schema field `target_age_group`.
3. **Design content automation pipeline**: Weekly batch job that (a) computes risk deltas per registered area, (b) identifies new fushinsha incidents, (c) generates natural language safety summary via LLM, (d) delivers via push/email.

---

## Part B: Risk Management Expert Personas (R1--R5)

---

### R1: ISO 31000 Certified Auditor (55M)

**Use Case**: Verify that Risk Space follows ISO 31000 risk management process: Identify, Analyze, Evaluate, Treat, Monitor.

#### What Currently Works
1. **Risk identification**: Multiple risk layers (crime, traffic, disaster, weather, suspicious persons) are systematically enumerated with `layer` + `subtype` taxonomy.
2. **Risk analysis**: EH formula quantifies risk as probability x severity x (1 - escapability). This maps to ISO 31000's "likelihood x consequence" framework.
3. **Risk evaluation**: Safety rank (S/A/B/C/D) with defined thresholds provides risk evaluation criteria.
4. **Monitoring**: Auto-refresh (5 min), data freshness tracking, and morning briefing provide ongoing monitoring mechanisms.

#### What Is CRITICALLY Missing
1. **No documented risk criteria.** The thresholds (EH < 0.05 = S, < 0.15 = A, etc.) are hardcoded in JavaScript. No documented justification for why these values were chosen. No stakeholder consultation record.
2. **No residual risk definition.** After "treatment" (e.g., user avoids dangerous route), what is the residual risk? Not modeled.
3. **No PDCA evidence trail.** No change log showing when risk criteria were reviewed and updated. No management review records. No corrective action tracking.
4. **No risk treatment options.** The system identifies risk but does not systematically present treatment options (avoid, mitigate, transfer, accept) with effectiveness estimates.
5. **No risk register.** ISO 31000 requires a maintained risk register. The dashboard shows live data but has no structured register format.

#### Data Quality / Completeness Concerns
- Risk criteria are not traceable to organizational objectives (whose risk appetite do these thresholds represent?).
- No uncertainty quantification on the EH value itself (the CI95 field in statistical_metadata is not surfaced in the dashboard).
- Communication and consultation (ISO 31000 clause 5.2) is absent -- no stakeholder feedback mechanism.

#### Top 3 Action Items
1. **Create Risk Management Framework document**: Define context, scope, risk criteria rationale, stakeholder consultation process, and review cycle. Align explicitly to ISO 31000:2018 clauses.
2. **Implement risk register**: Structured database of identified risks with owner, treatment plan, residual risk level, review date, and status. Expose via dashboard and export.
3. **Add audit trail**: Version-controlled change log for all risk criteria, model parameters, and data source changes. Include management review sign-off timestamps.

---

### R2: COSO ERM Framework Auditor (48F)

**Use Case**: Evaluate governance, strategy alignment, performance monitoring, and continuous improvement per COSO ERM.

#### What Currently Works
1. **Performance indicators**: EH value, safety rank, fushinsha counts, haven density are measurable KRIs (Key Risk Indicators).
2. **ESG governance metadata** exists in enterprise overlay (`esg_governance_metadata.json`) with per-prefecture governance scores.
3. **Compliance badges** (TCFD, Solvency II, IFRS 17, Basel III, SASB, GRI, ISSB, NGFS) are displayed in enterprise mode.

#### What Is CRITICALLY Missing
1. **Governance documentation is absent.** The compliance badges are self-declared labels in JavaScript. No actual compliance evidence, no audit reports, no third-party attestation.
2. **No risk appetite statement.** COSO ERM requires explicit risk appetite and tolerance definitions. What level of EH is "acceptable" for which stakeholder?
3. **No KRI dashboard for management.** The enterprise overlay shows raw metrics but no traffic-light KRI dashboard with breach alerts, trend lines, and escalation procedures.
4. **No internal control mapping.** COSO requires controls to be mapped to risks. The dashboard identifies risks but not what controls are in place (e.g., police patrol schedules, CCTV coverage).
5. **No improvement cycle documentation.** No evidence of lessons learned, post-incident reviews, or model improvement iterations.

#### Data Quality / Completeness Concerns
- Compliance badges are cosmetic. No actual TCFD climate disclosure, no IFRS 17 insurance contract analysis, no SASB materiality assessment has been performed.
- ESG scores are generated, not audited. The methodology for `governance_safety_score` is undocumented.

#### Top 3 Action Items
1. **Remove or substantiate compliance badges**: Either produce actual compliance artifacts (TCFD report, SASB disclosure) or remove the badges. False compliance claims are a legal liability.
2. **Define risk appetite framework**: Document organizational risk appetite for each risk layer, with tolerance bands and escalation triggers. Publish as a governance document.
3. **Build management KRI dashboard**: Aggregated view showing KRI trends over time, breach history, and automatically generated management reports.

---

### R3: FSA Risk Management Inspector (45M)

**Use Case**: Evaluate model risk management, stress testing, backtesting, and data lineage per SR 11-7 and FSA guidelines.

#### What Currently Works
1. **Model documentation exists partially**: Schema (`schema.md`) and field mapping (`field_map.md`) document data transformations thoroughly.
2. **Tail risk metrics**: VaR 95%, VaR 99%, CVaR 99% in enterprise overlay.
3. **Monte Carlo simulation** with configurable parameters (drift, volatility, iterations).
4. **Data lineage**: `source` object in schema tracks org, URL, license, update frequency, missing rate, and geocoding status. `raw` field preserves original data.
5. **Merkle tree verification** (`manifest.sig`) provides data integrity checking.

#### What Is CRITICALLY Missing
1. **No backtest results.** The Monte Carlo model has NEVER been validated against historical outcomes. No backtest report exists.
2. **No model inventory.** SR 11-7 requires a complete inventory of all models used, their owners, validation status, and materiality classification. The EH model, time multiplier model, weather multiplier model, and Monte Carlo model are all undocumented as a model inventory.
3. **No stress testing framework.** VaR/CVaR are shown but the stress scenarios (earthquake + crime spike + weather event) are not defined, run, or documented.
4. **No model change management.** When the `TM()` (time multiplier) function parameters change, there is no approval process, no pre/post validation, no documentation.
5. **No independent validation.** All models are built and "validated" by the same team. FSA requires independent model validation.

#### Data Quality / Completeness Concerns
- The `TM()` function (time multiplier) uses hardcoded seasonal patterns. No citation to empirical research or calibration data.
- Weather multiplier logic is a simple heuristic (rain = +20%, etc.), not a validated statistical relationship.
- Missing rate (`source.missing_rate`) is defined in schema but never computed or displayed.
- Data lineage stops at the API/CSV level. No row-level provenance tracking.

#### Top 3 Action Items
1. **Produce Model Risk Management (MRM) documentation**: Model inventory, model cards (purpose, methodology, assumptions, limitations, validation results) for each model (EH, time multiplier, weather multiplier, Monte Carlo). Follow SR 11-7 format.
2. **Implement backtesting framework**: Compare model predictions against actual incident data over holdout periods. Report coverage ratios, Kupiec test results, and model accuracy metrics.
3. **Commission independent model validation**: Engage external quantitative risk consultancy to validate all models. Document findings and remediation plan.

---

### R4: Ministry of Defense -- Cybersecurity Division (40M)

**Use Case**: Evaluate as potential C2 dashboard; assess data integrity, OPSEC, and threat intelligence integration.

#### What Currently Works
1. **Merkle tree data integrity verification** with SHA-256 hashing and `manifest.sig` file.
2. **Privacy mode** blocks external API calls and rounds coordinates to reduce location precision.
3. **Quick-exit button** (DV safety feature) demonstrates awareness of hostile-environment usage.
4. **Data deletion capability** (`mimamoriDeleteAllData`) with complete localStorage purge.
5. **Local-first architecture**: core functionality works from local JSON files without external dependencies.

#### What Is CRITICALLY Missing
1. **No authentication or authorization.** The dashboard has zero access control. Anyone with the URL can access all data. No RBAC, no MFA, no session management.
2. **No data encryption.** Data is stored in localStorage as plaintext JSON. No encryption at rest. Transit security depends entirely on HTTPS (which is not enforced in the HTML).
3. **No tamper detection at runtime.** Merkle verification runs once at startup. A MITM attack during the session could serve modified tile data without detection.
4. **No audit logging.** No record of who accessed what data, when, from where. Essential for OPSEC and forensic investigation.
5. **No threat intelligence integration.** The "suspicious person" layer is crime reports, not threat intelligence. No STIX/TAXII integration, no IOC correlation, no situational awareness feed from defense/intelligence sources.
6. **Client-side JavaScript is fully inspectable.** All risk computation logic, data sources, and API endpoints are exposed in the HTML source. An adversary can reverse-engineer the entire system.

#### Data Quality / Completeness Concerns
- CDN dependencies (unpkg.com for Leaflet, cdn.jsdelivr.net for Chart.js, cdnjs for jsPDF) are supply chain attack vectors.
- CARTO tile server (`basemaps.cartocdn.com`) is a third-party dependency that could be compromised.
- No Content Security Policy (CSP) headers defined. Vulnerable to XSS injection.

#### Top 3 Action Items
1. **Implement security hardening**: CSP headers, Subresource Integrity (SRI) for all CDN resources, HTTPS enforcement, and Content-Type validation. Self-host all dependencies for classified environments.
2. **Add authentication and audit trail**: OAuth2/OIDC authentication, role-based access control, comprehensive audit logging (access, query, export events). Integrate with SIEM.
3. **Implement continuous integrity verification**: Re-verify data integrity on every tile load, not just startup. Add server-side signed responses (JWS) for all API responses.

---

### R5: Tokyo Metropolitan Government -- Crisis Management Advisor (60M)

**Use Case**: Integration with Metropolitan Disaster Plan; stranded commuter estimation; legal responsibility for information accuracy.

#### What Currently Works
1. **Seismic hazard layer** with JSHIS data showing 30-year exceedance probabilities (intensity 5-/5+/6-) per city.
2. **JMA integration**: earthquake data, weather warnings/advisories, typhoon information all mapped to schema.
3. **Evacuation shelter layer** from GSI designated emergency shelters with disaster-type flags.
4. **Climate scenarios** (RCP 2.6/4.5/8.5) with 2030/2050/2100 horizons and delta-EH projections.
5. **Emergency contact modal** with 110, 119, #9110, and DV hotlines.
6. **Data attribution section** crediting all government data sources.

#### What Is CRITICALLY Missing
1. **No stranded commuter (帰宅困難者) estimation.** The schema has no layer for population density, commuter flow, or transit capacity. Cannot estimate how many people would be stranded in a Shuto Chokka earthquake scenario.
2. **No regional disaster plan integration.** No mapping to Tokyo Metropolitan Regional Disaster Plan structure. No alignment with designated evacuation areas vs. wide-area evacuation sites.
3. **No legal disclaimer or liability framework.** The dashboard presents risk scores that could influence life-safety decisions. No terms of use, no disclaimer of liability, no statement about data accuracy limitations.
4. **No multi-hazard scenario modeling.** Cascading disasters (earthquake triggers fire triggers gas leak) are not modeled. Each risk layer is independent.
5. **No interoperability with CAP (Common Alerting Protocol).** Government emergency alerts use CAP format. The dashboard cannot receive or display CAP alerts.
6. **No flood/tsunami inundation mapping.** The schema defines flood/landslide subtypes but the dashboard has no inundation depth overlay. JMA tsunami API exists in the MCP tools but is not visualized.

#### Data Quality / Completeness Concerns
- Seismic data shows city-level averages but not micro-zone variations (soil amplification, liquefaction risk).
- Evacuation shelter data may be outdated (shelters designated by local governments change).
- No real-time crowd density data for stranded commuter estimation.
- Weather warning layer (`map.json`) is loaded but integration logic is minimal.

#### Top 3 Action Items
1. **Add stranded commuter estimation layer**: Integrate ODPT (Open Data for Public Transportation) passenger volume data with seismic scenario triggers. Model walking distance to shelters by district.
2. **Prepare legal framework**: Terms of use document explicitly stating data is for reference only, not for life-safety decisions without professional judgment. Add prominent disclaimer to dashboard.
3. **Implement CAP integration**: Subscribe to JMA's CAP feed for real-time emergency alerts. Display as priority overlay with audio alert capability.

---

## Part C: Cross-Cutting Enterprise Requirements Matrix

| Requirement | B1 | B2 | B3 | B4 | B5 | R1 | R2 | R3 | R4 | R5 | Priority |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Production REST API | X | X | X | X | X | | | | | | **P0** |
| Authentication & RBAC | X | X | X | X | X | | X | X | X | X | **P0** |
| SLA documentation | X | X | X | | X | | | | | X | **P0** |
| Multi-tenant architecture | | X | | | X | | | | | | **P1** |
| National data coverage (47 pref) | X | X | X | X | X | | | X | | X | **P0** |
| Model validation / backtesting | | | | X | | X | X | X | | | **P1** |
| Data lineage / audit trail | X | | | X | | X | X | X | X | X | **P1** |
| Age-stratified risk model | | X | X | X | X | | | | | | **P1** |
| Edge/CDN deployment | | | X | | X | | | | | | **P2** |
| Legal disclaimer / ToU | X | X | X | X | X | X | X | X | X | X | **P0** |
| Privacy compliance (APPI) | X | X | X | X | X | | | | X | | **P0** |
| Embeddable widget / SDK | | | X | | X | | | | | | **P2** |
| Server-side persistence (DB) | X | X | X | X | X | | | | X | | **P0** |
| Automated reporting | | X | | X | X | | X | | | X | **P1** |
| Security hardening (CSP, SRI) | X | X | X | X | X | | | | X | | **P1** |
| Model documentation (SR 11-7) | | | | X | | X | X | X | | | **P1** |
| CAP / J-ALERT integration | | | | | | | | | X | X | **P2** |
| Streaming / batch API | | | X | | | | | | | | **P2** |
| Independent model validation | | | | X | | X | X | X | | | **P2** |
| Risk register / treatment plans | | | | | | X | X | | | X | **P2** |

---

## Part D: Prioritized Implementation Roadmap

### Phase 0: Foundation (Weeks 1-4) -- **Must-have for any enterprise deployment**
1. **Production API**: Deploy Cloudflare Workers with REST endpoints. Implement `get_risk_field(lat, lon, radius_km, time, layers)` returning JSON per schema.
2. **Authentication**: OAuth2/OIDC with API key fallback. RBAC with at least 3 roles (viewer, analyst, admin).
3. **Legal framework**: Terms of use, privacy policy, data accuracy disclaimer, APPI compliance documentation.
4. **SLA v1**: Uptime 99.9%, p95 latency < 500ms, data freshness guarantees per layer type.
5. **National data pipeline**: Automated collection from all 47 prefectural police, JMA, and NPA sources. Store in PostGIS.

### Phase 1: Enterprise Features (Weeks 5-12)
6. **Multi-tenant architecture**: Organization and project-level isolation. Per-school views for ALSOK use case.
7. **Model documentation**: Complete model cards for EH, time multiplier, weather multiplier, Monte Carlo. Backtesting against 2023 holdout data.
8. **Data lineage system**: Row-level provenance tracking from source through transformation to API response.
9. **Age-stratified risk**: Implement elementary/junior-high/high-school risk profiles.
10. **Automated reporting**: Monthly PDF/Excel per tenant with trend analysis and compliance checklists.

### Phase 2: Scale & Specialization (Weeks 13-24)
11. **Edge deployment**: Precomputed risk at S2 cell level on CDN. p99 < 100ms target.
12. **Embeddable SDK**: Web Component + React/Flutter packages for third-party app embedding.
13. **Actuarial package**: 10-year historical data, Poisson/GPD models, backtest reports, independent validation.
14. **CAP / J-ALERT integration**: Real-time emergency alert overlay with push notification support.
15. **Stranded commuter estimation**: ODPT integration with seismic scenario modeling.

### Phase 3: Certification & Compliance (Weeks 25-36)
16. **ISO 31000 alignment**: Complete risk management framework documentation. External audit.
17. **FSA model governance**: SR 11-7 compliant MRM documentation. Independent validation engagement.
18. **SOC 2 Type II**: Security audit and attestation for enterprise customers.
19. **COSO ERM alignment**: Risk appetite framework, KRI dashboard, management reporting.
20. **Penetration testing**: External security assessment. Remediate all critical/high findings.

---

## Part E: Current Dashboard Strengths (What Impressed Us)

Despite the gaps above, the dashboard demonstrates remarkable ambition and several genuinely strong foundations:

1. **Comprehensive risk formula**: EH = P(incident) x Severity x (1 - P(escape)) is a sound conceptual framework that can be extended to actuarial-grade models.
2. **Mimamori mode depth**: Location registration, route evaluation, time-window scheduling, morning briefing, simplified (grandparent) mode, voice readout, privacy mode, and DV safety features show deep user empathy.
3. **Enterprise overlay**: ELT, VaR/CVaR, cat bond pricing, Basel III ORC, climate scenarios (RCP), sovereign risk scorecard -- this is far beyond a typical prototype.
4. **Data integrity**: Merkle tree verification with SHA-256 is the right approach for trustworthy data.
5. **Multi-language support**: JA/EN/ZH/KO with full UI localization, plus multilingual emergency scripts (including Tagalog, Vietnamese, Portuguese for foreign resident safety).
6. **Schema design**: The common schema in `schema.md` is well-thought-out, with proper GeoJSON, ISO 8601 timestamps, source metadata, and extensible `raw` fields. This is a solid foundation for an API.

The gap between the current prototype and enterprise readiness is significant but bridgeable. The core data model and conceptual framework are sound. What is needed is primarily infrastructure (API, database, auth, deployment), process (documentation, validation, compliance), and data coverage (nationwide expansion).

---

*Document generated: 2026-04-09*
*Evaluated by: 10 enterprise/risk management professional personas*
*Dashboard version: 3,876 lines, dashboard/index.html*
