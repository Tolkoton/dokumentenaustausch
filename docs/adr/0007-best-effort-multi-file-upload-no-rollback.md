# ADR-0007: Best-effort multi-file submit-upload semantics; no rollback (klardaten gateway has no DELETE proxy)

- **Status:** Accepted
- **Date:** 2026-05-27
- **Deciders:** Owner (sole developer)
- **References:**
  - `.claude/overseer/slice/submit-handler.md` (Phase 2 decisions D6, D8, D4, D5)
  - [ADR-0006](0006-binder-as-state-store-for-replay-policy.md) — the
    replay policy whose burn marker is the response doc this ADR
    governs.
  - `.claude/artifacts/spikes/klardaten-delete-semantics-2026-05-26.json` —
    empirical falsification of premise A9.
  - `.claude/artifacts/spikes/klardaten-size-envelope-2026-05-26.json` —
    empirical premise A5 (uploads succeed up to 200 MB).
  - `.claude/artifacts/spikes/submit-sb-discovery-2026-05-26.md` — empirical
    premise A4 (SB sees attachments via manual DATEV-UO inspection;
    no notification channel).

## Context

The submit-handler slice accepts a Mandant submission of N attached
files plus structured answers and freeform Anmerkungen, via
`POST /r/{token}/submit`. Phase 2's first draft picked an
**all-or-nothing** semantic: if any file's upload to klardaten failed,
the handler would issue DELETE on the N-1 already-succeeded
structure-items, leaving the binder in a clean pre-submit state. The
Mandant would see one "submission failed, please retry" page.

This semantic depended on a load-bearing assumption (premise A9):
*"Klardaten supports DELETE on `/document-files/{id}` and
`/documents/{vgm}/structure-items/{id}` cleanly enough to use as a
rollback primitive."*

A 10-minute spike script
(`scripts/probe_klardaten_delete_semantics_2026-05-26.py`,
2026-05-27) probed both endpoints against the dev gateway. **Result:
A9 falsified.** Every DELETE returned HTTP 404 with an empty body —
on real ids of just-uploaded files, on already-deleted ids, on
never-existed ids. The verified-absence check (`list_structure_items`
after DELETE) showed the uploaded file still present in the binder.
The gateway has no DELETE route on these endpoints at all.

Operational implication beyond this slice: **klardaten provides no
API-driven cleanup path of any kind.** All file removal is via the
DATEV-UO web interface, manually.

The all-or-nothing design has no implementable rollback primitive.
The slice must choose a different semantic.

## Decision

**Multi-file submit uploads use best-effort semantics. No rollback.**

The handler's contract:

