# Phase 1 — System Design (DRAFT)

**Project**: Belegmeister
**Maps to**: C4 Context + Quality Attribute Scenarios
**Inputs**: `phase-0-brief.md` (APPROVED 2026-05-12)
**Track**: BASIC

---

## 1. System vision (one paragraph)

Belegmeister is an internal tool for a small German Steuerbüro (2–5 bookkeepers)
that **automates the Beleganforderung loop** — the repetitive task of asking
Mandanten (clients) for missing receipts that are needed to complete their DATEV
bookkeeping. It detects bookings that are missing supporting documents (using
multiple signals from DATEV), emails the affected Mandant a one-shot upload link
(no account required), collects the uploaded file, notifies the bookkeeper pool
responsible for that Mandant, sends fixed-cadence reminders, and escalates
unanswered requests back to the bookkeepers. Its purpose is to remove the
manual "chase the receipt" workflow from each bookkeeper's daily routine so the
team can spend its time on actual bookkeeping rather than email follow-up.

## 2. Stakeholders

| # | Role | Type | Primary concerns |
|---|------|------|------------------|
| S1 | **Bookkeeper** | Internal user (2–5 people) | Stop chasing receipts manually; trust the auto-flow; know what's stuck and why; finish a Beleganforderung with one click ("close + uploaded to DUO"). |
| S2 | **Mandant** | External recipient (clients of the Kanzlei; small businesses, self-employed). | Minimum friction to comply; clear instructions in German; trustworthy-looking email from the Kanzlei domain; mobile-friendly upload. |
| S3 | **Kanzlei lead / partner** | Internal owner | GDPR compliance; audit trail; Mandant experience; sustainable cost (this is internal tooling, not revenue). |
| S4 | **Developer (operator)** | Solo (the user) | Ops simplicity; observability; low maintenance burden; type safety + TDD discipline (per global policy). |
| S5 | **DATEV / Klardaten** | External system (not a person, but a stakeholder in the sense of "things that constrain us") | API stability; rate limits; authentication boundaries; webhook signature integrity. |

## 3. System context

### What Belegmeister depends on

- **DATEV ecosystem** (via Klardaten gateway):
  - **Bookings + master data** — read access to detect missing-receipt bookings and look up Mandant contact email + access-rights metadata.
  - **Webhooks** — `client` / `document` change events from Klardaten (HMAC-SHA256 signed) for near-real-time detection.
  - **Reverse-proxy DATEVconnect** — `https://api.klardaten.com/datevconnect/<path>` for direct DATEVconnect calls when needed.
  - **(v2 only)** Write access to DATEV Unternehmen Online for uploaded Belege.
- **Microsoft 365** (existing Kanzlei infra):
  - **Microsoft Graph / SMTP relay** for outbound Beleganforderung email through the Kanzlei mailbox(es).
  - **Entra ID (Azure AD)** for bookkeeper authentication (OIDC).
- **Hetzner (DE)** — hosting infrastructure (Cloud or Dedicated; data stays in Germany).

### What depends on Belegmeister

- **Bookkeepers' daily workflow** — replaces the manual "email Mandant, chase reply, upload to DUO" loop.
- **(v2) Mandant→DUO data flow** — closes the loop without bookkeeper intervention.

### Data flows

```
Mandant ──email──> Belegmeister  (browser → upload page → file)
Bookkeeper ──UI──> Belegmeister  (manual request / close / dashboard)
DATEV  ──webhook──> Belegmeister (booking / document change events via Klardaten)
Belegmeister ──read──> DATEV (master data, access-rights, document status; via Klardaten)
Belegmeister ──send──> Mandant inbox (via M365 Graph/SMTP, from Kanzlei domain)
Belegmeister ──notify──> Bookkeeper (in-app + optionally email)
Belegmeister ──write──> DATEV DUO (v2 only)
```

## 4. Key user journeys

### J1 — Auto-detected missing Beleg (account 1370 path)

1. Bookkeeper books a transaction in DATEV that lands in account 1370 "Ungeklärte Buchungen".
2. Klardaten fires a `document` webhook to Belegmeister.
3. Belegmeister verifies the signature, dedupes against any existing open request for the same booking, and creates a Beleganforderung.
4. System looks up the Mandant's email from DATEV master data; resolves the responsible bookkeeper pool from DATEV access-rights.
5. System emails the Mandant from the Kanzlei mailbox with: booking date, amount, narrative ("for the transaction of EUR 245.00 on 2026-04-12"), and a unique upload link.
6. Mandant clicks the link, lands on a Kanzlei-branded upload page, drops the file (PDF/JPG/PNG/HEIC), gets a confirmation.
7. Belegmeister stores the file in DE-region storage, marks the request "received", and notifies the bookkeeper pool in-app.
8. Any bookkeeper from the pool picks it up, downloads the file from Belegmeister, uploads to DUO manually, and clicks "close" in Belegmeister.

