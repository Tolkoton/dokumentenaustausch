# Phase 0 — Problem Discovery Brief (DRAFT)

**Project**: Belegmeister
**Status**: DRAFT — in flight, batch 1 of discovery Q&A in progress
**Last updated**: 2026-05-12

---

## 1. Problem statement (one paragraph)

A small German Steuerbüro (tax office; 2–5 internal bookkeepers) currently handles
**Beleganforderung** — the process of requesting missing receipts from Mandanten
(clients) for DATEV bookings that lack supporting documents — entirely manually:
bookkeepers identify a missing receipt during bookkeeping, email the Mandant with
the booking details, track whether and when the receipt arrives, send reminders,
and upload received receipts back to DATEV Unternehmen Online. The user wants an
internal tool that automates detection, outbound request, receipt collection
(no Mandant account required — Steuerboard-style upload link), arrival
notification to the assigned bookkeeper pool, reminder cadence, and ideally
direct upload of received receipts back to DATEV.

## 2. Greenfield or brownfield

**Greenfield**. No existing software for this workflow today; current process
runs in inbox + DATEV Unternehmen Online manually.

The system will *integrate* with existing systems (DATEV) but is itself new.

## 3. Primary stakeholders sketch

| Role | Description |
|------|-------------|
| Bookkeeper (internal user) | 2–5 staff at the Steuerbüro. Identifies missing receipts in DATEV, gets notified when receipts arrive, follows up. |
| Mandant (external recipient) | Client of the Steuerbüro. Receives Beleganforderung emails with upload link. **No account required** — interaction is one-shot email + upload page. |
| Kanzlei lead / partner | Owns the Steuerbüro; cares about Mandant experience, audit trail, GDPR compliance. |
| DATEV ecosystem | Source-of-truth for bookings and receipts. Integration target via Klardaten gateway (provisional). |

## 4. Hard constraints surfaced (so far)

- **DATEV ecosystem**: must integrate with DATEV (bookings now; Unternehmen Online upload **v2**).
- **Klardaten** is the planned integration path (per session 2 research — OAuth/JWT + webhooks + DATEVconnect reverse proxy). This avoids "must run in Kanzlei LAN" and "DATEV Marketplace approval" gates.
- **Hosting**: Hetzner instance (Hetzner Cloud or Hetzner Dedicated, Germany). German data residency, sovereign hosting — strong GDPR alignment. NOT Azure-resident even though identity is M365.
- **Microsoft 365 is the existing email + identity infra**. Outbound Beleganforderung emails should go through the Kanzlei's M365 mailbox(es) (Microsoft Graph `sendMail` or SMTP-relay); bookkeeper auth should use the Kanzlei's M365 tenant (Microsoft Entra ID / Azure AD via OIDC/OAuth2 from our Hetzner-hosted app).
- **GDPR**: German tax-office context, regulated personal data of Mandanten and Mandant bookkeeping documents.
- **No Mandant accounts**: Mandant-side UX must be account-less (Steuerboard-style upload link).
- **Quick-win first, then iterate**: user wants pragmatic v1, not a platform.
- **Reference comparators**: taxflow, Steuerboard (NOT to be copied — comparators only).

### v1 vs v2 scope (as currently scoped)

- **v1**: detect missing-receipt bookings → email Mandant with upload link → collect file at our endpoint → notify bookkeeper pool → 3 reminders on fixed weekdays → escalate to bookkeeper if no reply → bookkeeper downloads file from our app and uploads to DUO manually.
- **v2**: auto-forward received receipts into DATEV Unternehmen Online (eliminates the manual upload step). Blocker for v1: the system must determine the **target DUO location** (which Mandant, which document binder / period / type) for a given booking — until that's reliable, upload can't be automated. This is a Phase 2 question.

### Deadline / budget / team

- **Deadline**: no hard external deadline stated. Implicit pressure is "quick-win first".
- **Budget**: not stated; assumed small internal-tool budget (no external customer paying yet).
- **Team**: 1 developer (the user) + the 2–5 bookkeepers as domain experts / pilot users.

### Tech stack preference

