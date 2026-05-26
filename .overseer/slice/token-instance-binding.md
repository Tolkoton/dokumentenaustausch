# Slice token-instance-binding — planning artifact

## Goal

Replace the magic-link token's VGM-only binding with a per-letter binding.
After this slice, `GET /r/{token}` deterministically loads the specific
`_request_letter_*` the SB user generated at mint time, even when newer
letters have been added to the same VGM. The "newest letter wins" bug
that the magic-link-ui smoke caught (PROGRESS.md `magic-link-ui` section:
"BLOCKS PRODUCTION /r/ HOSTING") is fixed by construction; the read path
no longer guesses. Token payload becomes `{vgm_id, letter_id, exp}` —
one field per concern. No backwards-compat with the old `{vgm_id, exp}`
shape; no production tokens exist, so the cut is clean.

## Premise verified

| # | Assumption | Evidence | Freshness |
|---|------------|----------|-----------|
| P1 | Each `_request_letter_*` in a VGM has identifiers (`id`, `document_file_id`, `counter`) distinct across letters in the same binder. | `artifacts/spikes/submit-letter-discovery-2026-05-26.md` — 17 letters in VGM 395357, all four identifier columns unique. | FRESH 2026-05-26 |
| P2 | Those identifiers are stable across re-reads. | `artifacts/spikes/token-instance-binding-id-stability-2026-05-26.json` — re-listing of VGM 395357 at 10:40 UTC vs original probe at ~10:23 UTC: every `(id, document_file_id, counter, creation_date)` tuple byte-identical across all 17 letters. | FRESH 2026-05-26 |
| P3 | The mint side already has the letter's identifier in hand at token-mint time. | `src/belegmeister/datev/upload.py:212-223` — `UploadResult.document_id` IS the structure-item `id` (string). | FRESH (current source) |
| P4 | The read side can fetch a specific letter via `klardaten.download_document_file(int) -> bytes`. | `src/belegmeister/klardaten/client.py:270`; `src/belegmeister/web/request_view.py:290-303` already uses it. | FRESH (current source) |
| P5 | No production-issued tokens exist that would be broken by a wire-format change. | PROGRESS.md `magic-link-ui` section ("BLOCKS PRODUCTION /r/ HOSTING") + `web.app` is localhost-only. | FRESH 2026-05-26 |
| P6 | HMAC token primitive admits new payload fields with no crypto change. | `src/belegmeister/magic_link/token.py:107-109, 163-225` — canonical-sorted-keys JSON; schema change touches only `_encode_payload`/`_decode_payload`/`TokenPayload`. | FRESH (current source) |
| P7 | Identifier-driven selection is sufficient; downstream parsing/rendering needs no change beyond one new `log_reason`. | `src/belegmeister/web/request_view.py:154-237` — `_pick_newest_letter` is the sole consumer of the newest-heuristic; downstream (`_download_text`, `_parse_letter`) is identity-preserving. | FRESH (current source) |

## Out of scope (deliberate)

- **Replay policy** (single-use vs unlimited within `exp`) — deferred to submit-handler.
- **Backwards-compat with `{vgm_id, exp}` tokens** — none in production; cut cleanly.
- **POST `/r/{token}/submit` handler** — that's the submit-handler slice.
- **Letter cleanup / archival inside VGMs** (the 17-letter pile in 395357) — pre-existing debt, not introduced here.
- **SB UI redesign** — only the printed-URL token format changes (mechanical).
- **Resolver-perf** — closed by ADR-0005 (renumbered pre-slice from the conflicting ADR-0003).
- **Production deployment of `/r/`** — separate future slice (per PROGRESS.md).
- **Smoke cleanup automation** — out; UUID-prefixed filename + recorded `structure_item_id`s in smoke JSON serve as breadcrumbs for future cleanup once klardaten DELETE semantics are probed.
- **A4** (SB discovery of Mandant uploads via DATEV-UO) — that's a submit-handler Phase 0 premise, not this slice's concern.

## Decisions (with WHY)

- **D1: Token identifier = `structure_item.id` (str).** Chosen because (a) `UploadResult.document_id` already returns it (zero upload-module change), (b) the string handle is the durable contract surface inside DATEV's DMS.
  - Rejected: `document_file_id` (int) — collapses the read-side error taxonomy (see D2) and load-bears on klardaten's internal int numbering.
  - Rejected: both ids — redundant given D2(a) wins.

