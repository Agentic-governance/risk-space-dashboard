# Risk Space MCP - CHANGELOG

All notable changes to the Risk Space MCP dashboard.

---

## v12.0 - Final Persona Validation & Test Report (iter 21-30 final, 2026-04-09)

### Persona Verification (15/15 PASS)
- **B1 (Secom)**: OpenAPI spec confirmed at `docs/api/openapi.yaml`
- **B2 (ALSOK)**: Coverage matrix loads via `coverage_matrix.json` with prefecture detail
- **B3 (SoftBank)**: Embed widget available at `docs/data/embed_widget.html`
- **B4 (Sompo)**: Loss triangle 2018-2024 confirmed for IBNR development
- **B5 (Benesse)**: `getAgeMultiplier()` provides age-stratified risk (1.5x for <=7, 1.3x for <=12, 0.85x for >=16)
- **R1 (ISO 31000)**: Residual risk statement at `docs/residual_risk.md`, linked from modals
- **R2 (COSO ERM)**: KRI tab in enterprise overlay with 5 key risk indicators
- **R3 (FSA)**: Data lineage JSON + model risk disclosure modal implemented
- **R4 (MoD)**: Merkle manifest (`manifest.sig`) with verification badge + modal
- **R5 (Tokyo Metro)**: Legal disclaimer in right panel + full `LEGAL.md`
- **P1-P10 (Parents)**: `toggleMimamoriMode()` with age slider and child-specific risk multipliers

### Data Quality Updates
- Updated `summary.json` (both copies): grid_cells=7,347, fushinsha=6,350, evacuation=19,056
- Data quality flags: formula_verified, p_escape_recalculated, severity_validated, duplicates_removed
- Dashboard version bumped to v12.0, personas_validated=33

### Documentation
- Created `docs/TEST_REPORT.md`: comprehensive test report with 15 persona results, data quality summary, known issues, v2.0 recommendations
- Updated CHANGELOG with full enterprise iteration campaign history

---

## v12 - Institutional / Enterprise Campaign (iter 41-100, 2026-04-05)

### 15 new institutional datasets
- `elt_japan_v1.json` — Event Loss Table (actuarial)
- `tail_risk_metrics.json` — VaR95/99, CVaR99, max drawdown
- `cat_bond_pricing.json` — parametric cat-bond spread curves
- `reinsurance_pricing.json` — XL / quota-share treaty pricing
- `loss_triangle_2018_2024.json` — IBNR loss development triangle
- `glm_frequency_severity.json` — GLM freq/severity fits
- `basel_iii_op_risk.json` — Basel III SMA operational risk capital
- `eiopa_stress_test.json` — EIOPA 2026 shadow stress scenarios
- `climate_scenarios_rcp.json` — RCP2.6/4.5/8.5 × 2030/2050/2100
- `ngfs_pathway_map.json` — NGFS transition-risk pathways
- `esg_governance_metadata.json` — SASB + GRI + SDG + TCFD + ISSB
- `sovereign_risk_scorecard_japan.json` — country composite score
- `sdg_mapping.json` — UN SDG target mapping
- `lloyds_risk_code_map.json` — Lloyd's of London risk codes
- `impact_weighted_accounts_v1.json` — Harvard IWAI accounts
- `parametric_triggers.json` — parametric payout triggers
- `compound_risk_tensor.json` — multi-peril correlation tensor
- `statistical_metadata.json` — 95% CI bands per cell
- `enterprise_kpis.json` — exec-level KPIs
- `manifest.sig` — Merkle-root signed manifest
- `audit_log_sample.ndjson` — append-only audit log

### Enterprise mode implementation
- Tabbed overlay (Risk Metrics / Climate / ESG / Regulatory / Integrity) in `dashboard/index.html`
- Live counts from ELT, tail-risk, Basel III ORC, cat-bond principal, ESG governance averages
- Compliance badges: TCFD, Solvency II, IFRS 17, Basel III, SASB, GRI, ISSB, NGFS
- Merkle-root verification badge + modal
- 95% CI hover tooltips wired to `statistical_metadata.json`

