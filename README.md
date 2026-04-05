# Risk Space MCP

Institutional-grade risk probability space for Japan — integrating crime, disaster, traffic, and weather into a unified, actuarially-sound data layer. Same architecture as Patent Space MCP and Caselaw MCP (Cloudflare Workers + R2 + static JSON).

## Institutional-Grade Features

- **Actuarial foundation** — Event Loss Table (ELT), GLM frequency/severity fits, loss development triangles, IBNR
- **Tail risk** — VaR95, VaR99, CVaR99, max drawdown with 95% confidence bands
- **Catastrophe market** — parametric cat-bond pricing, reinsurance XL/QS pricing, parametric triggers
- **Climate** — RCP2.6/4.5/8.5 scenarios across 2030/2050/2100 horizons, NGFS pathways
- **Stress testing** — EIOPA 2026 shadow scenarios (pandemic, cyber, NatCat)
- **Data integrity** — signed Merkle manifest (`manifest.sig`), append-only audit log, per-cell 95% CI
- **Enterprise overlay** — tabbed dashboard with Risk Metrics, Climate, ESG, Regulatory, Integrity panes

## Compliance Frameworks Supported

| Framework | Coverage |
|-----------|----------|
| TCFD      | Climate physical risk (governance / strategy / risk management / metrics) |
| Solvency II | S.26.01 SCR estimates, EIOPA stress-test shadow run |
| IFRS 17   | Insurance contract measurement, LRC / LIC / CSM mapping |
| Basel III | SMA operational risk capital (BI, BIC, ILM, ORC) |
| SASB      | Services sector disclosures (SV-PS-*) |
| GRI       | 413-1, 403-10, 418-1 |
| ISSB      | IFRS S1 / S2 |
| UN SDG    | 11.7, 16.1, 16.4 |
| NGFS      | Transition-risk pathway mapping |
| Lloyd's   | Risk code mapping |

## Data Access Methods

1. **Static JSON** — every dataset is a public JSON under `/data/` on GitHub Pages or R2. No auth.
2. **Interactive Dashboard** — `dashboard/index.html` (also published at `docs/index.html`).
3. **Query API** — `docs/api/risk.html?lat=35.68&lon=139.75&radius=0.01` returns filtered cells.
4. **Signed Manifest** — `manifest.sig` provides Merkle root + SHA-256 per file.
5. **OpenAPI Spec** — `docs/api/openapi.yaml` for the Workers-based API.

## Quick Start

```bash
# Dashboard (interactive map)
open dashboard/index.html

# Read the ELT
curl -s https://<pages>/data/elt_japan_v1.json | jq '.events | length'

# Verify the signed manifest
curl -s https://<pages>/data/manifest.sig | jq '{merkle_root, file_count, version}'

# Pull tail-risk metrics
curl -s https://<pages>/data/tail_risk_metrics.json | jq '.national'
```

Python (pandas):
```python
import pandas as pd, requests
base = 'https://<pages>/data'
elt = pd.DataFrame(requests.get(f'{base}/elt_japan_v1.json').json()['events'])
elt['aal'] = elt['annual_rate'] * elt['mean_loss_jpy']
print('National AAL (JPY):', int(elt['aal'].sum()))
```

## Repository Layout

- `schema.md` — confirmed schema spec
- `field_map.md` — field mapping table
- `sources.json` — data source registry
- `dashboard/` — interactive web dashboard (`index.html` + `data/`)
- `docs/` — published site (GitHub Pages) with API docs, methodology, framework mappings
- `workers/` — Cloudflare Workers entrypoints
- `scripts/` — ingestion, ETL, and build scripts
- `data/` — raw source data
- `issues.md` — known issues / gaps

## Design Principles

- Risk is expressed as a **probability distribution**, never a single number
- **UK Police API's** "location × category × time" model, adapted for Japan
- Same architecture as **Patent Space MCP / Caselaw MCP** (Cloudflare Workers + R2)
- Every numeric claim is backed by a source entry in `sources.json`

## License

Data: CC-BY 4.0 (attribution required to upstream statistical authorities: NPA, JMA, NIED, etc.). Code: MIT.
