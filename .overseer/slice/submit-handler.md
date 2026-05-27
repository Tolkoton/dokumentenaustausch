# Slice submit-handler — planning artifact

## Goal

After this slice, when a Mandant submits the magic-link form (text
answers + optional freeform Anmerkungen + N attached files) via
`POST /r/{token}/submit`, the structured response data appears as a
`_response_<letter_id>_<ISO>.txt` document in the originating VGM AND
the uploaded files appear as siblings to that response document in the
same VGM, with the Mandant redirected to a confirmation page. SB opens
the VGM in DATEV-UO and sees both the response document and the
attachments. The submit handler enforces single-use token semantics
(presence of a `_response_<letter_id>_*` marker in the VGM is the
"already submitted" check, per ADR-0006). Partial-success on multi-file
upload is committed honestly to the response doc's inventory rather
than rolled back (klardaten has no DELETE proxy per ADR-0007).

Observable end-to-end: HTTP POST → DATEV-UO eyeball (or
`list_structure_items` probe) confirms the new response doc + the N
attachment artifacts in the binder.

## Premise verified

All 8 (+1 verified-then-falsified) premises are FRESH, evidenced by
empirical artifacts. The A9 falsification is what drove the cascade
from "all-or-nothing rollback" (original D6) to "best-effort, no
rollback" (revised D6 + ADR-0007).

| # | Assumption | Evidence | Status |
|---|------------|----------|--------|
| A1 | Klardaten accepts multi-file 2-step upload for arbitrary common MIME types (PDF, JPG). | `artifacts/spikes/submit-multi-file-upload-2026-05-26.json` — PDF 7.2 MB + JPG 5.8 MB both 200. | ✅ VERIFIED 2026-05-26 |
| A2 | `KlardatenClient.attach_file_to_binder` exposes the upload seam reusably. | `src/belegmeister/datev/upload.py` `upload_to_binder` + `BinderClient` Protocol used by `create_request.py`. | ✅ VERIFIED (current src) |
| A3 | Token (post token-instance-binding) carries `letter_id`; submit handler can re-fetch the exact letter Mandant saw. | token-instance-binding slice CODE COMPLETE 2026-05-26 (PROGRESS.md). `parse_request_letter` exists (`request_format.py`, slice 4a). | ✅ VERIFIED (current src) |
| A4 | SB sees Mandant-uploaded files in DATEV-UO without any notification mechanism. | `artifacts/spikes/submit-sb-discovery-2026-05-26.md` — verdict CONFIRMED via colleague-eyeball; notification: NONE. | ✅ VERIFIED 2026-05-26 (caveat: colleague-proxy observation, not owner-direct) |
| A5 | Klardaten accepts realistic Mandant upload sizes (25–200 MB). | `artifacts/spikes/klardaten-size-envelope-2026-05-26.json` — 25/50/100/200 MB all 200; `max_confirmed_mb=200`. | ✅ VERIFIED 2026-05-27 (untested above 200 MB) |
| A6 | `POST /r/{token}/submit` returns 404 today (no clashing handler). | PROGRESS.md slice-3 smoke; magic-link-ui smoke. | ✅ VERIFIED |
| A7 | Stateless tokens carry no replay protection today. | `src/belegmeister/magic_link/token.py` is pure HMAC. | ✅ VERIFIED (current src — this is as-is fact; policy is D2) |
| A8 | FastAPI multipart `List[UploadFile]` + scalar `Form` mixed in one request. | python-multipart added in 4b; documented FastAPI behavior. | ✅ ACCEPTED on framework docs + loud-vs-silent-failure reasoning (first integration test catches loudly) |
| A9 | Klardaten supports DELETE on `/document-files/{id}` and `/documents/{vgm}/structure-items/{id}` as a rollback primitive. | `artifacts/spikes/klardaten-delete-semantics-2026-05-26.json` — every DELETE returned 404 with empty body; file persists post-DELETE; `supports_all_or_nothing_rollback=false`. | ❌ **FALSIFIED 2026-05-27** — drove D6 cascade to best-effort; see ADR-0007 |

