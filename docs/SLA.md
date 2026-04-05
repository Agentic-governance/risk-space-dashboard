# Risk Space MCP — Service Level Agreement (SLA)

Version: 1.0.0
Last updated: 2026-04-05

## 1. Service classification

Risk Space MCP is currently delivered as a **static data distribution** hosted via GitHub Pages (`docs/`). It is provided on a **best-effort availability basis** and is **not** accompanied by a contractual uptime SLA. No monetary credits, warranties, or guarantees apply at this tier.

| Tier              | Availability target | Binding? | Channel                    |
|-------------------|---------------------|----------|----------------------------|
| Community (current) | Best effort (~99.0% observed) | No       | GitHub Pages static        |
| Enterprise        | 99.9% monthly       | Yes      | Cloudflare Workers + R2    |
| Enterprise+       | 99.95% monthly      | Yes      | Multi-region CF Workers    |

## 2. Data update frequency by source

| Source                               | Target cadence | Typical latency  | Notes                                      |
|--------------------------------------|----------------|------------------|--------------------------------------------|
| JMA earthquakes (`earthquakes_latest.json`) | 10 minutes     | <15 min          | Polled from JMA XML feed                   |
| JMA weather warnings (`weather_warnings.json`) | 30 minutes | <45 min          | All 47 prefectures                         |
| AMeDAS observations (`amedas_current.json`)    | 60 minutes | <90 min          | Current-hour aggregate                     |
| NPA crime trends (`crime_trends.json`)         | Annual     | Prior-year data  | e-Stat refresh (March/April)               |
| Grid risk (`grid_risk.json`)                   | Daily      | 24h              | Recomputed from crime + events inputs      |
| Hotspots (`hotspots_expected_harm.json`)       | Daily      | 24h              | Derived from grid_risk                     |
| Tail risk / statistical metadata               | Weekly     | 7d               | Recomputed on data refresh                 |
| Loss triangle / GLM                            | Quarterly  | 90d              | Manual validation step                     |
| Evacuation shelters (`evacuation_shelters.json`) | Quarterly | 90d            | GSI / MLIT source                          |
| Manifest signature (`manifest.sig`)            | On every data push | N/A         | Merkle root re-computed                    |

## 3. Known limitations

- **No transactional guarantees.** Consumers may observe mid-update inconsistency if they fetch individual files during a publish cycle. Use `manifest.sig` to verify a consistent snapshot.
- **No signed authenticity** at the community tier: `manifest.sig` currently contains an `ed25519:PLACEHOLDER_NO_KEY_PROVISIONED` field. Enterprise tier ships with real ed25519 signatures.
- **No private incident data.** Only aggregate/public statistics are exposed. Grid cell counts are smoothed via KDE (bandwidth 250m).
- **Statistical quantities are synthesized** where source data is incomplete (e.g. loss triangle development pattern, GLM coefficients) — see each file's `metadata.methodology`.
- **No real-time alerting.** Polling-based consumption only.
- **Geographic coverage**: Japan only; resolution 0.0025°–0.01° grid.
- **CI/CD**: Failed builds leave the prior snapshot in place; check `_version.json` for the currently published version.

## 4. Enterprise upgrade path

For production workloads requiring binding SLAs, lower latency, and authenticated delivery, upgrade to the Enterprise tier:

| Capability                        | Community | Enterprise |
|-----------------------------------|-----------|------------|
| Uptime SLA                        | None      | 99.9%      |
| Authenticated ed25519 manifests   | No        | Yes        |
| Private prefecture-level detail   | No        | Yes        |
| Query API (spatial, temporal)     | No        | Yes        |
| Push updates (webhook / SSE)      | No        | Yes        |
| Support response                  | Best effort | 4 business hours |
| Data residency                    | Public CDN | JP region CF R2 |
| Audit logging                     | No        | Yes, 12 months retention |

**Deployment target**: Cloudflare Workers + R2 (same architecture as Patent Space MCP and Caselaw MCP).

Contact the Risk Space team to provision an Enterprise tenant.

## 5. Incident reporting

Report data quality issues, stale sources, or availability problems via GitHub Issues on the Risk Space repository. Include:
- File path affected
- `manifest.sig` `merkle_root` observed
- Timestamp (UTC)
- Expected vs observed value

## 6. Changes to this SLA

This document is versioned with the repository. Breaking changes (e.g. schema bumps, cadence reductions) will be announced in `docs/CHANGELOG.md` at least 14 days in advance for the Community tier, and 30 days for Enterprise.