- **D2: Read-path strategy = list + find-by-id.** Chosen because **observability is design-load-bearing for operational health**: distinguishing `letter_id_not_in_binder` (low-frequency, high-information, actionable customer-support signal — "Mandant got a stale link") from `vgm_not_found` preserves on-call diagnostic value. Collapsing the taxonomy is irreversible — once merged, we cannot reverse-engineer which 404s were which class.
  - Rejected: direct-download (D2b) — saves 1 HTTP call (~200-500 ms RTT) but collapses three error paths into one ambiguous 404. Perf gain is not material in the interactive single-user context. **Status: REJECTED, not deferred.** Revisit is reactive-only — only if operational log-mining ever shows `letter_id_not_in_binder` never fires in practice over months of real use, suggesting the taxonomy distinction is operationally inert. No review is scheduled.

- **D3: Token payload schema = `{vgm_id: str, letter_id: str, exp: int}`.** Chosen because one field per concern: `vgm_id` for routing/logging, `letter_id` for selection, `exp` for expiry. Clean separation of concerns; minimal token bytes.
  - Rejected: `{letter_id, exp}` — forces D2(b) (already rejected).
  - Rejected: `{vgm_id, letter_id, document_file_id, exp}` — token ~20% fatter without payoff (read path uses only `vgm_id` + `letter_id`).

- **D4: CLI / SB-form printed-URL update IS in scope (fold-in from Phase 1).** The wire-format change must propagate through the mint pipeline. `generate_token` signature changes, so all callers update.

- **D5: New `log_reason="letter_id_not_in_binder"` added to `RequestLinkInvalid` canonical taxonomy (fold-in from Phase 1).** Distinct from `letter_missing` (empty VGM) and `vgm_not_found` (VGM 404). Without it, the error taxonomy is incomplete and D2's primary rationale (observability) does not pay off.

## Hardest seams (with test approach)

### Seam 1 — `_find_letter_by_id` predicate (read side)

Replaces `src/belegmeister/web/request_view.py:272-287` `_pick_newest_letter`.

- **Bug shape:** predicate selects wrong letter under multi-letter conditions (the very state observed today on VGM 395357 with 17 letters).
- **Naive-test failure mode:** fixture with ONE letter whose id matches the token. Predicate returns it; `return children[0]` also passes; "one letter = false confidence."
- **Wide test:** fixture with **≥3 letters** where the target satisfies NONE of these extreme positions across **all four** identifier candidates surfaced by `letter-discovery`:
  - NOT at index 0, NOT at index 1, NOT at last index — defeats `children[N]` for common N.
  - NOT lex-largest by `name`, NOT lex-smallest — defeats name-sorted picks either direction.
  - NOT newest by `creation_date`, NOT oldest.
  - NOT highest `document_file_id`, NOT lowest.
  - NOT highest `counter`, NOT lowest.
- **Anti-pattern named:** any naive heuristic keyed on the four candidate identifiers must fail this fixture. Resolver-perf precedent: "one return = it works" was the same trap.

### Seam 2 — Mint-side letter_id round-trip

Seam between `upload_to_binder` returning `UploadResult.document_id` and `generate_token(letter_id=…)` consuming it, inside `belegmeister.cli.create_request.run_create_request`.

- **Bug shape:** wrong identifier threaded (copy-paste of `vgm_guid`; stale variable from earlier iteration; wrong field from `UploadResult`).
- **Naive-test failure mode:** assertions on call-shape — `generate_token was called`, `a URL was printed`. Passes with the wrong arg. Exactly the resolver-loop failure class ("called list_documents with $skip — call shape right, arg semantics wrong").
- **Wide test:** mock `upload_to_binder` to return `UploadResult(document_id="STRUCT_ID_X")`, run `run_create_request`, take the printed URL's token, `verify_token` it, **assert `payload.letter_id == "STRUCT_ID_X"`**. Round-trip via `verify_token`, not assertions on call-shape.
- **Anti-pattern named:** "assertions on call-shape miss the wrong-arg class. Verify what survived the encode/decode cycle, not what entered the encoder."

### Seam 3 — Automated smoke cross-assertion

`scripts/smoke_token_instance_binding.py` — owner-runnable; output to `artifacts/spikes/`.

- **Flow:** create request in dev VGM → capture token T1 + letter L1's id + distinctive substring injected at mint time → create a SECOND request in the same VGM → capture token T2 + letter L2 + distinct distinctive substring → GET `/r/T1` → GET `/r/T2`.
- **Bug shape (the original):** `/r/T1` renders L2's content. Smoke that asserts only `200 OK + non-empty body` PASSES with the bug intact.
- **Wide test (the four cross-assertions):**
  - `L1_substring IN /r/T1 body`
  - `L2_substring IN /r/T2 body`
  - `L2_substring NOT IN /r/T1 body`
  - `L1_substring NOT IN /r/T2 body`
  The NOT-in cross-assertions are the real bug-detectors.
