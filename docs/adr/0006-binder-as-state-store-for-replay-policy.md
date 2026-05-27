# ADR-0006: Binder contents as the state-store for magic-link token replay policy

- **Status:** Accepted
- **Date:** 2026-05-27
- **Deciders:** Owner (sole developer)
- **References:**
  - `.overseer/slice/submit-handler.md` (Phase 2 decision D2)
  - `.overseer/slice/token-instance-binding.md` (deferred replay policy to this slice)
  - [ADR-0002](0002-klardaten-gateway-for-datev.md) — klardaten as the
    sole DATEV integration surface; this ADR sits on top of that.

## Context

The submit-handler slice introduces `POST /r/{token}/submit`. Tokens are
HMAC-signed payloads `{vgm_id, letter_id, exp}` and carry no built-in
replay protection — by themselves they are valid for any number of
submissions within the `exp` window. The slice needs an explicit replay
policy. Three policy options were considered:

| Policy | State requirement | Recovery / observability |
|---|---|---|
| (a) **Single-use burn-on-success** | Per-token "submitted?" marker | Owner can re-enable a token by clearing the marker |
| (b) **Idempotency-key (token + content hash)** | Per-(token, content-hash) cache | Same token + same payload returns same result; same token + new payload depends on policy |
| (c) **Unlimited within `exp`** | None | Every POST commits; multiple `_response_*` docs accumulate |

For option (a), the location of the per-token marker is itself a
sub-decision:

| Marker location | Infra surface | Operability |
|---|---|---|
| In-process dict / set | None at code time, broken at runtime | Lost on every restart; multi-worker breaks; wrong for any non-toy deployment |
| Local SQLite file | New file path, schema, migration story, backup considerations | Recovery requires DB query / surgery |
| **In-binder (presence of `_response_<letter_id>_*.txt`)** | None | Recovery is "delete the response doc in DATEV-UO" — discoverable, owner-runnable, no extra tooling |

## Decision

**Replay policy is single-use burn-on-success, with the burn marker
stored as the presence of `_response_<letter_id>_*.txt` inside the
target VGM itself.**

Mechanics:

1. On `POST /r/{token}/submit`, after token verification, the handler
   calls `KlardatenClient.list_structure_items(vgm_guid)` and filters
   for any structure-item whose `name` starts with
   `_response_<letter_id>_`.
2. If any match: raise `RequestSubmitFailed(log_reason="replay_rejected")`.
   The exception handler in `web/app.py` renders the confirmation
   template with the `already_submitted` banner (see D5; this is NOT a
   user-visible error).
3. If no match: proceed with the file-upload + response-doc-commit
   flow. The response doc's eventual commit IS the burn marker for
   future POSTs against the same `{vgm_id, letter_id}` pair.

The token itself remains stateless (HMAC-only); no token-derived id is
stored anywhere outside the binder.

## Consequences

### Positive

- **Zero new infrastructure.** No SQLite, no Redis, no in-memory dict.
  State lives with the data it's about — the binder is the
  authoritative record of "did Mandant submit?".
- **Recovery is discoverable from DATEV-UO.** If the owner needs to
  re-enable a token (Mandant attached the wrong file; owner wants to
  let them re-submit), they delete the `_response_<letter_id>_*` from
  the VGM in DATEV-UO. No CLI, no DB surgery, no documentation lookup.
  Same UI the SB already uses to view the case.
- **Multi-process / multi-host safe** by virtue of klardaten being
  the only state authority. Two uvicorn workers, two hosts behind a
  load balancer, the policy still holds because both call the same
  klardaten endpoint to check.
- **Establishes a reusable pattern.** Future slices needing per-VGM
  durable state ("has this VGM been processed by job X?") can use the
  same approach — a sentinel-prefixed structure-item — without adding
  a new infrastructure dependency.

### Negative / accepted

- **TOCTOU window.** The `list_structure_items` check is not atomic
  against a subsequent `attach_file_to_binder` write from a separate
  request. Two near-simultaneous POSTs (~50ms apart) can both pass
  the check, both upload, and the binder ends up with two
  `_response_<letter_id>_*` files.

  **Mitigation:** defense-in-depth — the magic-link-ui form already
  ships a `lockSubmit` JS handler (per the slice-4b pattern) that
  disables the submit button on first click. That covers same-tab
  double-click (the realistic ~99% case). The in-binder check covers
  deliberate replay (curl, post-confirmation refresh, attacker
  resending a captured token). True cross-tab / cross-device
  concurrent submits from a single Mandant remain a vanishing-small
  residual risk. **Failure mode:** cosmetic clutter (two `_response_*`
  docs visible to SB); no data corruption; manual SB cleanup is one
  DATEV-UO action. Accepted.

- **Recovery has two prerequisites, not one.** Re-enabling a token
  requires BOTH the `_response_*` deletion AND the original token's
  `exp` not having passed. If `exp` has passed, recovery is "issue a
  new magic link via `create-request`", not "delete the marker".

- **Adds one `list_structure_items` GET per POST.** Latency cost is
  ~200-500 ms (per the existing GET-side flow's measured cost) on top
  of every submit. Acceptable in the interactive single-user context;
  not a hot-path concern.

- **Marker-file pollution is permanent.** Per [ADR-0007](0007-best-effort-multi-file-upload-no-rollback.md)
  (klardaten gateway has no DELETE proxy), the `_response_*` doc
  cannot be removed via API. The "owner deletes the doc" recovery
  path is therefore a DATEV-UO action exclusively. This is consistent
  with the rest of the system; flagged for clarity.

### Neutral

- **The check filename pattern is `_response_<letter_id>_*` (prefix
  match), not exact filename.** Two reasons: (a) `_response_<letter_id>_<ISO>.txt`
  carries an ISO timestamp the handler cannot predict pre-write; (b)
  multiple `_response_*` docs from a TOCTOU race still all match the
  prefix, so the check stays correct for the "did anyone already
  submit?" question.

## Alternatives considered (rejected)

- **(b) Idempotency-key (token + content-hash).** Requires server-side
  state anyway (cache of seen hashes). Hashing multipart bodies with
  `UploadFile` streams is non-trivial in FastAPI. Edge case "Mandant
  edits then resubmits" is ambiguous — different content hash = new
  attempt or same intent? YAGNI for the product's single-submit
  semantic.

- **(c) Unlimited within `exp`.** Mandant double-click → multiple
  response docs in VGM. SB has to manually disambiguate by timestamp.
  Worse product UX for the marginal savings of removing one GET per
  POST.

- **In-memory dict.** Lost on restart. Wrong for any non-toy
  deployment.

- **Local SQLite under `~/.local/share/belegmeister/`.** New infra
  surface (file path, schema, migration story, backup considerations)
  for one boolean per token. YAGNI when binder-presence works.

## Why this is ADR-worthy (not just slice-local)

The submit-handler slice is the FIRST consumer of the
"binder-as-state-store" pattern. Establishing it as an explicit
architectural choice — rather than an undocumented implementation
detail — lets future slices either follow the same pattern (reusing
the rationale here) or deviate with their own ADR justifying a
different state-store choice. Without this ADR, the pattern is
implicit and the next slice author may reinvent state-store
infrastructure unnecessarily.
