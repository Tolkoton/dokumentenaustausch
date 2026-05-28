# ADR-0002: Integrate with DATEV via the klardaten gateway

- **Status:** Accepted (retroactive — reconstructed 2026-05-20)
- **Date:** 2026-05-12
- **Deciders:** Owner (sole developer)
- **Supersedes:** none
- **Related:** [ADR-0001](0001-resolver-perf-persisted-index.md);
  `docs/DATEV-DEVELOPER-PORTAL.md`; `.claude/architecture/phase-0-brief.md`

## Context

Belegmeister automates a Steuerbüro's Beleganforderung workflow and must
read DATEV data (Vorgangsmappen, document master data, client master data)
and eventually write receipts back into DATEV Unternehmen Online. DATEV
offers three integration surfaces with very different operational profiles:

1. **DATEVconnect** — REST API that runs **inside the Kanzlei LAN** against
   the DATEV desktop stack. No internet endpoint; partner apps must run
   on-premise.
2. **DATEV Online APIs** (`/platform/`) — cloud OAuth2/OIDC APIs. Production
   access requires DATEV Marketplace approval (>25 active connections,
   customer interviews, strategic-fit review) — months of process, not
   suitable for a single Kanzlei's internal tool.
3. **klardaten** — third-party hosted gateway that exposes DATEVconnect
   plus webhooks as a regular cloud REST API with bearer-token auth.
   No marketplace approval required; no on-prem footprint.

The product is hosted on Hetzner (Germany) for GDPR residency; running an
on-prem connector at the Kanzlei is explicitly off the table.

## Considered options

Reconstructed retroactively; alternatives were not formally weighed at the time.

- **Option A — DATEVconnect direct.** Lowest latency to DATEV, but forces
  an on-prem deployment at the Kanzlei and a LAN-bound network model that
  contradicts the Hetzner hosting decision.
- **Option B — DATEV Online APIs direct.** Cleanest long-term, but the
  approval gate makes it infeasible for a v1 internal tool by a single
  developer.
- **Option C — klardaten gateway.** Cloud REST + webhooks + bearer auth.
  Trades a third-party dependency and per-call latency for shipping v1
  without an approval gate or LAN deployment.

## Decision

Use **klardaten** (`https://api.klardaten.com`) as the sole DATEV
integration surface. All DATEV reads and writes go through
`KlardatenClient` in `src/belegmeister/klardaten/client.py`.

## Consequences

- **Positive:** v1 ships without DATEV Marketplace approval or an on-prem
  connector. Authentication is a single bearer token, easy to rotate.
  Webhooks become an option for v2 without changing the integration model.
- **Negative / accepted:** Adds a third-party in the critical path; a
  klardaten outage is a DATEV outage for us. klardaten's API surface
  becomes our effective DATEV contract (and is empirically derived — see
  ADR-0001 and `docs/DATEV-DEVELOPER-PORTAL.md`; the DATEV portal itself
  is a JS-SPA that `WebFetch` cannot render).
- **Permanent finding (carried by ADR-0001):** klardaten's documents API
  has no server-side filter. `$filter`, `?number=`, by-number path lookups,
  and `$top` are silently ignored. Only `$skip` paginates; page is fixed
  at 1000. Any "find a binder by number" code must work within that
  primitive (resolved in ADR-0001 via a persisted index).