- **Pollution mitigation:** filename prefix `_smoke_letter_<UUID>.txt` (distinctive); smoke output JSON records `structure_item_id`s for future cleanup targeting. Distinctive substrings injected at mint time within the test rather than relying on existing fixtures (immune to state-leak across runs).
- **Output format:** `artifacts/spikes/token-instance-binding-smoke-<YYYY-MM-DD>.json` (load-bearing evidence — machine-parseable). Optional narrative alongside as `.md`.
- **Anti-pattern named:** "200 OK is a contentless assertion under the bug we're fixing."

### Seam 5 — log_reason equality distinguishing three error paths

The new `letter_id_not_in_binder` must NOT collapse into existing `letter_missing` or `vgm_not_found`. The slice's primary rationale (D2 observability) only pays off if the implementation distinguishes the three in practice.

- **Bug shape:** copy-paste from the adjacent empty-VGM branch yields `raise RequestLinkInvalid(log_reason="letter_missing")` when the real condition is `letter_id_not_in_binder`. Operationally: on-call sees the wrong route in dashboards.
- **Naive-test failure mode:** test asserts `with pytest.raises(RequestLinkInvalid)`. PASSES — same exception class.
- **Wide tests (three, named):**
  - `test_letter_id_not_in_binder_emits_distinct_log_reason` — populated VGM, target `letter_id` not among children → `exc.log_reason == "letter_id_not_in_binder"`.
  - `test_empty_binder_still_emits_letter_missing` — empty VGM (regression guard) → `exc.log_reason == "letter_missing"`.
  - `test_vgm_404_still_emits_vgm_not_found` — VGM GET returns 404 (regression guard) → `exc.log_reason == "vgm_not_found"`.
- **Anti-pattern named:** "`raises RequestLinkInvalid` is contentless under this slice; the `log_reason` field carries the operational distinction. Discipline established by existing `test_letter_malformed_logs_reason_and_returns_404`."

## Exit criterion

The slice is done when **all of these are simultaneously true**:

1. **Seam-1 test green:** `tests/web/test_request_view.py::test_find_letter_by_id_selects_target_in_multi_letter_binder` — fixture defeats all four naive heuristics per Seam 1 design.
2. **Seam-2 test green:** `tests/cli/test_create_request.py::test_mint_threads_upload_result_id_into_token_letter_id` — round-trip via `verify_token` assertion.
3. **Seam-5 tests green:** three distinct `log_reason` assertions (letter_id_not_in_binder / letter_missing regression / vgm_not_found regression).
4. **Token wire-format test green:** `tests/magic_link/test_token.py::test_old_vgm_only_token_rejects_as_malformed_under_new_schema` — explicit no-backwards-compat lockin; locks the Phase 1 decision into a test (catches the schema-loosening regression pattern of a `letter_id: str = ""` default sneaking in).
5. **Smoke evidence captured:** `artifacts/spikes/token-instance-binding-smoke-<YYYY-MM-DD>.json` shows two real requests in dev VGM, both tokens captured with their `letter_id`s, and all four cross-assertion results = true. Owner-run; exit code 0.
6. **Gate cleanliness:** `uv run pytest tests/ -q` green; `uv run mypy --strict src/ tests/ scripts/` clean; `uv run ruff check .` clean. No regression in existing test count.
7. **CLI external-surface sanity:** smoke output includes a one-shot decode of the printed token verifying it yields a 3-field payload `{vgm_id, letter_id, exp}` with non-empty `letter_id`.
8. **Disappearance-or-explain on `_pick_newest_letter`:** UNIT 2's PASS verdict explicitly names that the deleted function's existing tests are removed (or migrated), with the new Seam-1 wide test cited as the behavior-covering replacement. Same discipline magic-link-ui used for RT3 deletion (D-S3).

## Unit decomposition (3 units, fused after Phase 4 pushback)