### J2 — Bookkeeper flag path

Same as J1, but step 1 is the bookkeeper marking a booking in DATEV with a flag/comment that Klardaten surfaces via webhook. From step 2 onward, identical to J1.

### J3 — Manual "request Beleg" path

Bookkeeper opens Belegmeister, picks a Mandant and a booking (or types booking details manually), clicks "Anforderung senden". Belegmeister composes and sends the email (steps 5–8 identical to J1). This is the fallback for cases the auto-detection misses.

### J4 — Reminder cycle + escalation

1. Beleganforderung is created on a Wednesday; no upload by next Tuesday (>4 days).
2. Tuesday 09:00 Europe/Berlin: reminder #1 fires.
3. No upload by Thursday: Thursday 09:00 reminder #2.
4. No upload by following Tuesday: reminder #3.
5. No upload by following Thursday: request transitions to "stuck"; bookkeeper pool is notified in-app (and optionally by email).
6. Bookkeeper takes over manually (phones Mandant, etc.), or closes the request as "abandoned".

### J5 — Mandant has no email on file (actionable error)

1. Detection fires for a booking whose Mandant has no email address in DATEV.
2. Belegmeister creates the Beleganforderung in **actionable-error** state with reason "Mandant missing contact email".
3. The bookkeeper pool sees it in the "needs attention" lane of the dashboard.
4. Bookkeeper either updates the Mandant's email in DATEV (triggers re-evaluation) or marks the request "handle offline" (closes without action).

### J6 — Klardaten unreachable (failure path)

1. Klardaten webhook delivery fails or Klardaten returns 5xx on a read call.
2. Belegmeister logs the failure, queues the affected work, and retries with exponential backoff.
3. No webhook events are lost (Klardaten retries on its side per HMAC delivery semantics; we accept idempotently).
4. When Klardaten recovers, the queue drains automatically; bookkeepers see no impact unless the outage exceeds the agreed-on lag tolerance (covered by QAS-04).

### J7 — Bookkeeper opens the dashboard

1. Bookkeeper signs in via the Kanzlei's M365 single-sign-on (one click if already signed in to their Outlook session).
2. Lands on a one-page dashboard showing: open requests by age bucket, stuck requests, actionable-error queue, recent closures.
3. Filters by Mandant or by responsible bookkeeper-pool. Clicks a request to see history (sent, reminders, received, closed) and the uploaded file.

## 5. Functional capabilities

The system can:

1. Detect missing-receipt bookings via four signals (account 1370 / bookkeeper flag / missing DUO link / manual UI action) and deduplicate to one Beleganforderung per booking.
2. Look up Mandant contact email from DATEV master data through Klardaten.
3. Resolve the responsible bookkeeper pool for each Mandant from DATEV access-rights metadata.
4. Generate a unique, unguessable upload link per Beleganforderung.
5. Compose Beleganforderung emails in German with booking details and the upload link, and send them from the Kanzlei's existing mailbox (so Mandanten see a familiar sender).
6. Receive uploaded Belege at a Kanzlei-branded web page; accept PDF, JPG, PNG, HEIC; size limit applies.
7. Store received Belege in DE-region storage, retained only as long as the workflow requires.
8. Notify the bookkeeper pool in-app when a Beleg arrives, when a request becomes "stuck", or when an actionable error occurs.
9. Schedule and send reminders on fixed weekdays (Tue/Thu, 09:00 Europe/Berlin) up to 3 times per Beleganforderung.
10. Escalate to bookkeeper pool when a request remains unanswered after 3 reminders.
11. Present an operational dashboard: open / received / stuck / actionable-error / closed; filter by Mandant or pool.
12. Allow a bookkeeper to manually create a Beleganforderung.
13. Allow a bookkeeper to download a received Beleg and mark the request closed.
14. Authenticate bookkeepers using the Kanzlei's existing single-sign-on (so signing in to Belegmeister is one click for someone already signed in to their work account).
15. Log access to Belege and to Mandant personal data for audit purposes.
16. Run with German data residency; no Mandant personal data leaves EU regions in normal operation.