**Operational implication beyond this slice (A9 fallout):** klardaten
gateway provides NO API-driven cleanup path. ALL file removal is
DATEV-UO manual. Carried forward to PROGRESS.md and ADR-0007.

## Out of scope (deliberate)

1. **Notification channel to SB** — A4 confirmed; future enhancement if friction reports.
2. **File-size client-side cap below 200 MB** — A5 verified envelope; defensive cap without evidence adds UX friction.
3. **PDF/A conversion, virus scanning, MIME sniffing, file content validation** — security hardening; separate threat-model slice.
4. **Edit / resubmit / "wrong file" flow** — UX enhancement; replay policy intentionally blocks it.
5. **Per-question file attachment** (Q1's file vs Q3's file) — UI complexity; MVP is one bucket of files.
6. **SB feedback UI / dashboard** — separate SB-side slice.
7. **Mandant cancellation / opt-out flow** — not typical magic-link concern.
8. **Cleanup of probe pollution in VGM 395357** + smoke pollution this slice generates — operational hygiene; smoke can use fresh dev VGM if pollution interferes.
9. **Magic-link expiry handling beyond existing `token.exp` check** — already in `request_view`; this slice doesn't touch expiry.
10. **Mandant-supplied filename sanitization** — cosmetic; klardaten accepts; YAGNI.

## Decisions (with WHY)

### D1 — Response document codec

`src/belegmeister/web/response_format.py` (new). Serialize-only API
(no parse round-trip this slice; submit is write-once server-side).
Wire format mirrors 4a's `==BELEGMEISTER==` marker pattern with
response-specific sections: `type=antworten`, `letter_id`,
`submitted_at` metadata; Q/A pairs from positional answer list;
`==ANMERKUNGEN==` freeform section; `==ATTACHMENTS==` filename
manifest; `==FAILED_ATTACHMENTS==` failure inventory (added by D6).

WHY: SB reads both `_request_letter_*` and `_response_*` side-by-side
in DATEV-UO's text viewer; visual consistency lowers cognitive load.
Plain text needs no special tooling. Markers make it future-parseable
if a downstream slice needs round-trip.

Rejected: JSON (opaque to SB), YAML (opacity + indentation brittleness),
pure Q/A grid (no marker for letter_id binding), Markdown (no DATEV-UO
rendering benefit), append-to-letter (destroys audit trail).

**UNIT 1 implementation constraint:** `response_format.py` MUST
import `has_sentinel_collision` from `src/belegmeister/request_format.py`
(or refactor it to take a marker tuple if the marker set differs).
NO copy-paste. Per MEMORY[feedback_cross_layer_validation_extract].

### D2 — Replay policy

Single-use burn-on-success with in-binder state. **Burn marker:
presence of any `_response_<letter_id>_*.txt` in the target VGM.**

WHY: Zero new infrastructure. State lives with the data. Recovery
discoverable from DATEV-UO. Multi-process / multi-host safe via
klardaten as authoritative state. Establishes the
"binder-as-state-store" pattern for future slices.

Rejected: idempotency-key (needs separate cache + content-hashing
multipart is non-trivial), unlimited-within-exp (cluttered VGM on
double-click), in-memory dict (lost on restart), local SQLite (infra
surface for one boolean per token).

**Framing (post-Pushback 1):** defense-in-depth de-duplication, NOT
atomic single-use. JS lockSubmit covers same-tab double-click
(realistic 99% case); in-binder check covers deliberate replay (curl,
post-confirmation refresh, attacker resending captured token). True
cross-tab / cross-device concurrent submits have a small TOCTOU
window — accepted residual risk per ADR-0006. **Recovery requires
BOTH:** `_response_<letter_id>_*` deletion in DATEV-UO AND original
token's `exp` not yet passed.

→ Ratified by **[ADR-0006](../../docs/adr/0006-binder-as-state-store-for-replay-policy.md)**.

### D3 — File naming convention in VGM

