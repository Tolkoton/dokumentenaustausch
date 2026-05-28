# Spike — `_request_letter_*` structure-item discovery (informs Path A token-instance-binding)

- **Date:** 2026-05-26
- **Probe:** `scripts/probe_request_letter_structure_items_2026-05-26.py`
- **Endpoint:** `GET /datevconnect/dms/v2/documents/{binder_guid}/structure-items`
- **Target:** VGM 395357, binder `4c83e94e-24e7-4866-809c-5e983ad7f485`
- **HTTP status:** 200
- **Read-only.** No mutations.

## Empirical finding (load-bearing for Path A)

A single binder carries **17 `_request_letter_*` structure-items today**
(12 created today, the rest going back to 2026-05-15). Multi-request reuse
of the same VGM is the normal case, not an edge case.

Each structure-item in the binder's listing exposes these per-letter
identifiers — every one of which is stable per letter and distinct
across letters in this corpus:

| Field | Type | Example | Stability | Suitability for token binding |
|-------|------|---------|-----------|-------------------------------|
| `id` | str | `"1185519"` | Stable per structure-item; new letters get new ids | **Best candidate.** Highest grain, durable handle inside DATEV's DMS. |
| `document_file_id` | int | `1164586` | Stable per blob; documented elsewhere as single-shot at upload but read-stable | Strong candidate; one-fewer indirection than `id`. |
| `counter` | int | 2, 3, … 18 | Monotone within binder | Usable but binder-scoped (collides across binders unless paired with `vgm_id`). |
| `creation_date` | str | `"2026-05-26T07:46:57.680"` | ms precision | Brittle — two letters in same ms would collide; not a true id. |
| `name` | str | `"_request_letter_2026-05-26T074656Z.txt"` | s precision in filename | Same brittleness as `creation_date`; couples to our own naming. |

## Implications for the token-instance-binding slice

1. **Token payload becomes `{vgm_id, letter_id, exp}` or `{letter_id, exp}`.**
   `letter_id` is the structure-item `id` (string). The route's letter-resolver
   reads the specific structure-item, not "the newest one in the VGM."

2. **The current "newest letter wins" selection in `request_view.py` is the bug.**
   The slice must replace the selection rule with "exact match on token's
   `letter_id`."

3. **Token wire format change is necessary.** Old tokens (`{vgm_id, exp}` only)
   cannot be honored once the route requires a `letter_id`. Per PROGRESS.md:
   no production-issued tokens exist (no public host), so the new wire format
   can be cut cleanly. Owner ratifies in the prereq slice's Decisions.

4. **Backwards-compat option** (if any owner-issued tokens exist locally and
   matter): accept `{vgm_id, exp}` tokens by defaulting `letter_id` to "newest
   in binder" — i.e. preserve the present buggy behavior on legacy tokens.
   Owner should reject this; it would leave the smoke-discovered bug as a
   permanent legacy code path.

## Submit-slice impact (downstream of Path A)

- Once `letter_id` is on the token, the submit handler:
  - parses the binding letter's questions deterministically (same letter the
    Mandant saw), and
  - has a natural pairing key for `_response_*` artifacts: name them
    `_response_<letter_id>_<ISO>.txt` so SB can later read "did this specific
    request get answered?" by structure-item-id substring scan.

## What this spike does NOT settle

- **Whether SB notices new attachments without notification (A4).** Owner-driven
  DATEV-UO visual check — see `submit-sb-discovery-2026-05-26.md` template.
- **What the `_response_*` artifact format is** — submit-slice Phase 2 design.
- **Replay policy (A6)** — explicit accept / app-level idempotency / token
  burn-on-use. Submit-slice or prereq slice Phase 2 decision.

## Raw output

22 items in binder total, 17 matching `_request_letter_*`. Full per-item
record shapes captured in the probe's stdout (see transcript).