## 6. Quality Attribute Scenarios (QASes)

### QAS-01: Detection-to-email latency

**Quality attribute:** performance / responsiveness

| Part        | Specification |
|-------------|---------------|
| Source      | DATEV (via Klardaten webhook) |
| Stimulus    | A `document` or `client` change event indicating a missing-receipt booking |
| Environment | Normal operations; Klardaten reachable; M365 reachable |
| Artifact    | Whole pipeline: webhook receiver → dedupe → compose → send |
| Response    | Beleganforderung email is dispatched to M365 |
| Measure     | p95 ≤ 2 minutes from webhook receipt to email accepted by M365; p99 ≤ 10 minutes |

**Rationale:** Bookkeepers expect that "the moment I book a 1370 entry, the Mandant gets the email" — but precise sub-minute latency is unnecessary. 2 min p95 keeps the experience trustworthy without forcing tight realtime requirements.

**Owner (Phase 2):** TBD

### QAS-02: Reminder firing reliability

**Quality attribute:** reliability / timeliness

| Part        | Specification |
|-------------|---------------|
| Source      | Internal scheduler |
| Stimulus    | A Beleganforderung is due for its scheduled reminder (Tue or Thu, 09:00 Europe/Berlin) |
| Environment | Normal operations; M365 reachable |
| Artifact    | Reminder scheduler + email sender |
| Response    | The reminder email is dispatched |
| Measure     | ≥99% of due reminders fire within ±15 minutes of the scheduled slot; 100% within ±2 hours; zero silently-dropped reminders over a 30-day window |

**Rationale:** A predictable cadence is the entire value proposition of the reminder feature; missed reminders erode bookkeeper trust faster than missed detections.

**Owner (Phase 2):** TBD

### QAS-03: Mandant upload-page availability

**Quality attribute:** availability

| Part        | Specification |
|-------------|---------------|
| Source      | Mandant |
| Stimulus    | Clicks the upload link from the Beleganforderung email |
| Environment | Public internet; arbitrary Mandant device (mobile/desktop, slow networks possible) |
| Artifact    | Upload page (web frontend + upload endpoint) |
| Response    | Page loads; file upload succeeds |
| Measure     | ≥99.5% successful uploads (HTTP 2xx final response) during business hours Europe/Berlin (Mon–Fri 07:00–20:00); ≥98.0% off-hours; planned-maintenance windows excluded |

**Rationale:** A failed upload after the Mandant has already opened the link is much worse than no email at all — they may not retry. Slightly relaxed off-hours target reflects the solo-developer ops reality.

**Owner (Phase 2):** TBD

### QAS-04: Klardaten outage tolerance

**Quality attribute:** recoverability

| Part        | Specification |
|-------------|---------------|
| Source      | External system (Klardaten) |
| Stimulus    | Klardaten unreachable (network partition or Klardaten 5xx) |
| Environment | Normal traffic; outage of up to 4 hours |
| Artifact    | Webhook receiver + Klardaten read client |
| Response    | Webhooks queued idempotently; read calls retry with backoff; no data loss; no duplicate Beleganforderungen on recovery |
| Measure     | Queue drains within 30 minutes of Klardaten recovery for outages ≤4 hours; zero duplicate Beleganforderungen per booking across the outage boundary |

**Rationale:** Klardaten is a third-party dependency we do not control; the only safe assumption is "it will be down sometimes". Idempotent intake is the only acceptable design.

**Owner (Phase 2):** TBD

### QAS-05: GDPR data minimization & deletion

**Quality attribute:** security / privacy

| Part        | Specification |
|-------------|---------------|
| Source      | Internal scheduler (data retention job) |
| Stimulus    | A Beleganforderung has been in "closed" or "abandoned" state for the configured retention horizon |
| Environment | Normal operations |
| Artifact    | Beleg storage + database |
| Response    | The uploaded Beleg file is irrecoverably deleted; the Beleganforderung metadata is anonymised (Mandant identifiers redacted, audit-relevant fields preserved) |
| Measure     | 100% of eligible records processed daily; zero retained files older than retention horizon + 24 hours; deletion auditable |

**Rationale:** GDPR demands data minimization. Holding Belege longer than needed is a liability without a corresponding benefit (the canonical copy lives in DATEV DUO once uploaded).

**Open**: retention horizon value is OQ-2 (default proposal: 30 days post-closure for v1).

**Owner (Phase 2):** TBD

