# Architecture Progress Log

## Session 1 — 2026-05-12

### Phase 0 — Problem Discovery (DRAFT)

**Track**: BASIC (Phase 0 is always BASIC per skill rules).

**Initial brief from user** (summary):
- Internal tool for a German Steuerbüro automating **Beleganforderung** (requesting missing receipts).
- Today: bookkeepers manually email Mandanten when a DATEV booking lacks a receipt, track replies, send reminders, and upload received receipts to DATEV Unternehmen Online.
- Proposed system: detect missing-receipt bookings (via designated account such as 1370 "Ungeklärte Buchungen" or a flag field), email Mandant with transaction details + upload link (no Mandant account required, Steuerboard-style), notify bookkeeper on arrival, surface outstanding counts, send reminders, optionally auto-forward to DATEV Unternehmen Online.
- Users: 2–5 internal bookkeepers; Mandanten are external email recipients without accounts.
- Constraints: DATEV ecosystem, GDPR-bound, "quick-win" first then iterate.
- Deployment form: **explicitly open** — to be surfaced in Phase 0.
- Reference products (comparators only, not copying): taxflow, Steuerboard.

**Decisions / rationale so far**: none yet. No design decisions belong in Phase 0.

**Next action**: posed 10 discovery questions to user (4 structured + 6 open-text). Awaiting answers.

**Open questions parked for the brief**: will be populated from answers.

---

## Session 2 — 2026-05-12 (resumed)

### Context discovered before re-posing questions

- Reviewed `docs/DATEV-DEVELOPER-PORTAL.md` and `docs/klardaten.json` (OpenAPI of Klardaten DATEVconnect Gateway).
- Klardaten provides: (a) OAuth/JWT-protected reverse proxy to DATEVconnect at `https://api.klardaten.com/datevconnect/<path>`, (b) data-change webhooks for `client` and `document` entities with HMAC-SHA256 signature verification, (c) per-organization Windows-credential profiles stored at the on-prem connector (not at Klardaten), (d) API keys for machine-to-machine usage (`uk-...` bearer).
- This eliminates the "must run inside Kanzlei LAN" or "must obtain DATEV Marketplace approval" constraints that direct DATEVconnect/DUO integration would impose for a first iteration. Klardaten is a viable integration path and likely the fastest one for a quick-win.
- Prior session's 10 questions were not persisted to a DRAFT file. Re-posing in batch 1, informed by Klardaten findings (structured options for the integration-path question now include Klardaten explicitly).

### Q&A captured (across batches)

User answered in rapid-fire fragments rather than waiting on a single batch. Consolidated into `phase-0-brief.md.DRAFT` section 9. Highlights:

- **Volume**: 100–200 Beleganforderungen *per bookkeeper per month* → ~200–1,000/month firm-wide.
- **Bookkeeper ↔ Mandant routing**: pool, derived from DATEV access-rights metadata.
- **DATEV upload**: auto-forward to DUO is **v2**, not v1. v1 hands off via bookkeeper download/manual upload. Blocker: target DUO-location resolution (Mandant/binder/period/type) is unsolved.
- **Reminder cadence**: 3 reminders, fixed weekdays (Tue/Thu), then escalate to bookkeeper pool.
- **Hosting**: Hetzner instance (DE) — strong GDPR alignment.
- **Identity + email**: M365 (Entra ID for bookkeepers, Graph/SMTP for outbound).
- **Detection signals**: all four — account 1370, bookkeeper flag/comment, missing DUO link, manual UI action. Implies a detection pipeline with dedup.
- **Mandant email source**: DATEV master data via Klardaten.
- **Success metric**: qualitative — "if it just works". No quantitative KPI.

### Decisions / rationale

- **No quantitative KPI in v1** — user explicit. Phase 1 should not invest in metrics/dashboards beyond operational health.
- **v1 keeps a holding-storage step for Belege** — not a long-term archive, just a buffer until bookkeeper uploads to DUO manually.
- **Brief length 179 lines** — within the 100–300 target.

### Critique pass (1 round)

Discovery-critique checklist run mentally against `phase-0-brief.md.DRAFT`:
- Two SCOPE-LOCAL gaps found and patched (deadline/budget statement; Python tech-stack constraint inherited from global CLAUDE.md).
- 5 SCOPE-EXTERNAL items accepted as known unknowns (carried to Phase 1) rather than triggering a 3rd Q&A batch: DUO target resolution, GDPR retention horizon, Mandant upload-page auth friction, reminder time-of-day, DATEV-access-rights → pool mechanics. All are Phase 1/2 work.