1. **Sequential per-file upload, continue past failures.** For each
   file the Mandant attached, attempt `attach_file_to_binder`. Record
   per-file outcome (success or failure with reason) in an
   in-memory inventory. Do NOT abort the loop on a failure; continue
   to the next file. The realistic failure mode is per-file
   (klardaten rejects one file's format/size); aborting the loop
   would incorrectly deny the Mandant the legitimate successes of
   adjacent files.

2. **Bailout iff `files_attempted > 0 AND files_succeeded == 0`.**
   In this case, the handler raises
   `RequestSubmitFailed(log_reason="upload_failed_all_files")`. The
   response doc is NOT written; the token is NOT burned (no
   `_response_<letter_id>_*` marker exists; the next POST against
   the same token is welcomed). Mandant sees a generic error page;
   they can retry with the same magic link.

3. **Commit response doc on any other outcome.** Specifically the
   three other branches of the file-upload state space:
   - `files_attempted == 0`: Mandant submitted answers-only or
     answers-plus-Anmerkungen with no files. Response doc commits
     with empty `==ATTACHMENTS==` section. Token burns. Confirmation
     page renders `full_success` banner (no banner, just acknowledgment).
   - `files_attempted > 0 AND 0 < files_succeeded < files_attempted`:
     partial success. Response doc commits with
     `==ATTACHMENTS==` listing succeeded files and
     `==FAILED_ATTACHMENTS==` listing failed files with
     `failure_reason`. Token burns. Confirmation page renders
     `partial_success` banner.
   - `files_attempted > 0 AND files_succeeded == files_attempted`:
     full success. Response doc commits with clean `==ATTACHMENTS==`.
     Token burns. Confirmation page renders `full_success` banner.

4. **Order of operations: files first, then response doc.** The
   response doc references the successfully-uploaded files by their
   final stored filename (which embeds the per-file UUID generated
   by D3's naming scheme). Files-first means the response doc only
   commits when there is real content to summarize; if the response
   doc commit itself fails after files succeeded, the handler
   raises `RequestSubmitFailed(log_reason="upload_failed_response_doc")`.
   The succeeded files remain in the binder as orphans (per the
   no-DELETE constraint); the SB will see them on the next case
   review without the response-doc context, and can manually
   reconcile.

5. **Banner copy MUST NOT claim "SB has been notified".** Per A4
   verification, there is no notification channel. The banner for
   `partial_success` is:

   > *"Es wurden {n_succeeded} von {n_total} Dateien erfolgreich
   > hochgeladen. Bitte kontaktieren Sie Ihre Steuerberatung, um die
   > fehlenden Dateien nachzureichen."*
   >
   > English variant: *"{n_succeeded} of {n_total} files uploaded
   > successfully. Please contact your SB to retry the remaining files."*

   The response doc lands in the binder; SB sees it on the next
   review. That is the actual mechanism — periodic VGM inspection,
   not push notification. Claiming otherwise would mislead the
   Mandant about a mechanism that doesn't exist.

## Inventory schema (codec-load-bearing)

Each attempted file produces one inventory entry:

```python
@dataclass(frozen=True)
class AttachmentOutcome:
    original_filename: str
    stored_filename: str | None        # None if upload failed
    structure_item_id: str | None      # None if upload failed
    document_file_id: int | None       # None if upload failed
    status: Literal["succeeded", "failed"]
    failure_reason: str | None         # categorized: "klardaten_4xx", "klardaten_5xx", "network_timeout", "other"
    elapsed_s: float
```

The response doc serializer (D1) renders succeeded entries into the
`==ATTACHMENTS==` section (filenames Mandant + SB can read) and failed
entries into the `==FAILED_ATTACHMENTS==` section with
`original_filename` + `failure_reason` for SB diagnostic value.

## Consequences

### Positive

- **No dependency on a missing klardaten primitive.** The slice ships
  with the gateway as-is; no waiting on klardaten vendor work.
- **Mandant gets actionable diagnostics on partial failure.** Per-file
  inventory in the response doc tells the SB exactly which files
  failed and why; SB can re-issue a magic link asking specifically
  for the missing files.
- **State machine has four explicit branches, each testable in
  isolation.** Phase 3 RED tests follow the branch enumeration in
  the Decision section above; no implicit branches sneak in.

### Negative / accepted

- **Orphan files possible.** If the response doc upload fails after
  some files succeeded, those files remain in the binder with no
  audit-trail document referencing them. SB has to recognize them
  visually ("here are some attachments without a response doc;
  Mandant probably submitted but our system half-failed"). DATEV-UO
  manual cleanup is the only removal path.

- **Token may burn on partial-success.** A Mandant whose 5 files
  contained one bad file (e.g., wrong format) ends up with 4 files
  uploaded, 1 failed, response doc committed, token burned. They
  cannot self-serve retry; they must contact the SB for a new link.
  Acceptable because (a) SB intervention catches the underlying issue
  (e.g., "send the Beleg as PDF, not as a .heic photo"), (b) the
  alternative (commit-on-full-success-only with self-serve retry)
  causes runaway orphan accumulation when klardaten is even mildly
  flaky.

- **Typed answers are LOST on the bailout path.** If
  `files_attempted > 0 AND files_succeeded == 0`, the response doc
  is never written, so the Mandant's typed answers and Anmerkungen
  are not persisted server-side. On retry, the Mandant must re-type.
  Acceptable for MVP because (a) typical answer text is short
  (yes/no, brief explanation), (b) the alternative (committing
  response doc on full-failure) burns the token on a zero-value
  submission, requiring SB intervention for what is usually a
  retry-able transient error. Future enhancement (out of scope):
  client-side localStorage form persistence.

- **Concurrent submits can leak inventory.** Per ADR-0006's TOCTOU
  acknowledgment, two near-simultaneous POSTs from the same Mandant
  can both pass the replay check and both commit response docs. In
  the best-effort regime, this means two response docs in the binder
  with potentially-overlapping `==ATTACHMENTS==` inventories
  (depending on which file uploads interleaved when). Still no data
  corruption; still cosmetic clutter; still DATEV-UO cleanup.

- **The "klardaten is fully down" path takes N × per-file-timeout.**
  With N=5 and a 30 s per-file timeout, a fully-down klardaten
  scenario takes ~150 s before the bailout fires. Mandant waits
  staring at a spinner. Acceptable for the rare full-outage case
  per A5 (no outages observed across the 25/50/100/200 MB envelope);
  worth monitoring in production.

### Neutral

- **A9's spike script (`scripts/probe_klardaten_delete_semantics_2026-05-26.py`)
  is retained** as future-reference evidence; if klardaten ships
  DELETE support in a future API version, the same script becomes
  the re-verification probe.

## Alternatives considered (rejected)

- **(a) All-or-nothing with klardaten DELETE rollback.** The original
  D6 draft. Falsified by the A9 spike — klardaten has no DELETE
  proxy. Not implementable.

- **(b₁) Commit-on-full-success-only with self-serve retry.** Mandant
  retries with same files → each failed attempt adds new orphan
  structure-items to the VGM. If klardaten has any flakiness, the
  VGM accumulates duplicates rapidly. SB sees "5 copies of the same
  file" with no clear "latest" indicator. Worse hygiene than
  burn-on-any-success when no DELETE is available.

- **(b₂) Stop-on-first-failure (instead of continue-past-failures).**
  Per-file format rejection on file 3 of 5 causes files 4-5 to be
  silently skipped despite being legitimately uploadable. Mandant
  sees "stopped after file 3"; cannot tell whether 4-5 would have
  succeeded. Misclassifies per-file failure (the most common mode)
  as system failure.

- **(c) Always commit response doc, even on all-files-failed.** Single
  state machine path (no bailout), uniform SB audit. Rejected because
  it burns the token on the most-retry-able failure case (transient
  full-klardaten-outage), forcing SB intervention for an error
  Mandant could have self-resolved by waiting 60 s and retrying. The
  asymmetry between Mandant retry urgency (now) and SB response
  timing (whenever they next inspect the VGM; days possible per A4)
  makes this UX worse than the bailout path.

- **Scratch-binder staging.** Upload files to a dedicated scratch
  binder, "promote" to the target VGM only on full success. Pro:
  orphans live in scratch, not the customer VGM. Con: requires a
  klardaten primitive (binder→binder move or copy) that hasn't been
  probed and almost certainly doesn't exist in the gateway's
  surface; "promote via re-upload" doubles network cost and simply
  relocates the orphan problem to scratch (still no DELETE).
  Introduces scratch-binder lifecycle as a new infra surface. Does
  not change the verdict; flagged for completeness.

- **Single-file MVP (drop multi-file entirely).** Trivially satisfies
  all-or-nothing (N=1, can't have partial). Rejected because the
  Beleganforderung product fundamentally requires multi-file (front
  and back of receipt scans, multi-page documents, multiple receipts
  per inquiry). Single-file would ship a product-inadequate MVP.

## Why this is ADR-worthy

The slice's behaviour under partial-failure is a load-bearing product
decision — it changes the Mandant UX, the SB workflow, and the
operational consequences of klardaten outages. The decision rests on
a falsified premise (A9) that any future contributor might assume
otherwise about; this ADR is the durable record of why the obvious
"all-or-nothing" path was abandoned and what to do if the premise
ever changes. Without the ADR, the next slice author may attempt to
add a DELETE-based rollback path (assuming the gateway must support
it) and rediscover A9 the slow way.
