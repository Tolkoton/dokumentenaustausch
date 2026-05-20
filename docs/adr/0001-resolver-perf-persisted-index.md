# ADR-0001 — Resolver performance: persisted SQLite number→GUID index, no synchronous scan

- **Status:** Accepted (2026-05-19)
- **Deciders:** Owner (product verdict + design lock), via spike + design escalation
- **Supersedes:** none
- **Related:** memory `slice-4b-blocked-resolver-perf`, `project-datev-dms-v2-schema`;
  spike `scripts/spike_direct_lookup_2026-05-19.py`
- **Authority:** This file is the source of truth for the resolver-perf
  implementation slice. The implementation reads THIS, not chat or memory.

## Context

Slice 4b (SB request-creation web form) is **code-complete but BLOCKED,
not shipped**. A not-found VGM resolve takes **~45 s and grows with DATEV
size** (owner product verdict 2026-05-19: not shippable). Root cause:
`resolve_binder_guid_by_number` (`src/belegmeister/datev/resolver.py`)
paginates every document page (`max_pages=50 × page_size=1000`, up to 50
sequential GETs); the 30 s `KlardatenClient.timeout` bounds ONE page, not
the total (~50–150 s realistic, ~25 min pathological). Lowering
`max_pages` would falsely report a real binder as "nicht gefunden" — a
correctness regression — so 4b cannot self-fix.

### Spike result (live, read-only, the gate — NOT TestClient)

`scripts/spike_direct_lookup_2026-05-19.py` swept, against live
`api.klardaten.com`, 6 query-param forms (`$filter=number eq X`,
`$filter=Number eq X`, `$filter=number eq 'X'`, `?number=X`,
`?document-number=X`, `?documentNumber=X`) and 2 path routes
(`/documents/by-number/{n}`, `/documents/number/{n}`).

Decisive discriminator: a **definitely-absent number**. A working filter
⇒ empty result; an ignored filter ⇒ full unfiltered page.

**Outcome: NO usable direct-lookup-by-number exists.** Every query form
is silently ignored — the absent-number query returns the full 1000-item
page identical to baseline. Both path routes 404. Additional finding:
**`$top` is also ignored** (asked 50, got 1000); only `$skip` paginates,
pages fixed at 1000. The O(n) `$skip` scan is the only server-side
primitive. This is **settled — do not re-probe** the filter question.

## Decision

Replace the on-resolve O(n) scan with a **persisted number→GUID index**.
The resolve path becomes index-only; the full scan is demoted to a
background refresh. **No synchronous scan exists anywhere; there is no
deadline-net.**

### Q1 — Index build / refresh strategy

- **Persisted SQLite** index, **stdlib `sqlite3`** (no new dependency),
  carrying a `built_at` timestamp.
- File location: a **user-data / config directory**, NOT the install
  directory (4c ships a read-only `.exe`).
- **Background refresh** (the synchronous `KlardatenClient` runs on a
  thread): a full `$skip` scan at startup **and** every **N** minutes.
  **N is configurable, biased long.**
- **Atomic full swap:** the refresh builds a brand-new index, then swaps
  the reference atomically. Concurrent resolves see the old index XOR the
  new one — **never a half-built index**.
- **Refresh failure** (DATEV down): log, keep the last-good index, retry
  on the next tick. Never crash.
- **GUID-for-a-number is stable** ⇒ an index entry is never *wrong*,
  only *missing* for a brand-new binder — exactly the miss case.

### Q2 — Miss message (extend B6, do NOT add a parallel path)

The index-miss raises the **existing** `VgmNotResolved` and flows through
the **existing** `_resolve_vgm_guid` → render block at
`src/belegmeister/sb/app.py:447`. Enrich the one f-string at
`app.py:455-458`; no second not-found code path.

```
VGM-Nummer {nummer} wurde in DATEV nicht gefunden
(zuletzt geprüft vor ~{X} Min). Falls die Vorgangsmappe
gerade erst angelegt wurde, in ~{N} Min erneut versuchen.
```

- `{X}` = minutes since the index's `built_at` (**relative**, a freshness
  *judgment*: small X → strong; X→N → weaker, covered by the retry line).
  `built_at` must reach the render site.
- `{N}` = configured refresh period.
- B6 unit test `test_B6_numeric_but_unknown_binder_rerenders_form_no_core`
  keeps the `"nicht gefunden"` substring; it gains assertions for the
  freshness stamp and the retry hint.

### Q3 — Cold start (first-ever launch only)

- The app **always starts** on B11 config-checks only. **Block-startup
  rejected** — it would tie boot to DATEV reachability, breaking the
  deliberate B11 (config → fail-fast) vs B12 (network → graceful
  degradation) split.
- First-ever build runs in the **background**; failure → retry on timer.
- Until the first index exists, resolve returns a **sibling of the miss
  branch** (NOT a synchronous scan — promise "no synchronous scan
  anywhere" stays intact):

```
VGM-Index wird erstmalig aufgebaut, in ein bis zwei Minuten
erneut versuchen.
```

  This distinct message is **required for honesty**: "nicht gefunden"
  before the index exists would be a lie. Avoid false-precise "~1 Min".
- First-launch splash UX is the 4c launcher's concern — out of scope here.

## Implementation slice briefing (read before Step 0)

This is a vertical slice crossing: the resolver module, a new SQLite
index store, a background refresh thread, the 4b render branch, and B6
tests. Step 0 of that slice MUST explicitly name:

1. **Atomic-swap concurrency** is the hardest seam to unit-test
   (build-new → atomic reference swap; concurrent resolves see old XOR
   new, never half-built). Step 0 must call this seam out by name and
   state how it is tested.
2. **Background refresh is a thread and must NEVER block the event loop.**
   Startup only *launches* the refresh — it does not await it.
3. **Exit criterion (how 4b finally closes):** implementation →
   re-run smoke step 8b → record the **real measured not-found
   duration** in PROGRESS.md → Step 6 PROGRESS reconciliation → 4b
   marked closed. Until then 4b stays BLOCKED. PROGRESS.md is **not**
   touched before that point.

## Consequences

- **Positive:** resolve is O(1) on a hit; misses are fast and honest with
  a freshness judgment; no synchronous scan or deadline anywhere; app
  boot is decoupled from DATEV reachability; restarts are instant (last
  index loaded from disk).
- **Negative / accepted:** a brand-new binder is unresolvable until the
  next refresh tick (≤ N min) — surfaced honestly by the Q2 message, not
  hidden. A new on-disk artifact and SQLite schema to maintain. Index
  staleness is a *missing-entry* risk only, never a *wrong-entry* risk
  (GUID-for-a-number is stable).
- **Permanent finding:** DATEV/klardaten has no server-side filter of any
  shape; the `$skip` scan is the only primitive. Do not re-litigate.