- Response doc: `_response_<letter_id>_<ISO>.txt`
- Mandant attachments: `_attachment_<letter_id>_<8-char-uuid>_<original-filename-with-extension>`

WHY: Both share `_<letter_id>_` infix so SB visually groups response
doc + its N attachments in DATEV-UO's binder listing. UUID prevents
collision when Mandant uploads two files with same name
(e.g. `scan.pdf` × 2). Original filename preserved so SB has Mandant's
context (`_attachment_X_a1b2c3d4_Rechnung_Müller.pdf` — actionable;
not `_attachment_X_3.pdf`).

Rejected: verbatim-original (collision + no audit binding), sequential
renaming (loses Mandant context), UUID-only (no semantic info for SB).

### D4 — Error taxonomy expansion

New exception class `RequestSubmitFailed` (distinct from existing
`RequestLinkInvalid`). Five log_reason values:

- `upload_failed_all_files` — `files_attempted > 0 AND files_succeeded == 0`; bailout before response doc; token NOT burned.
- `upload_failed_response_doc` — files succeeded but response doc commit failed; orphan files remain; token state ambiguous (no marker).
- `replay_rejected` — D2 in-binder check fires.
- `empty_submit` — D7 predicate fails server-side.
- `multipart_parse_error` — FastAPI/python-multipart fails on malformed body.

WHY: GET-side errors (`RequestLinkInvalid`) mean "link is broken or
unauthorized"; recovery is "ask SB for new link." POST-side errors
mean "submission attempt failed"; recovery is "retry with same link"
(or contact SB on partial). Different semantic class; different
on-call escalation; different log analytics aggregation. Combining
muddies operational triage.

Rejected: reuse `RequestLinkInvalid` with new log_reasons (collapses
two different error semantics into one class).

**Module location for `RequestSubmitFailed`:** Phase-3 implementation
choice — either `src/belegmeister/web/errors.py` (new central) or
co-located with the handler in `web/app.py`. Slice contract does not
pin; consistency with `RequestLinkInvalid` (which lives in
`request_view.py` today) is the constraint to weigh.

### D5 — Confirmation page

Server-rendered HTML after POST (200 OK + page body). New template
`src/belegmeister/web/templates/submit_confirmation.html`. POST
handler returns it directly on success; no redirect, no new GET route.

WHY: Simplest implementation. No new GET route to defend. Browser
handles refresh-to-resubmit warning natively. Refresh actually
triggers re-POST → D2's replay check fires → returns
`already_submitted` banner.

Rejected: PRG-303-redirect (adds GET route surface + token-in-access-log
hazard per slice-3 SECURITY.md), inline flash on `/r/{token}` (extends
GET handler with submission-state branching).

**Three banner states** (single template; conditional banner block):

1. **`full_success`** — no banner; brief acknowledgment ("Ihre Antworten und Dateien wurden empfangen.").
2. **`partial_success`** — banner: *"Es wurden {n_succeeded} von {n_total} Dateien erfolgreich hochgeladen. Bitte kontaktieren Sie Ihre Steuerberatung, um die fehlenden Dateien nachzureichen."* (English: *"{n_succeeded} of {n_total} files uploaded successfully. Please contact your SB to retry the remaining files."*) **MUST NOT claim "SB has been notified"** — per A4, there is no notification mechanism.
3. **`already_submitted`** — banner (D2 replay-rejected path): *"Sie haben diese Anfrage bereits eingereicht. Ihre Antworten und Dateien sind beim Steuerberater eingegangen."*

Handler dispatches:

```python
try:
    result = orchestrate_submit(...)
    return render_confirmation(banner=result.banner_state)
except RequestSubmitFailed as exc:
    if exc.log_reason == "replay_rejected":
        return render_confirmation(banner="already_submitted")
    raise  # generic error path
```

### D6 — Best-effort multi-file upload, no rollback

Driven by A9 falsification. **No klardaten DELETE primitive exists;
all-or-nothing rollback is not implementable.**

