# Risk Space MCP - CHANGELOG

All notable changes to the Risk Space MCP dashboard.

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