### QAS-06: Upload link unforgeability

**Quality attribute:** security

| Part        | Specification |
|-------------|---------------|
| Source      | Unauthenticated attacker |
| Stimulus    | Attempts to upload to or read state from a Beleganforderung they were not the recipient of |
| Environment | Public internet |
| Artifact    | Upload page + upload endpoint + link generator |
| Response    | Access denied unless the request bears the exact token issued for that Beleganforderung; brute-forcing a token is computationally infeasible; expired/closed-request tokens are rejected |
| Measure     | Tokens have ≥128 bits of cryptographic entropy; tokens scoped to a single Beleganforderung; tokens expire on close or after 90 days, whichever is sooner; per-IP rate limit on the upload page |

**Rationale:** No Mandant account means the link IS the credential. If it leaks or is guessable, anyone can submit any file.

**Owner (Phase 2):** TBD

### QAS-07: Operability for a 1-developer team

**Quality attribute:** operability / maintainability

| Part        | Specification |
|-------------|---------------|
| Source      | Developer (during incident response or routine maintenance) |
| Stimulus    | Needs to diagnose why a Beleganforderung is stuck or why a reminder didn't fire |
| Environment | Production |
| Artifact    | Whole system (logs, dashboard, queue inspection) |
| Response    | The full lifecycle of any Beleganforderung (events, retries, errors, related external API calls) is reconstructable from logs + dashboard within minutes, without shell access to the production database |
| Measure     | ≤5 minutes from "user reports issue" to "developer has identified the root-cause event" for the top-5 expected failure modes (detection miss, send failure, Klardaten 5xx, file rejected, reminder missed) |

**Rationale:** Solo-dev ops reality: there is no on-call rotation, no SRE, no DBA. The system has to explain itself.

**Owner (Phase 2):** TBD

## 7. Constraints

### Hard

- **DATEV ecosystem** — bookings live in DATEV; we integrate via Klardaten (HTTPS, OAuth/JWT, webhook HMAC-SHA256 signing).
- **Klardaten** — initial integration path; concrete capabilities and quirks documented in `docs/klardaten.json` + `docs/DATEV-DEVELOPER-PORTAL.md`.
- **Microsoft 365** — outbound email + bookkeeper identity (Entra ID OIDC). No alternative providers in v1.
- **Hosting in Germany** — Hetzner Cloud or Hetzner Dedicated; data residency is DE; no egress of personal data to non-EU regions.
- **GDPR** — applies to Mandant personal data, booking narratives, uploaded Belege.
- **No Mandant accounts** — Mandant-side interaction is one-shot email + link; no login, no persistent session.
- **Python 3.11+ with strict typing** — Pydantic models everywhere, `mypy --strict`, TDD-first (RED/GREEN/REFACTOR). Inherited from the user's global project policy (`~/.claude/CLAUDE.md`) and the project's `CLAUDE.md` autonomy/safety hooks.

### Team / budget / deadline

- **Team**: 1 developer + 2–5 bookkeepers as pilot users and domain experts.
- **Budget**: no hard budget; internal tooling — costs measured in solo-developer-hours.
- **Deadline**: no hard external deadline. Implicit pressure is "quick-win first, iterate from there".

### Regulatory

- **GDPR** (always).
- **German tax-relevant record retention** — typically 10 years for accounting records. **Applies to the canonical record in DATEV**, not necessarily to our pass-through copies. OQ-2 to confirm with Kanzlei lead.

## 8. Out of scope (v1)

1. **Auto-upload to DATEV Unternehmen Online**. Belegmeister v1 holds the file; the bookkeeper retrieves and uploads manually. v2 closes this loop.
2. **Quantitative success-metric dashboards / analytics**. The user explicitly said "if it just works is success, we can't measure bookkeeper or client". Operational health signals only.
3. **Mandant accounts, login, persistent sessions, profile management**. One-shot tokenized link is the entire Mandant UX.
4. **Multi-Kanzlei / multi-tenant operation**. Single Kanzlei in v1; multi-tenancy is a re-architecture, not an enhancement.
5. **Non-DATEV bookkeeping systems** (Lexware, sevDesk, sage, etc.).
6. **Mobile-native Mandant app**. Web-only, mobile-responsive — that's enough.
7. **OCR / content extraction from received Belege**. We pass the file through unchanged.
8. **Per-Mandant configurable reminder cadence**. One global cadence (Tue/Thu, 3 reminders) in v1.
9. **Email providers other than M365 for outbound**. No Gmail-relay fallback, no third-party SMTP.
10. **Non-email notification channels for Mandanten** (no SMS, WhatsApp, push). Bookkeeper-side notifications may use M365 email or in-app only.
11. **Self-service onboarding for new bookkeepers**. Adding a new bookkeeper is a manual operation (assign in DATEV access-rights; pool membership updates on next sync).
12. **Public API for third parties to query Beleganforderung state**. Internal use only.