Four explicit branches (each Phase-3-testable as a seam):

| Branch | Condition | Response doc | Token | Banner |
|---|---|---|---|---|
| Answers-only | `files_attempted == 0` | committed (empty `==ATTACHMENTS==`) | burns | `full_success` |
| All-failed bailout | `files_attempted > 0 AND files_succeeded == 0` | NOT written | NOT burned | (raises `upload_failed_all_files` → error page) |
| Partial-success | `files_attempted > 0 AND 0 < files_succeeded < files_attempted` | committed (`==ATTACHMENTS==` + `==FAILED_ATTACHMENTS==` populated) | burns | `partial_success` |
| Full-success | `files_attempted > 0 AND files_succeeded == files_attempted` | committed (clean `==ATTACHMENTS==`) | burns | `full_success` |

Rejected: all-or-nothing-with-DELETE (A9 falsified), commit-on-full-only
with self-serve retry (orphan-runaway), stop-on-first-failure
(misclassifies per-file as system), always-commit
(burns token on most-retry-able failure case), scratch-binder staging
(needs binder→binder primitive that doesn't exist), single-file MVP
(product-inadequate for Beleganforderung).

→ Ratified by **[ADR-0007](../../docs/adr/0007-best-effort-multi-file-upload-no-rollback.md)**.

### D7 — Empty-submit rule

Predicate: `≥1 file OR ≥1 non-empty answer OR non-empty Anmerkungen`.
Enforced BOTH client-side (JS disables Submit until predicate holds)
AND server-side (handler rejects with 422 + re-rendered form + error
banner if violated).

WHY: Client-side for UX (Mandant sees disabled button as feedback);
server-side for correctness (defense in depth; disabled JS / browser
quirks / scripted attacks can't bypass). Predicate is "any-one-of-N
nonempty" — has no HTML5-native form-validation; JS is ~15 lines;
server check is ~5 Python lines before any klardaten call.

Rejected: client-only (bypassable), server-only (bad UX — round-trip
for prevent-able-by-JS error), no-policy (silent empty submissions
clutter VGM).

**Cross-language constraint:** the predicate exists in two
implementations (JS + Python). Cannot be physically extracted to one
source. Spec lives in prose; mitigation is matching fixture tables on
both sides per Phase-3 reminder.

### D8 — Upload ordering: files first, continue past failures

Sequence (UNIT 3 implementation contract):

1. Validate token (existing `verify_token`) + replay check (D2 list_structure_items prefix match).
2. Parse multipart body (FastAPI multipart + `List[UploadFile]`).
3. Validate D7 server-side predicate.
4. For each Mandant file: attempt `attach_file_to_binder`; record per-file `AttachmentOutcome` (status + reason + IDs). **Continue past failures** — do NOT abort the loop.
5. Bailout check: if `files_attempted > 0 AND files_succeeded == 0`, raise `RequestSubmitFailed(log_reason="upload_failed_all_files")` BEFORE response doc commit. Token NOT burned.
6. Otherwise (any of the 3 commit branches in D6): serialize response doc via D1 codec referencing successful files' stored names (with UUIDs per D3); upload response doc. If THAT fails, raise `RequestSubmitFailed(log_reason="upload_failed_response_doc")`. Succeeded files become orphans.
7. Render confirmation template with appropriate banner state.

WHY: Files-first means response doc only commits when there is real
content to summarize. If response-doc-first, you'd roll back BOTH on
file failure (and rollback is impossible per A9). Per-file
`AttachmentOutcome` inventory schema is the codec's first non-trivial
branch.

Rejected: response-doc-first (creates inconsistency window),
interleaved/atomic (no klardaten transactional batch primitive).

## Hardest seams (with test approach)

### Seam 1 — D6 four-branch dispatcher

**Bug shape:** handler doesn't distinguish the four branches. Failure
modes: always-commits-response-doc, always-burns-token, bailout fires
on `files_attempted == 0` incorrectly, partial-branch never fires.

**Naive-test failure mode:** one test per branch, each happens to pass
because every branch eventually renders a 200 page. The branching
decision is never exercised. Anti-pattern: *"per-branch tests that
pass without touching the branch decision."*

**Wide test:** single parametrized test asserting THREE properties per
branch simultaneously:

- `response_doc_committed`: precise definition = "an `attach_file_to_binder` call with `file_name` matching `^_response_<letter_id>_.*\.txt$`" (regex pinned in test).
- `token_burned`: `_response_<letter_id>_*` present in mock binder state post-flow.
- HTTP-response identity: "non-2xx status + generic error page identity" vs "200 + specific banner-state template identity" (not pinning specific 5xx number).

Matrix per the D6 table above. 4 branches × 3 axes = 12 assertion-axes.
If any two branches collapse, at least one axis violates.

**Location:** `tests/web/test_app_submit_branching.py` (new).

### Seam 4 — Codec sentinel-collision safety

**Bug shape:** `response_format.py` serializer doesn't check whether
Mandant-supplied text (answers OR Anmerkungen OR D3-prefixed filename)
contains literal `==BELEGMEISTER==` or any section marker. Output has
nested markers; structural meaning corrupted.

**Naive-test failure mode:** round-trip of innocuous content PASSES;
the collision-detection predicate is never exercised. Anti-pattern:
*"innocuous-content round-trip passes; collision-detection logic
untested."*

**Wide test (3 positive + 1 negative fixture):**

- Positive: answer text containing literal `==BELEGMEISTER==` → assert raises.
- Positive: Anmerkungen containing literal `==FAILED_ATTACHMENTS==` → assert raises.
- Positive: original filename containing literal `==ATTACHMENTS==.pdf` → assert raises (predicate must apply to stored filenames too, not just text content).
- Negative: near-misses (`"== BELEGMEISTER =="` spaces; `"BELEGMEISTER"` no equals; case mismatch per 4a behavior) → assert BOTH (a) no exception raised AND (b) serialized output contains the near-miss content verbatim (rejects the silent-swallow bug).

**Location:** `tests/web/test_response_format.py` (new, mirroring 4a's
`tests/test_request_format.py` shape; web-only placement defensible
because the codec is web-only).

### Seam 6 — Response doc references stored filenames (not original)

**Bug shape:** response doc's `==ATTACHMENTS==` section embeds Mandant's
original filename instead of the post-D3 stored filename.

**Naive-test failure mode:** single Mandant file `"Rechnung.pdf"`;
assert `"Rechnung.pdf" in body` PASSES whether the doc embeds the
original (bug) or the stored `_attachment_<lid>_<uuid>_Rechnung.pdf`
(correct) — original is substring of stored. Anti-pattern: *"original
name is substring of stored name; substring assertion is contentless."*

**Wide test:**

- Two-files-same-original fixture: `"scan.pdf"` × 2 → distinct UUIDs in stored names → assert both UUIDs present in response doc body + regex assertion `"scan.pdf" not preceded by "_attachment_<lid>_"` pattern.
- Umlaut fixture: filename `"rechnung_ü.pdf"` → assert stored name appears verbatim (including umlaut, not URL-escaped or stripped) — catches "I 'sanitized' the stored name" regression.

**Location:** `tests/web/test_app_submit_inventory.py` (new) for
integration-level + `tests/web/test_response_format.py` for codec-level.

### Regular-difficulty tests (slice-required, not "hardest")

- Failure-reason categorization (parametrized 6-input pure function): `tests/web/test_response_format.py::test_failure_reason_from_klardaten_outcome`.
- In-binder replay check: `tests/web/test_app_submit.py::test_replay_check_*`.
- Banner-state derivation: `tests/web/test_app_submit.py::test_banner_state_from_outcome`.
- D7 server-side predicate (4 cases): `tests/web/test_app_submit.py::test_empty_submit_predicate_*`.
- lockSubmit JS template pin: `tests/web/test_app_route.py::test_get_form_renders_lock_submit_js`.

### Deferred from this Phase 3 (no infra)

- JS lockSubmit behavior under double-click — no browser-driver infra; Phase-4 manual smoke walkthrough if owner has bandwidth.
- Multi-file multipart parsing under real request shapes — A8 "loud-failure accepted on framework docs"; first integration test catches it.

## Exit criterion

Slice is DONE iff all 12 items green / produced.

### Hardest-Seam tests (3)

1. `tests/web/test_app_submit_branching.py::test_d6_four_branch_matrix` — Seam 1.
2. `tests/web/test_response_format.py::test_serializer_raises_on_marker_in_answer`, `…_in_anmerkungen`, `…_in_filename`, `test_serializer_preserves_near_miss_content_verbatim` — Seam 4 (4 tests).
3. `tests/web/test_app_submit_inventory.py::test_response_doc_embeds_stored_not_original_filenames` + `tests/web/test_response_format.py::test_serializer_embeds_filename_verbatim_with_umlaut` — Seam 6.

### Regular-difficulty tests (4)

4. `tests/web/test_response_format.py::test_failure_reason_from_klardaten_outcome` — parametrized 6 inputs.
5. `tests/web/test_app_submit.py::test_replay_check_*` — fires-when-present + passes-when-absent.
6. `tests/web/test_app_submit.py::test_banner_state_from_outcome` — parametrized (replay/outcome) → banner.
7. `tests/web/test_app_submit.py::test_empty_submit_predicate_*` — 4 cases.

### Template pin (1)

12. `tests/web/test_app_route.py::test_get_form_renders_lock_submit_js` — adjacent to the existing `:125` form-action pin.

### End-to-end smoke (1)

8. `scripts/smoke_submit_handler.py` owner-runnable:

```bash
uv run python scripts/smoke_submit_handler.py
```

Defaults dev VGM `4c83e94e-24e7-4866-809c-5e983ad7f485` (#395357).
Sub-scenarios:

- **Sub-A (full_success)** — mint token → POST 2 valid synthetic files + 2 answers + Anmerkungen → assert HTTP 200 + confirmation template + response doc with both UUIDs in `==ATTACHMENTS==` + 2 `_attachment_*.pdf` siblings via `list_structure_items`.
- **Sub-B (replay_rejected)** — immediately re-POST same token → assert HTTP 200 + `already_submitted` banner identity + binder count unchanged from Sub-A.
- **Sub-C (full_success answers-only)** — mint second token → POST 0 files + non-empty answers → assert HTTP 200 + `full_success` + response doc with empty `==ATTACHMENTS==` section.

Sub-D (partial_success) and Sub-E (all-files-failed) are deferred to
S1 unit-test coverage only. Justified: deterministically inducing
klardaten-side per-file rejection requires gateway-version-specific
malformed payloads. S1's mock-driven coverage is the authoritative
branch-correctness assertion; smoke covers wiring for Sub-A/B/C.

Output JSON: `artifacts/spikes/submit-handler-smoke-<YYYY-MM-DD>.json`
with per-sub `cross_assertion_pass` booleans + `overall_pass`.

Pollution per run: 1 response doc + 2 attachments + 1 second response
doc = 4 new structure-items in dev VGM 395357. Per ADR-0007 no-DELETE,
these persist; smoke script docstring documents "run minimally, not
iteratively during development".

### Gate cleanliness (1)

9. `uv run ruff check .` clean; `uv run mypy --strict src/ tests/ scripts/` clean (expected 57-60 source files post-slice); `uv run pytest tests/ -q` green (expected 216 baseline + ~15-20 slice-added; pinned to exact N at UNIT closure per token-instance-binding precedent).

### Slice closure artifacts (2)

10. **PROGRESS.md slice-closure entry** at head of file: "submit-handler — <DATE>". Includes 12-item exit table (PASS/FAIL with evidence path); smoke cross-assertion summary; final test count delta; ADR cross-references (0006 + 0007); commit message draft.
11. **`.overseer/ledger.md`** updated with `OVERSEER_SLICE_AWAITING_OWNER` per closure discipline.

### Disappearance-or-explain accounting

**ADDED (new files):**
- `src/belegmeister/web/response_format.py`
- `src/belegmeister/web/templates/submit_confirmation.html`
- `tests/web/test_response_format.py`
- `tests/web/test_app_submit.py`
- `tests/web/test_app_submit_branching.py`
- `tests/web/test_app_submit_inventory.py`
- `scripts/smoke_submit_handler.py`
- `docs/adr/0006-binder-as-state-store-for-replay-policy.md` (Accepted 2026-05-27)
- `docs/adr/0007-best-effort-multi-file-upload-no-rollback.md` (Accepted 2026-05-27)
- `scripts/probe_klardaten_size_envelope_2026-05-26.py` (Phase-0 spike; staged 2026-05-27)
- `scripts/probe_klardaten_delete_semantics_2026-05-26.py` (Phase-0 spike; staged 2026-05-27)
- `artifacts/spikes/klardaten-size-envelope-2026-05-26.json` (A5 evidence)
- `artifacts/spikes/klardaten-delete-semantics-2026-05-26.json` (A9 falsification evidence)

**MODIFIED:**
- `src/belegmeister/web/app.py` — gains POST `/r/{token}/submit` handler + `RequestSubmitFailed` exception handler registration.
- `src/belegmeister/web/templates/request.html` — gains lockSubmit JS handler on form (Phase 1 in-scope decision).
- Wherever `RequestLinkInvalid` lives today (`web/request_view.py`) — gains `RequestSubmitFailed` class with 5 log_reasons enum (or co-located in new `web/errors.py` per Phase-3 implementer choice).

**DELETED / REMOVED:** Nothing explicitly. The pre-existing implicit
`POST /r/{token}/submit` → 404 behavior is replaced by the new
handler; this is route-precedence change, not code deletion. Verified
empirically: `grep -rn "submit" tests/web/` shows the only existing
reference is `tests/web/test_app_route.py:125` asserting the GET-side
form's `action="/r/{token}/submit"` — that's a load-bearing pin for
the new handler's path (NOT a 404 assertion to migrate).

**RENAMED / MOVED:** Nothing.

## Unit decomposition (4 units)

| Unit | Scope | Files | Sentinel on completion |
|------|-------|-------|------------------------|
| **UNIT 1 — Response codec** | `response_format.py` with sentinel-collision predicate imported from `request_format.py` (NO copy-paste per MEMORY); S4 tests + S6 codec-level test. Pure functions; no HTTP, no klardaten. | `src/belegmeister/web/response_format.py`, `tests/web/test_response_format.py` | `=== UNIT 1 COMPLETE ===` |
| **UNIT 2 — Handler skeleton + branching dispatcher** | POST route in `web/app.py`; token verify; D7 server-side predicate; D2 in-binder replay check; D6 four-branch dispatcher (with stubbed file-upload loop); confirmation template skeleton + 3 banner states; `RequestSubmitFailed` exception class; lockSubmit JS in `request.html`; S1 branching matrix (mocked inventory inputs); banner-state derivation test; replay-check tests; D7 predicate tests; lockSubmit pin in `test_app_route.py`. **Sentinel framing:** "branching dispatcher correct against mocked-inventory inputs; loop stubbed for UNIT 3" — NOT "handler complete". | `src/belegmeister/web/app.py`, `src/belegmeister/web/templates/submit_confirmation.html`, `src/belegmeister/web/templates/request.html`, `tests/web/test_app_submit.py`, `tests/web/test_app_submit_branching.py`, `tests/web/test_app_route.py`, plus error-class home (Phase-3 implementer pick) | `=== UNIT 2 COMPLETE === (handler skeleton + branching matrix; loop stubbed for UNIT 3)` |
| **UNIT 3 — Real file-upload loop + inventory** | Continue-past-failures sequential loop in handler; `AttachmentOutcome` inventory construction; failure_reason categorization; D8 ordering (files first, then response doc); S6 stored-filename integration test; S2 failure_reason parametrized test. | `src/belegmeister/web/app.py` (loop replaces UNIT-2 stub), `tests/web/test_app_submit_inventory.py` (new), `tests/web/test_response_format.py` (S2 cases) | `=== UNIT 3 COMPLETE ===` |
| **UNIT 4 — Smoke + closure** | `scripts/smoke_submit_handler.py` Sub-A/B/C against real klardaten with JSON evidence; PROGRESS.md slice-closure entry; ledger `OVERSEER_SLICE_AWAITING_OWNER`. | `scripts/smoke_submit_handler.py`, `PROGRESS.md`, `.overseer/ledger.md` | `OVERSEER_SLICE_AWAITING_OWNER: <closure message including smoke output path>` |

## Deferred to later slices (19)

1. **Notification channel SB-on-Mandant-submit** — A4 confirmed not needed for MVP; future if friction reports.
2. **File-size client-side cap below 200 MB** — A5 envelope verified; cap without evidence is friction.
3. **PDF/A conversion, virus scan, MIME sniff, content validation** — security hardening; threat-model slice.
4. **Edit / resubmit flow** — replay policy intentionally blocks; future product call.
5. **Per-question file attachment** — UI complexity; MVP is one bucket.
6. **SB feedback UI / dashboard** — separate SB-side slice.
7. **Mandant cancellation / opt-out** — not typical magic-link concern.
8. **Cleanup of probe + smoke pollution in VGM 395357** — operational hygiene; ADR-0007 no-DELETE means manual DATEV-UO only.
9. **Magic-link expiry handling beyond `token.exp`** — already in `request_view`; this slice doesn't touch.
10. **Mandant-supplied filename sanitization** — cosmetic; YAGNI.
11. **Concurrent submit / multi-tab TOCTOU beyond JS lockSubmit + in-binder check** — ADR-0006 accepted residual risk.
12. **Client-side form-state persistence (localStorage)** for the bailout-retry case — ADR-0007 typed-answers-lost consequence; future enhancement.
13. **`response_format.py` parse / round-trip API** — serialize-only this slice; downstream consumers (analytics, search, audit) may need parsing later.
14. **Klardaten DELETE re-verification** if vendor ships it later — A9 spike retained for re-running.
15. **Smoke Sub-D (partial_success) + Sub-E (all-files-failed) against real klardaten** — gateway-version-specific induction; S1 unit tests cover branch correctness.
16. **Production deployment of `/r/` (public hosting)** — separate slice per PROGRESS.md `magic-link-ui` "Future open-item"; deployment character, not code-slice character.
17. **Multi-axis failure_reason categorization** (elapsed_s, error_class beyond HTTP status) — single-axis sufficient for MVP; future if SB diagnostic depth needs more.
18. **Rate limiting on POST `/r/{token}/submit`** — endpoint is unauthenticated by design (token IS the auth credential); MVP relies on token HMAC unguessability + `exp`-bound validity. Future hardening when production traffic reveals abuse patterns or scraping.
19. **i18n framework / non-German Mandant locales** — slice ships German-first banner text per ADR-0007 verbatim strings; English variant documented as fallback but no locale-detection wired. Future internationalization deserves its own slice with locale-resolution conventions, translation catalog, fallback semantics.

## Open items requiring human decision

None outstanding. All decisions ratified through the planning
conversation:

- Phase 0 premises A1-A8: verified empirically; A9 falsified empirically.
- Phase 1 goal + scope + OOS: locked.
- Phase 2 D1-D8: locked (with D2 reframe + D6 cascade + D4 expansion + D5 banner copy + D8 ordering all per pushback ratification).
- Phase 3 hardest seams S1/S4/S6: locked with concrete fixture designs.
- Phase 4 exit criterion: 12 items + disappearance accounting empirically verified.
- Phase 5 deferred: 19 items, each with WHY-LATER.
- ADR-0006 + ADR-0007: drafted, Accepted 2026-05-27.

UNIT 1 may now enter implementation.
