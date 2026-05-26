# ADR-0005: Klardaten Gateway accepts OData params without `$` prefix

- **Status:** Accepted
- **Date:** 2026-05-26
- **Deciders:** Owner (sole developer), with Klardaten vendor confirmation
- **Supersedes:** [ADR-0001](0001-resolver-perf-persisted-index.md) — its
  persisted-index resolver design rested on the now-falsified premise that
  no server-side filter exists.
- **References:** [ADR-0002](0002-klardaten-gateway-for-datev.md) — the
  gateway-choice decision is unchanged; only the "Permanent finding"
  paragraph at lines 61-65 of ADR-0002 (which copy-pasted ADR-0001's
  conclusion) is contradicted by this ADR. Per project policy
  ("Never overwrite an existing ADR"), ADR-0002 stays as-written; this
  cross-reference is the durable correction.

## Context

Slice 4b/5b probes against `api.klardaten.com` (2026-05-19, 2026-05-21)
swept canonical OData syntax — `$filter=number eq X`, `$top=N`, `$skip=N`
— in multiple shapes (lowercase / uppercase / quoted; `?number=`,
`?document-number=`, `?documentNumber=`; path routes `/by-number/{n}`,
`/number/{n}`). Every form appeared silently ignored: the absent-number
filter returned a full 1000-row default page; `$top=50` also returned
1000 rows. The conclusion encoded in `resolver.py`, ADR-0001, and a
~150-line "Permanent finding" passage in ADR-0002 was:

> *"klardaten exposes no server-side filter; the only primitive is
>  `$skip` pagination."*

That conclusion drove the 1004-line `.overseer/slice/resolver-perf.md`
planning artifact and 16 staged-then-discarded implementation files for
a persisted SQLite number→GUID index with atomic-swap concurrency,
background refresh, and cold-start signaling.

**The conclusion was wrong.** The cause: the gateway accepts OData
semantics **without** the leading `$`. Every probe sent the `$`-prefixed
canonical form, which the gateway drops silently.

## Evidence

### Citation 1 — Klardaten n8n test suite

Klardaten's public n8n integration package asserts the exact wire format
in its contract tests:

> `nodes/Klardaten/n8n-nodes-datevconnect/tests/services/documentManagementClient.test.ts:28`
> — asserts the constructed URL contains `filter=number+eq+12345&top=10`
> (no `$` prefix on either parameter).

This is the vendor's own contract test against their own gateway; the
form sent in the assertion is the form the gateway implements.

### Citation 2 — Klardaten support email

Email from Johannes Kindermann (klardaten.com), 2026-05-26, verbatim:

> "für die Paginierung kannst du `?top=5&skip=10` nutzen [...]
>  Filter-Parameter [...]
>  `/datevconnect/dms/v2/documents?filter=number eq 395223`"

Direct vendor confirmation that `top`, `skip`, and `filter` are the
wire-format parameter names — no `$` prefix.

### Empirical verification

On 2026-05-26, against live `api.klardaten.com` with the configured
`x-client-instance-id` header:

```
GET /datevconnect/dms/v2/documents?filter=number+eq+395223
```

returned HTTP 200 with exactly one item:

- `number` = 395223
- `id` = `c168c052-...`
- `extension` = `"VGM"`
- `is_binder` = `true`

The same request issued with `$filter=number eq 395223` returned the
default 1000-row unfiltered page, confirming the `$`-prefixed form is
silently dropped by the gateway.

## Decision

**Klardaten Gateway uses OData semantics with the `$` prefix dropped.**
The wire-format query parameters on `/datevconnect/dms/v2/documents`
are:

- `filter` — OData filter expression (e.g., `number eq 395223`);
  enforced server-side.
- `top` — maximum rows to return; honored.
- `skip` — offset for pagination; honored.

`KlardatenClient.list_documents()` sends only these non-`$`-prefixed
params, and only the ones the caller supplies (omit = omit).
`resolve_binder_guid_by_number` becomes a single-call
`filter=number eq <doknum>` lookup.

## Consequences

- **Positive.** Resolver collapses from a worst-case 50-iteration page
  walk to a single HTTP call. The not-found path returns in one
  round-trip (~1 s) instead of ~45 s. No persisted index, no background
  refresh, no atomic-swap concurrency, no cold-start signal.
- **Positive.** All existing server-side primitives are now reachable —
  future endpoints needing filter-by-date, filter-by-class, or
  filter-by-correspondent inherit `filter` directly without a new
  acquisition strategy.
- **Negative / accepted.** The gateway's OData dialect deviates from
  canonical OData; future probes must check the no-`$` form before
  concluding "no filter exists." This finding lives in this ADR so the
  next probe author has a one-place lookup.
- **Implementation already landed.** The commit
  `fix(datev): rewrite resolve_binder_guid_by_number as single-call filter`
  (immediately preceding this ADR) ships the resolver rewrite, the
  client signature change, the test surface, and removes every
  `$`-prefix reference from production source. ADR-0005 is the doc-side
  record; the code is already on `master`.

## Why ADR-0001 is fully superseded

ADR-0001 designed a persisted-index resolver because the "no
server-side filter" premise made the synchronous `$skip` scan the only
primitive. That premise is false. With server-side `filter` available,
the persisted-index design — background refresh, atomic-swap
concurrency, SQLite schema, cold-start signal, freshness stamp,
deadline-net considerations — has no remaining justification. The
1004-line `.overseer/slice/resolver-perf.md` planning artifact is
removed in the immediately-following commit. ADR-0001 itself stays in
the repository as historical record (per project policy never to
overwrite an ADR) but should not inform new design work.

## Why ADR-0002 is referenced, not superseded

ADR-0002's load-bearing decision — "use klardaten as the sole DATEV
integration surface" — is unaffected. The gateway works; we still use
it; nothing about the integration-surface choice changed. The only
contradicted text in ADR-0002 is the "Permanent finding (carried by
ADR-0001)" paragraph at lines 61-65, which inherited ADR-0001's wrong
conclusion verbatim. That paragraph should be read with this ADR as
the durable correction.

## Lessons (not formally part of the decision, but worth recording)

- **A probe that tests one syntactic shape and concludes "feature
  absent" has probed only THAT shape.** The 4b/5b probes never tested
  the non-`$`-prefixed form because canonical OData uses `$`; the
  assumption was unstated and unprobed.
- **Vendor test suites are first-class evidence** when the vendor's
  documentation is a JS-SPA unreachable to `WebFetch`. The n8n package
  was public; consulting it would have surfaced the right wire format
  weeks earlier.
- **Resolver-perf's slice (1004 lines of planning + 16 implementation
  files) was correctly built on its premise.** The premise was the
  failure point, not the architecture work. This is the exact failure
  mode that the new Phase 0 "premise probe" in `/plan-slice` is
  designed to catch — and the precedent the probe cites.