- **Python 3.11+ with strict typing** (per the user's global project policy in `~/.claude/CLAUDE.md`: Pydantic models everywhere, `mypy --strict`, TDD-first). This is a hard constraint, not a preference — it applies to all of the user's projects.

## 5. Quality attribute hints (raw material for Phase 1 QASes)

| Hint | Source signal |
|------|---------------|
| **Throughput** | 100–200 Beleganforderungen **per bookkeeper per month** → at 2–5 bookkeepers, **firm-wide ~200–1,000/month** (≈10–50 created per business day). Sustained low-throughput workload; not a high-scale system. |
| **GDPR-compliant data handling** | "GDPR-bound" in initial brief. |
| **Operational simplicity** | "Quick-win first" + small team (2–5). Implies low-ops deployment preference. |
| **DATEV write-back reliability** (v2) | Auto-forward to DUO in v2 → retry / dead-letter required when shipped. |
| **Reminder timeliness** | "Reminder cadence twice a week" → scheduling/timing must be predictable. |
| **Email deliverability** | Outbound from Kanzlei M365 mailbox → SPF/DKIM/DMARC must be respected; Mandant inboxes are external (varied providers). |

## 6. Domain glossary seeds

| Term | Definition (working) |
|------|----------------------|
| **Beleg** | Receipt / supporting document for a bookkeeping entry. |
| **Beleganforderung** | The act of requesting a missing Beleg from a Mandant. |
| **Mandant** | Client of the Steuerbüro (typically a small business or self-employed). |
| **Steuerbüro / Kanzlei** | Tax office; the firm that does bookkeeping for Mandanten. |
| **DATEV** | German bookkeeping and tax software ecosystem (dominant in this segment). |
| **DATEV Unternehmen Online (DUO)** | DATEV's web portal where receipts are uploaded and shared between Mandant and Steuerbüro. |
| **DATEVconnect** | DATEV's on-prem REST API for partner integrations. |
| **Klardaten** | Third-party gateway exposing DATEVconnect as a hosted API + webhooks for partner apps. |
| **Ungeklärte Buchungen (account 1370)** | DATEV account commonly used to flag bookings whose nature/receipt is unclear — candidate detection mechanism. |

## 7. Open questions / known unknowns (in flight)

These are the questions whose answers are partial, ambiguous, or not yet given.
Will be resolved in batch 1 follow-up below.

**Known unknowns to carry into Phase 1** (will not block Phase 0 approval — flagged for Phase 1 to resolve or accept):

- **DUO target resolution**: for a given missing-receipt booking, how do we determine *where* in DATEV Unternehmen Online a Beleg should be uploaded? (Mandant + binder + period + document type.) Needed to make v2's auto-upload work and to inform v1's handoff UX. **Phase 2 question.**
- **Audit / data retention horizon**: how long do we keep Beleganforderung records and copies of uploaded Belege after the bookkeeper has uploaded to DUO? German tax-relevant data retention is typically 10 years for accounting records — does that apply to our pass-through copies or only to the canonical DATEV record? Decision: keep this as a known unknown; address in Phase 1 NFRs.
- **Mandant authentication on the upload page**: do we require *any* friction on the Mandant side (link + token; link + emailed PIN; link only) to mitigate phishing/abuse? Phase 1 quality-attribute question.
- **N=3 reminder weekday selection**: confirmed cadence (Tue/Thu fixed weekdays); confirmed N=3. Open: at what time of day? Configurable per Kanzlei? (Low-stakes; can be defaulted.)
- **DATEV access-rights → bookkeeper-pool mapping mechanics**: how is the access-rights metadata read (per Mandant, via DATEVconnect endpoints exposed through Klardaten)? **Phase 2 question.**

## 8. Early risks

- **R1 — DATEV integration brittleness**: Klardaten / DATEVconnect APIs can break or be rate-limited; upload-to-DUO step has more failure modes than the email-out step.
  *Mitigation idea*: queue with retry + dead-letter; surface failed uploads to bookkeeper.
- **R2 — Mandant trust on upload link**: Mandanten get a link from a domain they may not recognize; phishing-shaped emails get ignored or reported.
  *Mitigation idea*: send from Kanzlei domain (DKIM/DMARC); branded landing page.
- **R3 — GDPR scope**: storing copies of receipts (which contain personal/financial data) extends retention obligations significantly. v1 may want to be a *pass-through* (Mandant → DATEV) without long-lived storage.
- **R4 — Account 1370 false positives**: if detection only watches account 1370, bookkeepers who don't use that account consistently will under-trigger. Need multi-signal detection or a manual "flag this booking" path.

## 9. Recorded Q&A (this session)

Batch 1 of discovery questions was posed (per PROGRESS.md session 2). The actual
question texts from the prior batch were not persisted in this directory; the
following entries reconstruct what was asked from the user's quoted answers.

### Answered (partial)

- **Q6 — Bookkeeper ↔ Mandant assignment: 1:1, or pool? Who gets notified on receipt arrival?**
  → *Pool routing. The pool can be derived from DATEV access rights.*
  Implication: the system must read DATEV access-rights metadata (per Mandant)
  to determine which bookkeeper(s) get notified. This is a non-trivial
  integration touchpoint and a candidate Phase 2 ADR.

- **Volume question (number unclear in batch — likely Q12 "scale")**
  → *"100-200"*. Unit ambiguous — clarification requested below.

- **DATEV upload back-flow**
  → *"Ideally receipt should be uploaded to DATEV"* — followed by clarification:
  *"Auto-forward received receipts into DATEV Unternehmen Online for v2"*.
  v1 stores received files at our endpoint and notifies the bookkeeper pool; v2
  closes the loop by pushing into DUO automatically.

- **Reminder cadence**
  → *"Twice a week"*.
  Open follow-ups: fixed weekdays? configurable per Mandant? cap on reminders?

- **Email + identity infrastructure**
  → *"Existing email + identity infra: M365"*.
  Implication: outbound emails via Microsoft Graph or M365 SMTP relay; bookkeeper
  auth via Entra ID (Azure AD); the Kanzlei domain's SPF/DKIM/DMARC are
  M365-anchored — sender-policy work for our app should align.

- **Volume unit clarification**
  → *"Per month, per bookkeeper"*. At 2–5 bookkeepers ⇒ **200–1,000 Beleganforderungen/month firm-wide** (≈10–50/business day). Low-throughput workload.

- **Hosting**
  → *"Some Hetzner instance"*. German cloud/dedicated hosting; data stays in DE — strong GDPR alignment. App runs at Hetzner; identity remains in M365 (Entra ID via OIDC); email egress through M365 Graph/SMTP.

- **Detection mechanism (multi-signal)**
  → All four signals selected:
  (a) bookings on account 1370 "Ungeklärte Buchungen",
  (b) bookings with a flag/comment from the bookkeeper,
  (c) bookings missing a linked DUO document,
  (d) manual "request Beleg" action from our UI.
  Implication: detection is a **pipeline** with multiple inputs and a deduplication step (same booking should not trigger twice). Worth a Phase 2 component diagram.

- **Reminder ceiling policy**
  → *"Stop after N reminders + escalate to bookkeeper"*. Confirmed: **N=3, fixed weekdays Tue/Thu**; escalation = mark "stuck" + notify bookkeeper pool.

- **Mandant email source**
  → *"From DATEV master data via Klardaten"*.
  Implication: a Mandant contact-email lookup against Klardaten/DATEVconnect is on the critical path. If a Mandant has no email on file, the system must surface that to the bookkeeper as an actionable error (not silently fail).

- **Beleg storage in v1**
  → *"Upload to DATEV ideally, but this requires generated link to know where exactly it needs to be uploaded."*
  Interpretation: the user *wants* direct DATEV upload even in v1, but recognizes the dependency on knowing the DUO target location (Mandant/binder/period/type). The pragmatic split:
  - v1 stores the file at our endpoint *as a holding step*, not as a long-term archive.
  - Bookkeeper retrieves and uploads to DUO manually in v1 (and that handoff UX is part of v1 scope).
  - v2 closes the loop when DUO target resolution is solved.

- **Success metric**
  → *"If it just works is success, we can't measure bookkeeper or client."*
  Honest "no quantitative KPI" — the win is qualitative: bookkeepers stop chasing receipts manually. Implication for Phase 1: don't over-invest in metrics/dashboards. Operational signals (queue length, stuck requests, failed sends) are enough.

### Pending (not yet answered)

Remaining batch 1 questions not yet seen in conversation. Will be re-listed
in the next follow-up batch (see PROGRESS.md).