**Next action**: present `phase-0-brief.md.DRAFT` to user for approval (`approved` / `revise: ...` / `reject`).

### Phase 0 APPROVED — 2026-05-12

User approved the brief. Renamed `phase-0-brief.md.DRAFT` → `phase-0-brief.md`; INDEX.md updated.

**Handoff to Phase 1 inputs**:
- Brief: `.claude/architecture/phase-0-brief.md`
- 5 known unknowns to track as Phase 1 "Open questions" (DUO target resolution, GDPR retention, Mandant upload-page auth, reminder time-of-day, DATEV access-rights → pool mechanics)
- Quality-attribute hints from brief §5 are raw material for Phase 1 QASes
- Glossary seeds from brief §6 are starting glossary
- Tech-stack constraint: Python 3.11+ / Pydantic / mypy --strict / TDD-first (inherited from user's global policy)

**Next action**: enter Phase 1 (System Design). Run STAKES ASSESSMENT first to choose BASIC vs DEEP track.

---

## Session 2 — 2026-05-12 (Phase 1)

### Stakes assessment

- *reversibility_low*: NO (descriptive only)
- *blast_radius_systemic*: PARTIAL (drives Phase 2; recoverable via SCOPE-UPSTREAM)
- *novelty_high*: NO (DATEV/Steuerbüro is established territory)
- Verdict: **BASIC track**.

### Generated

`phase-1-system.md.DRAFT` (353 lines, single-pass). Sections 1–9 complete:
1. One-paragraph vision
2. Stakeholders (S1–S5: bookkeeper, Mandant, Kanzlei lead, developer, DATEV/Klardaten as external context)
3. System context (depends-on / depended-by / data-flow ASCII)
4. 7 user journeys (J1–J7, including 2 failure paths: Klardaten outage, missing-email actionable error)
5. 16 functional capabilities (user-visible outcomes, no tech names)
6. 7 QASes (perf, reliability, availability, recoverability, GDPR/privacy, security/token, operability)
7. Constraints (hard: DATEV+Klardaten, M365, Hetzner DE, GDPR, no Mandant accounts, Python+Pydantic+TDD; team/budget/deadline; regulatory)
8. Out-of-scope: 12 specific items
9. 7 open questions (OQ-1..OQ-7), each with a default proposal so Phase 2 can proceed if user defers

### Critique pass (1 round, BASIC)

- Checklist run mentally against `checklists/system-critique.md`. All items PASS except:
  - **Capability tech-name leak** (capabilities #5, #14, #16 named M365/Entra/Hetzner explicitly). Classified SCOPE-LOCAL; rephrased to user-visible properties; tech names remain only in §7 Constraints. Also softened the same leak in journey J7.
- No SCOPE-UPSTREAM flaws found (Phase 0 brief is consistent with the design).
- Karpathy pre-action checks (silent assumptions, over-complication, unrequested scope): no findings.

### Decisions / rationale

- **No DEEP-track escalation** — Phase 1 is descriptive and the domain is well-trodden.
- **OQ defaults included inline** so Phase 2 isn't blocked if user wants to defer.
- **Reminder cap N=3** baked into the design (per user); **OQ-4** asks only about time-of-day.
- **Functional capability "operate in DE region"** kept as user-visible property; "Hetzner" stays in Constraints only.

**Next action**: present `phase-1-system.md.DRAFT` to user for approval.

### Phase 1 APPROVED — 2026-05-12

User approved the system design. Renamed `phase-1-system.md.DRAFT` → `phase-1-system.md`; INDEX.md updated.

**Handoff to Phase 2 inputs**:
- System design: `.claude/architecture/phase-1-system.md`
- 7 QASes (QAS-01..QAS-07) — Phase 2 components must satisfy each; record owner per QAS.
- 7 open questions (OQ-1..OQ-7) — each has a default proposal; Phase 2 must either ratify the default (with rationale) or propose alternative.
- Constraints from §7 are non-negotiable inputs to Phase 2 ADRs.
- 16 functional capabilities are the scope edge for Phase 2 components.

**Next action**: enter Phase 2 (Architecture). Run STAKES ASSESSMENT — likely DEEP track given novelty of multi-signal detection pipeline + dual-platform integration (DATEV/Klardaten + M365 Graph + Hetzner DE residency) is the kind of cross-cutting territory where ToT can pay off.