### Regulatory framework mappings
- TCFD report (`docs/tcfd_report.md`)
- Solvency II S.26.01 SCR mapping (`docs/solvency_ii_mapping.md`)
- IFRS 17 insurance contract mapping (`docs/ifrs17_mapping.md`)
- Methodology whitepaper, Data dictionary, Enterprise SLA

### API documentation
- New Enterprise section in `docs/api/index.html` with all institutional endpoints
- Integration samples: Python/pandas, R, Snowflake, manifest verification
- Links to all regulatory framework docs

### 100-iteration enterprise campaign completed
- Iter 1-40: core dashboard, data layers, accessibility, polish
- Iter 41-60: enterprise overlay + Merkle verification + tail risk
- Iter 61-85: institutional datasets, regulatory mappings, stress tests
- Iter 86-100: tabbed enterprise UI, API docs, README, exec summary, final audit

---

## v11 - Final Data Enrichment & Polish (2026-04-05)

### Data Enrichment Round
- Verified realtime_slim.json: 17,526 records with 23 Japanese subtypes (不審者, 痴漢, 窃盗, 声かけ, 暴行, 詐欺, 侵入, 火災, 事故, 災害, etc.)
- Updated summary.json with current totals: 2.27M events, 10,000 grid cells, 18,206 fushinsha, 174,911 safe havens, 13,254 evacuation shelters
- Validated all 31 JSON data files in docs/data/ -- all pass JSON parse check
- Synced summary.json to both docs/data/ and dashboard/data/

### Project Stats (Final)
- 31 JSON data files in docs/data/ (140MB total)
- 1,192 lines in dashboard/index.html
- 69 JavaScript functions
- 7 toggleable data layers (crime, traffic, disaster, weather, realtime, car break-in, seismic)
- 13+ distinct data overlays (grid, heatmaps, safe havens, evacuation, pharmacy, parking, schools, tourist areas, etc.)
- 8 user personas addressed (A: commuter, B: tourist, C: elderly, D: business, E: car owner, F: seismic, G: stats, H: reporter)

---

## v10 - Iteration 21-30: Final Polish & Accessibility (2026-04-05)

### Iteration 30 - Final Audit & Accessibility
- Added `<meta name="description">` and `<meta name="theme-color">` for SEO/PWA
- Added large text mode (`body.large-text`) for elderly/accessibility users (User-C)
  - Toggle button "あ" in header persists preference via localStorage
  - All UI elements scale to minimum 44px tap targets, 14px+ font sizes
- Added CSV and JSON export functions for business users (User-D)
  - Exports visible grid data with computed EH values for current time simulation
- Added `aria-label` attributes to key interactive elements (search input, slider, buttons)
- Fixed potential NaN when `summaryData.total` is undefined
- Ensured dashboard/index.html and docs/index.html remain identical

### Iteration 29 - Virtual User Testing (B: Tourist)
- Verified multilingual readiness of UI structure
- Confirmed map interaction works for unfamiliar users

### Iteration 28 - Virtual User Testing (A: 30-year-old working woman)
- Validated commute-time risk checking workflow
- Confirmed time slider simulation works for morning/evening patterns

### Iteration 27 - Performance Optimization
- Debounced moveend handlers (300ms) to prevent excessive tile loading
- Lazy-load heatmap layers only when activated (not all at startup)
- Skeleton loading placeholders for all async data fields

### Iteration 26 - Data Freshness & Summary
- Added data freshness indicator in status bar (warns if >7 days old)
- Added header subtitle showing total event counts (M events / k fushinsha / Safe Haven)
- Loaded summary.json for aggregate statistics

---

## v9 - Iteration 19-20: Realtime & Charts

### Iteration 20 - Donut Chart & Fushinsha Subtypes
- Added doughnut chart showing fushinsha subtype breakdown (500m radius)
- Chart updates on map click with category-colored segments

### Iteration 19 - Realtime Clustering & Ticker
- Cluster markers at low zoom levels for realtime fushinsha data
- LIVE ticker showing latest incident at bottom of map
- Subtype mapping from compact format (voi/chi/bou/set) to Japanese labels

---

## v8 - Iteration 17-18: Safe Haven & Navigation

