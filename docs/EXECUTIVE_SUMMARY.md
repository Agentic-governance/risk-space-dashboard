# Risk Space MCP — Executive Summary

**Audience:** C-level decision makers in (re)insurance, asset management, sovereign wealth, infrastructure, and municipal risk offices.
**Date:** 2026-04-05 • **Version:** v12

---

## 1. Value Proposition

Risk Space MCP turns Japan's fragmented public risk data (NPA crime, JMA weather, NIED seismic, MLIT flood, NPA traffic) into a **single, actuarially-sound probability space** that plugs directly into ALM models, SCR calculations, cat-bond pricing, ESG disclosures, and board-level dashboards.

- **One schema, every peril** — crime × disaster × traffic × weather, expressed as probability distributions, not point estimates.
- **Institutional-grade** — Event Loss Tables, tail-risk (VaR/CVaR), loss-development triangles, GLM fits, signed manifests.
- **Regulator-aligned** — outputs pre-mapped to TCFD, Solvency II, IFRS 17, Basel III, SASB, GRI, ISSB, NGFS, UN SDG, and Lloyd's risk codes.
- **Open architecture** — static JSON over CDN; no vendor lock-in; every figure traceable to a primary public source.

---

## 2. Coverage & Data Volumes

| Dimension | Coverage |
|-----------|----------|
| Geographic | All 47 prefectures, 250m – 5km grid resolution |
| Perils | Crime (23 subtypes), traffic accidents, flood, earthquake, typhoon, heat, fire, cyber |
| Temporal | 2018–2024 historical + realtime + 2030/2050/2100 climate projections |
| Events | 2.27M historical events, 18,206 realtime fushinsha reports |
| Safe havens | 174,911 (koban, hospital, fire, conbini, AED, station) |
| Shelters | 13,254 designated evacuation shelters |
| Grid cells | 10,000 national + ~100k high-res tiles |
| Datasets | 40+ static JSON files, ~140 MB total |
| Institutional files | 20+ (ELT, tail-risk, cat-bond, Basel III, EIOPA, RCP, ESG, etc.) |

---

## 3. Compliance & Governance

**Frameworks mapped out of the box:** TCFD • Solvency II (S.26.01) • IFRS 17 • Basel III SMA • SASB • GRI • ISSB (IFRS S1/S2) • NGFS • UN SDG 11/16 • Lloyd's risk codes.

**Data integrity guarantees:**
- **Signed manifest** (`manifest.sig`) — SHA-256 per file + Merkle root, re-computable client-side.
- **Append-only audit log** — NDJSON with cryptographic chaining of every data release.
- **Per-cell 95% CI bands** — every expected-harm figure ships with confidence intervals and sample size.
- **Full provenance** — every source entry in `sources.json` links back to the issuing public authority.

**Methodology:** Inverse-normalized sub-scores, GLM frequency/severity, Monte-Carlo simulation of the ELT, elasticity-driven RCP projections, Basel III SMA (BI × BIC × ILM = ORC).

---

## 4. Pricing & Access Model

| Tier | Access | Price |
|------|--------|-------|
| **Open / Community** | All JSON under `/data/`, dashboard, OpenAPI spec, CORS-enabled | Free (CC-BY 4.0) |
| **Professional** | Signed manifest verification, historical snapshots, polling integrations | Self-serve |
| **Enterprise** | Private R2 bucket, signed URLs, 99.9% SLA, <500ms p95, audit trail, Slack Connect, named CSM | Contract |
| **Bespoke** | Custom perils, custom resolution, on-prem deployment, regulator filings support | Quote |

All tiers read the same schema — upgrade is purely about SLA, signing, and support, not data access.

---

## 5. Competitive Positioning

| Dimension | Incumbents (RMS, AIR, Verisk) | Risk Space MCP |
|-----------|-------------------------------|----------------|
| Perils covered | Property cat, single-peril | Multi-peril incl. crime / traffic / cyber / climate |
| Pricing | $$$$ / seat-licence | Free base + Enterprise SLA |
| Schema | Closed, proprietary | Open JSON, versioned, Merkle-signed |
| Japan granularity | National / prefecture | 250 m grid, 47 prefectures, 23 crime subtypes |
| Regulatory mapping | Manual integration | Pre-mapped to 10+ frameworks |
| Time-to-integrate | Months (SI-led) | Hours (curl + pandas) |

**Differentiators:** (1) crime × disaster × traffic × weather in one schema; (2) open, Merkle-signed, vendor-neutral; (3) regulator-aligned out of the box; (4) Patent Space / Caselaw MCP architectural compatibility — same stack, same ops model, shared tooling.

---

## 6. Governance & Roadmap

- **Architecture:** Cloudflare Workers + R2 + GitHub Pages (identical to Patent Space MCP, Caselaw MCP).
- **Release cadence:** data refreshed every 30 min (realtime), daily (grid), quarterly (ELT / climate).
- **v12 milestone:** 15 new institutional datasets, tabbed Enterprise UI, full regulatory mapping, 100-iteration enterprise campaign completed.
- **Next:** multi-jurisdiction (KR, TW, SG), counterparty-risk overlay, Basel III IRB proxy extension, EIOPA live feed.

---

**Contact:** see `docs/SLA.md` for enterprise procurement path, or open an issue at the project repo for community-tier support.