## 9. Open questions

Each is a known unknown blocking at least one Phase 2 decision. Each has a default proposal so Phase 2 can proceed if user defers.

### OQ-1 — DUO target resolution

> Given a booking with a missing receipt, how does the system determine the *exact* target location in DATEV Unternehmen Online (Mandant + binder/folder + period + document type) where an uploaded Beleg should land?

- **Why it blocks**: v2 auto-upload depends entirely on this; v1 dashboard UX is cleaner if the system can already show the bookkeeper where to upload.
- **Default proposal**: in v1, do *not* attempt to predict the DUO target — show the booking's Mandant + date + amount in the bookkeeper UI and let the bookkeeper choose. Defer auto-resolution to v2 when Klardaten/DATEVconnect coverage is verified.

### OQ-2 — Retention horizon for our holding storage

> How long do we keep an uploaded Beleg in our storage after the bookkeeper has marked the request closed?

- **Why it blocks**: QAS-05 needs a number; storage sizing depends on it.
- **Default proposal**: **30 days post-closure**, then irrecoverable deletion. Audit metadata (who, when, file hash) retained per the Kanzlei's standard audit retention. Confirm with Kanzlei lead.

### OQ-3 — Mandant upload-page authentication friction

> Is "secret token in URL" sufficient, or do we need a second factor (e.g., a 6-digit PIN emailed separately) for the Mandant to upload?

- **Why it blocks**: QAS-06 specifies the token strategy; adding a PIN doubles the Mandant-side friction.
- **Default proposal**: **token only**, with ≥128-bit entropy, per-request scope, and per-IP rate limit on the upload endpoint. Revisit if phishing or token-leak incidents occur.

### OQ-4 — Reminder time-of-day

> 09:00 Europe/Berlin on Tue/Thu? Or something else?

- **Why it blocks**: QAS-02 requires a specific scheduled slot.
- **Default proposal**: **Tue and Thu at 09:00 Europe/Berlin**. Configurable globally in Kanzlei settings, not per-Mandant.

### OQ-5 — Bookkeeper-pool resolution mechanics

> Which Klardaten/DATEVconnect endpoint exposes "who has access to this Mandant" so we can compute the bookkeeper pool?

- **Why it blocks**: J1/J2/J3/J7 all depend on "the right bookkeeper sees the notification".
- **Default proposal**: Phase 2 verifies via the Klardaten OpenAPI in `docs/klardaten.json` and proposes a polled-sync strategy (e.g., refresh pool memberships once per hour). If no suitable endpoint exists, fall back to a Belegmeister-internal Mandant↔pool mapping that the Kanzlei lead maintains.

### OQ-6 — Email-sending mechanism within M365

> Microsoft Graph `sendMail`? M365 SMTP relay? Exchange Online OAuth SMTP?

- **Why it blocks**: Phase 2 ADR; affects auth flow, delivery telemetry, send-as permissions on the Kanzlei mailbox.
- **Default proposal**: **Microsoft Graph `sendMail`** from a dedicated service principal with delegated permissions to send-as the Kanzlei mailbox. Best signal-of-delivery; aligned with Microsoft's recommended path.

### OQ-7 — Detection dedup correctness

> Across the four detection signals (1370 / flag / missing DUO link / manual), can a single booking trigger multiple Beleganforderungen? What's the canonical booking identifier across Klardaten payloads?

- **Why it blocks**: capability #1 (dedup) requires a stable key.
- **Default proposal**: Phase 2 verifies the Klardaten webhook payload shape and identifies a stable booking key (likely DATEV `Buchungsnummer` or a Klardaten-issued ID). If none is stable, fall back to a composite key (Mandant-ID + booking-date + amount + narrative hash) with explicit dedup window.

---

**End of Phase 1 system design (DRAFT).**

This document is the input to Phase 2 (Architecture). After Phase 2, this file does not change unless a Phase 2/3/4 critique surfaces a SCOPE-UPSTREAM flaw, in which case it is superseded and rewritten under a bumped version.