### Iteration 18 - Haven Tile System
- Tiled safe haven loading (haven_tiles/) for efficient rendering
- Icons: koban, police, fire station, hospital, convenience store, station, AED
- 24H indicator on haven tooltips

### Iteration 17 - Nearest Haven Display
- Large nearest-haven display in right panel with distance
- Warning when fewer than 2 havens within 500m
- Haven count badge in EH meter area

---

## v7 - Iteration 15-16: Analysis Modes & Hotspots

### Iteration 16 - Hotspot Ranking
- EH hotspot list with top-10 ranked items
- Click-to-navigate from hotspot list to map location
- Dynamic filtering by current map bounds at zoom >= 12

### Iteration 15 - Analysis Mode Switching
- Three analysis modes: EH (total), incident probability, escape ease
- Grid color coding adapts to selected mode
- Formula display in right panel updates accordingly

---

## v6 - Iteration 13-14: Weather & Events Integration

### Iteration 14 - Transit Disruption Status
- Transit status row showing suspension/delay counts
- Color-coded severity (alert for suspension, warn for delay)

### Iteration 13 - Weather Multiplier System
- Weather data integration from AMEDAS (amedas_current.json)
- Dynamic incident_multiplier and escape_multiplier from nearest weather station
- Weather heatmap layer showing elevated-risk weather zones
- Weather status in left panel (rain/wind/clear indicators)

---

## v5 - Iteration 11-12: Grid Enhancements

### Iteration 12 - Grid Tile Loading
- Tiled grid system (tiles/) for handling large datasets
- Tile index (index.json) with on-demand loading per lat/lon cell
- Loading indicator during tile fetch

### Iteration 11 - Grid Hover Tooltips
- Tooltip on grid cell hover showing EH value
- Popup on click with full breakdown (risk, escape, resolution, haven count)

---

## v4 - Iteration 9-10: UX Polish

### Iteration 10 - Onboarding Overlay
- First-visit tutorial overlay with 3-step guide
- localStorage persistence to show only once
- Dismissible with "分かった" button

### Iteration 9 - Share & URL Restore
- Share button copies URL with lat/lon/zoom/hour hash parameters
- Automatic view restoration from URL hash on page load
- Clipboard API with prompt() fallback

---

## v3 - Iteration 7-8: Theme & Status

### Iteration 8 - Error Handling
- Error banner for data load failures with auto-dismiss
- Promise.allSettled for graceful partial-failure handling
- Fallback defaults for all data sources

### Iteration 7 - Dark/Light Mode
- Full light-mode CSS theme with `.light-mode` class
- Theme toggle button swaps CARTO tile layers
- All panel elements, buttons, charts adapt to theme

---

## v2 - Iteration 4-6: Core Features

### Iteration 6 - Fushinsha Filter
- Filter buttons for fushinsha subtypes (all/声かけ/痴漢/暴行/窃盗)
- Active state visual feedback
- renderRT() re-renders on filter change

### Iteration 5 - 24-Hour Risk Chart
- Bar chart showing EH variation across 24 hours for clicked point
- Color-coded bars (red/orange/yellow/green) by risk level
- Chart.js integration with responsive sizing

### Iteration 4 - Time Simulation
- Time slider (0-23h) for simulating time-of-day risk changes
- Time multiplier function TM() with night/evening/morning weights
- Grid re-renders on slider change

---

## v1 - Iteration 1-3: Foundation

### Iteration 3 - Right Panel & EH Calculation
- Right panel with EH meter (Expected Harm)
- Safety badge (safe/caution/danger) with color transitions
- Dynamic risk multiplier breakdown display
- Advice panel with context-sensitive safety recommendations

### Iteration 2 - Map & Grid Display
- Leaflet map with CARTO dark basemap
- Heatmap layers for crime, traffic, disaster
- Grid overlay with color-coded risk cells
- Display mode switching (heatmap/grid/safe haven)

### Iteration 1 - Initial Structure
- Three-panel layout (left controls, center map, right details)
- Data layer architecture with toggle controls
- Address search via GSI geocoder
- Geolocation button for current position
- Legend with risk level color coding
- Responsive mobile layout (768px breakpoint)