| Unit | Scope | Files | Sentinel on completion |
|------|-------|-------|------------------------|
| **UNIT 1 — Token wire format + mint wiring (fused)** | TokenPayload gains `letter_id: str`; `generate_token` gains `letter_id` arg; `_encode_payload`/`_decode_payload` schema updated; old-format token rejected as MALFORMED; `run_create_request` threads `UploadResult.document_id`; Seam-2 round-trip test exercises both axes. | `src/belegmeister/magic_link/token.py`, `tests/magic_link/test_token.py`, `src/belegmeister/cli/create_request.py`, `tests/cli/test_create_request.py` | `=== UNIT 1 COMPLETE ===` |
| **UNIT 2 — Read-side wiring + error taxonomy** | `_pick_newest_letter` deleted (tests removed/migrated, recorded in PASS verdict); `_find_letter_by_id` added; new `log_reason="letter_id_not_in_binder"` added to `RequestLinkInvalid` taxonomy; Seam-1 wide test; Seam-5 three log_reason tests. | `src/belegmeister/web/request_view.py`, `tests/web/test_request_view.py` | `=== UNIT 2 COMPLETE ===` |
| **UNIT 3 — Automated smoke + slice closure** | `scripts/smoke_token_instance_binding.py` with cross-assertions and UUID-prefixed filenames; owner runs against dev VGM; output to `artifacts/spikes/token-instance-binding-smoke-<YYYY-MM-DD>.json` recording structure_item_ids + 4 cross-assertion booleans; PROGRESS.md closure entry; final gate check. | `scripts/smoke_token_instance_binding.py`, `PROGRESS.md`, `.overseer/ledger.md` | `OVERSEER_SLICE_AWAITING_OWNER: <closure message including smoke output path>` |

## Deferred to later slices

- **Token replay policy** — submit-handler. Why later: matters on POST mutations, not GET renders.
- **Token revocation list** — future incident-driven slice. Why later: stateless tokens are the load-bearing simplicity of the current design; revocation needs a persistence layer this slice does not justify. Gating: real incident or SB ops requirement.
- **`.md`-suffix legacy letters in VGM 395357** — operational hygiene. Why later: invisible to today's `.txt`-filtered read path; doesn't affect correctness. Gating: manual deletion request or convention change.
- **Smoke cleanup automation** — out; UUID prefix + recorded `structure_item_id`s in JSON as breadcrumbs. Why later: needs klardaten DELETE semantics probed first (unprobed today). Gating: DATEV admin asks "why are these `_smoke_letter_*` files here?" or a probe of DELETE semantics is run.
- **Production deployment of `/r/`** — separate slice (per PROGRESS.md `magic-link-ui` "Future open-item"). Why later: deployment-character (TLS, hosting, healthcheck, MAGIC_LINK_SECRET provisioning); not code-slice character.
- **A4 (SB-discovery DATEV-UO visual check)** — submit-handler Phase 0 prerequisite (template at `artifacts/spikes/submit-sb-discovery-2026-05-26.md`). Why later: A4 is a premise for submit-handler's notification semantics, not this slice's read path.

## Rejected (not deferred)

- **Direct-download read strategy (D2b).** Rejected for observability reasons; revisit is reactive-only (no calendar follow-through). Recorded here separately from Deferred to keep the deferred list honest about what could actually return.

## Open items requiring human decision

- **Pre-slice prep (BEFORE UNIT 1 starts): ADR renumber from 0003 to 0005.**
  Recommended owner-driven sequence (block-dangerous denies `git commit`, so owner runs commits):
  1. `git mv docs/adr/0003-klardaten-gateway-no-dollar-prefix.md docs/adr/0005-klardaten-gateway-no-dollar-prefix.md`
  2. `sed -i 's/ADR-0003/ADR-0005/g' docs/adr/0005-klardaten-gateway-no-dollar-prefix.md` — updates title line + self-references.
  3. Update ADR-0001's "Superseded-by" link if it references `0003-klardaten-gateway-no-dollar-prefix` → point to `0005-…`.
  4. `grep -rn "ADR-0003" -- ':!docs/adr/0003-uv-package-manager.md'` returns empty (only the legitimate uv-package-manager ADR keeps 0003).
  5. If the three prior commits that referenced "ADR-0003" are unpushed, optionally `--amend`/`rebase -i` to fix their messages; if pushed, leave alone.
  6. Commit as `chore(docs): renumber ADR-0003 (klardaten-gateway-no-dollar-prefix) to ADR-0005 — collided with existing ADR-0003 (uv-package-manager)`.
  After this lands, UNIT 3's PROGRESS.md closure can cite ADR-0005 cleanly.

- **A4 owner-driven DATEV-UO visual check** (not blocking this slice, but pending from prior conversation). Template at `artifacts/spikes/submit-sb-discovery-2026-05-26.md`; results feed submit-handler's Phase 0, not this slice's.
