# Slice resolver-perf — planning artifact

> Status: PLANNING_COMPLETE — slice contract for the resolver-perf
> implementation slice. The implementation reads THIS, not chat or memory.
> This artifact overrides generic overseer patterns for THIS slice.
> Supersedes / coexists with ADR-0001 — where they overlap, ADR-0001 is
> authoritative on architecture (Q1/Q2/Q3 directions); THIS artifact is
> authoritative on test design, exit chain, deferrals, and the
> measurement contract.

## Goal

Slice 4b moves from `BLOCKED` → `CLOSED` in `PROGRESS.md`, gated on:

- **(a) Cold-start path** — SB form render returns the sibling-of-miss
  message (`"VGM-Index wird erstmalig aufgebaut"`) in ≤ 1 second
  end-to-end (POST `/sb/create` → HTML response), measured by smoke step
  8b wall-clock. The background refresh is unbounded (minutes), measured
  separately via log line `"vgm index refresh complete (...)"`.
- **(b) Steady-state path** — SB form render returns
  `"nicht gefunden (zuletzt geprüft vor ~N Min)"` in ≤ 1 second
  end-to-end **AND** internal resolver call
  `resolve_binder_guid_by_number_via_index()` returns in ≤ 50 ms,
  measured via `time.perf_counter()` around the resolver call and
  logged. Both thresholds must pass independently — the ≤ 50 ms guards
  against render-time masking resolver slowness; the ≤ 1 s guards
  against pathological end-to-end blockers.
- **(c) Measurement discipline** — smoke step 8b is run **3 times
  consecutively** per path (cold-start, steady-state). All 3
  observations recorded in `PROGRESS.md`. `max(3)` must satisfy the
  threshold. Rationale: single observation on local machine is
  coin-flip territory (OS cache, Python GC pause, TCP retransmit can
  shift 0.9 s → 1.4 s); 3 runs cheap, `max` removes the "lucky low"
  failure mode. Not statistics — sanity check against luck.
- **(d) PROGRESS.md transition** — both wall-clock numbers +
  log-extracted build duration recorded in `PROGRESS.md`, replacing the
  `<TBD — mandatory before close>` placeholder at `PROGRESS.md:470-471`.

If smoke shows multi-second latency on either path → slice is `BLOCKED`
on a fresh design cycle, **NOT** shipped with caveats. `PROGRESS.md`
stays untouched per ADR-0001's exit-criterion chain.

## Out of scope (deliberate)

1. **Refresh-metrics surface** (Prometheus / health endpoint /
   structured metrics emission on tick success/failure). Warn-log is
   the only observability surface for V1. See [D-i].
2. **Manual "rebuild index now" admin button / CLI command.**
   Background refresh tick is the only rebuild trigger. See [D-ii].
3. **Index schema migration / versioning** for a future v2 of the
   index. Considered-and-dropped, no trigger. See [X-i].
4. **4c launcher first-launch splash / progress UI** ("index building,
   please wait" with progress bar). Q3 sibling-of-miss message in SB
   form is the only UX surface for "not ready yet" in V1. See [D-iii].
5. **Cross-process / multi-instance index coordination.** Single SB
   process per machine assumed. Concurrent processes not in threat
   model. See [X-ii].
6. **Index size / disk-pressure handling.** DATEV at SB scale is ≤ low
   hundreds of thousands of docs; sqlite handles that trivially.
   Considered-and-dropped. See [X-iii].

Full inventory of deferred + considered-and-dropped items: §Deferred
to later slices + §Considered-and-dropped.

## Decisions (with WHY)

Decisions in this section override generic patterns for THIS slice. If
a decision conflicts with ADR-0001, ADR-0001 wins — flag the conflict
and escalate (`SCOPE_AMENDMENT`), do not unilaterally amend.

### Q1 — Storage path within user-data dir

- **Chose:** `%APPDATA%/Belegmeister/vgm_index.sqlite` (Windows);
  `$XDG_DATA_HOME/Belegmeister/vgm_index.sqlite` with fallback
  `~/.local/share/Belegmeister/vgm_index.sqlite` (Linux).
- **Why:** separates state from install dir; survives reinstall;
  follows OS conventions. `mkdir(parents=True, exist_ok=True)` before
  any sqlite call.
- **Rejected:** project-relative path — because polluted by source
  tree, lost on git operations, doesn't match deployed install layout.
- **Rejected:** tempfile / `/dev/shm` — because ADR-0001 requires
  persistence across SB restarts (one of its load-bearing properties).
- **Scope:** macOS NOT in scope — project is Windows + Linux only
  (developer machine Linux, deployed Windows).

### Q2 — SQLite schema and `built_at` storage format

- **Chose:**
  ```sql
  CREATE TABLE vgm_index (
      dokumentnummer INTEGER PRIMARY KEY,
      guid           TEXT NOT NULL
  );
  CREATE TABLE meta (
      key   TEXT PRIMARY KEY,
      value TEXT NOT NULL
  );
  ```
  `meta` values are **ISO-8601 UTC strings** for timestamps (e.g.
  `"2026-05-21T14:23:01.012345+00:00"`); decimal integer strings for
  counts. Specifically: `meta(key="built_at")` stores
  `datetime.now(tz=timezone.utc).isoformat()`; reader parses via
  `datetime.fromisoformat(value)`; arithmetic against `now` done in
  UTC: `(datetime.now(tz=timezone.utc) - built_at).total_seconds() / 60`.
- **Why:** `INTEGER PRIMARY KEY` is the rowid alias in SQLite — fastest
  possible lookup, no separate B-tree; `meta` table holds lifecycle
  data updated once per refresh (not per row); ISO-8601 UTC keeps the
  build-host vs render-host TZ contract aligned.
- **Rejected:** `dokumentnummer TEXT PRIMARY KEY` — because DATEV API
  returns int; two conversions add bug-surface; INTEGER PRIMARY KEY is
  faster.
- **Rejected:** `last_seen_at REAL NOT NULL` per row — because
  atomic-full-swap sets every row to the same `built_at`; dead column
  for premature incremental-refresh scaffolding that contradicts ADR Q1.
- **Rejected:** `meta.value` as `REAL` with unix-timestamp-float —
  because faster parse, but loses human-readable inspection via sqlite
  CLI; SB scale doesn't need parse-speed.
- **Rejected:** `meta.value` as TEXT without format spec — because
  every reader site implements parse independently; TZ-handling
  inconsistencies surface in production months later.
- **Rejected:** naive-local datetime — because build host may differ
  from render host (dev Linux vs deploy Windows); naive-local
  introduces silent TZ offsets that pass tests but fail in mixed
  environment.

### Q3 — Atomic swap mechanism

- **Chose:** `os.replace` (FS-atomic file move) **+** `threading.Lock`
  (Python-level reader-writer serialization). Build new SQLite database
  to `vgm_index.sqlite.new` in same directory using **rollback-journal
  mode** (Q-journal). Explicitly `conn.close()` the build connection
  **before** swap. Then:

  ```
  refresh thread:
    1. build .new (no lock) — minutes long
    2. close build connection (no lock)
    3. acquire IndexStore.lock
    4. os.replace(".new", current)
    5. release lock

  resolver thread:
    1. acquire IndexStore.lock
    2. open transient sqlite3 connection on current path
    3. query (SELECT guid FROM vgm_index WHERE dokumentnummer = ?)
    4. close connection
    5. release lock
  ```

  The lock serializes both resolver-read and refresh-swap; at SB QPS
  (≪ 1) contention is invisible in practice. `os.replace` provides the
  filesystem-level atomic move; the lock prevents Windows
  `MoveFileEx` racing with reader-held handles.
- **Why:** addresses all three failure modes from PB1 of planning:
  SQLite `-journal` sidecar naming inconsistency post-swap (mitigated
  by close-before-swap + rollback-journal); Windows `MoveFileEx` fails
  with `PermissionError` when reader holds non-`FILE_SHARE_DELETE`
  handle (mitigated by lock); orphan `.new` on mid-build crash
  (mitigated by Q-cleanup).
- **Rejected:** `os.replace` alone — because of the three failure
  modes above.
- **Rejected:** WAL-mode + `os.replace` — because `-wal` and `-shm`
  sidecars need separate handling at swap time; rollback-journal with
  explicit `conn.close()` before swap is the cleaner contract.
- **Rejected:** in-place DELETE + INSERT in transaction — because
  consumer can see partial state during long build; violates ADR's
  "never half-built" guarantee.

### Q4 — Connection lifecycle in resolver path

- **Chose:**
  ```python
  with contextlib.closing(sqlite3.connect(current_path, timeout=1.0)) as conn:
      row = conn.execute(
          "SELECT guid FROM vgm_index WHERE dokumentnummer = ?", (number,)
      ).fetchone()
  ```
- **Why:** `contextlib.closing` guarantees `conn.close()` in `finally`.
  `sqlite3.Connection`'s native `with` only manages transactions, not
  lifecycle — that is a real Python footgun, particularly hazardous on
  Windows due to `MoveFileEx` semantics from Q3.
- **Rejected:** `with sqlite3.connect(...) as conn:` alone — because
  file descriptor leaks until GC.
- **Rejected:** long-lived single connection — because complicates
  atomic swap (needs re-open after `os.replace`); thread-safety footgun
  across FastAPI handlers.
- **Rejected:** connection pool — because no measurable benefit at SB
  scale (point-lookups, low QPS); pool itself is a thread-safety
  footgun.

### Q5 — Refresh thread lifecycle

- **Chose:** lifespan-aware startup using
  `@asynccontextmanager lifespan` (**not** deprecated
  `@app.on_event("startup")`). Daemon thread started in lifespan
  startup phase; shutdown signal via `threading.Event`; thread polls
  `event.wait(timeout=N*60)` — **no 1-second inner poll**,
  `Event.wait` is already interruptible. Lifespan shutdown calls
  `event.set()` then `thread.join(timeout=5.0)`. Mid-build interrupt:
  thread checks `event.is_set()` between major build steps (after
  DATEV API call complete, before `conn.close()`); if set, abandons
  `.new` build — orphan cleaned at next startup per Q-cleanup.
- **Why:** lifespan is the current standard; daemon dies with process
  on crash, no zombie threads; Event interrupt is built-in; 5 s join
  is best-effort.
- **Caveat (documented, not oversight):** if shutdown catches the
  thread mid-DATEV-fetch (`KlardatenClient.timeout = 30 s` per page),
  `join(5)` returns `False` and `daemon=True` kills the thread
  mid-HTTP-read. Acceptable failure mode: mid-build `.new` file is
  incomplete on disk, orphan-cleanup at next startup (Q-cleanup)
  catches it.
- **Rejected:** `@app.on_event("startup")` — deprecated since FastAPI
  0.93.
- **Rejected:** 1-second inner poll — `event.wait(timeout)` already
  interrupt-aware; inner poll burns CPU for no benefit.
- **Rejected:** hard daemon-kill on exit without join — because
  graceful join + orphan cleanup is the cleaner contract.

### Q-error — Refresh-thread failure handling

- **Chose:** outer `except Exception` with sub-classification by
  severity:

  ```python
  while not shutdown.is_set():
      try:
          build_index_and_swap()
      except httpx.HTTPError as exc:
          log.warning(
              "vgm index refresh: transient DATEV failure: %s; "
              "keeping last-good, retry in %d min", exc, N,
          )
      except (sqlite3.OperationalError, OSError) as exc:
          log.error(
              "vgm index refresh: storage failure (%s): %s; "
              "keeping last-good, retry in %d min",
              type(exc).__name__, exc, N,
          )
      except Exception as exc:
          log.error(
              "vgm index refresh: UNEXPECTED failure (%s): %s; "
              "keeping last-good, retry in %d min — investigate",
              type(exc).__name__, exc, N,
          )
      shutdown.wait(N*60)
  ```
- **Why:** thread NEVER exits via exception escape. Severity
  distinguishes "ignore for now" (httpx) from "must investigate"
  (storage / unexpected) so ops can triage.
- **Rejected:** catch `httpx.HTTPError` only — because
  `sqlite3.OperationalError` (disk full), `OSError` (permission
  denied), generic `Exception` (DATEV response shape regression)
  escape the loop, thread silently dies, `IndexStore.current_path`
  stays last-good FOREVER with no log signal.
- **Rejected:** catch `Exception` uniformly at warning level — because
  masks "unexpected" failures under same severity as "transient DATEV
  hiccup"; ops can't distinguish.
- **Rejected:** re-raise on non-httpx — because thread death is exactly
  the silent failure mode being prevented.

### Q-threshold — Resolver internal timing instrumentation

- **Chose:** `time.perf_counter()` captured at
  `resolve_binder_guid_by_number_via_index()` entry/exit;
  `log.info("vgm resolver: number=%s ms=%.1f hit=%s", number, ms, hit)`
  at **INFO** level. Smoke greps for the `"vgm resolver:"` line and
  extracts the `ms` field via the Seam 4 anchored regex.
- **Why:** INFO so the line is visible at default uvicorn log level
  (DEBUG would silently miss without `--log-level debug`); log-extraction
  matches the existing smoke-test pattern; no metrics infrastructure
  added.
- **Rejected:** return tuple `(guid, duration_ms)` — pollutes resolver
  signature for measurement-only need; callers don't care about
  duration.
- **Rejected:** structured metrics emission — no consumer exists yet
  (see D-i, D-iv).

### Q-build-log — Refresh completion log format

- **Chose:**
  `log.info("vgm index refresh complete: %d entries, %d ms, source=DATEV-DMS-v2", n_entries, ms_total)`
  at INFO level.
- **Why:** INFO so visible at default; greppable keyword
  `"vgm index refresh complete"`; entry count + duration surface
  retrospective tuning data.
- **Rejected:** separate start/end log lines — greppability suffers;
  one definitive completion line sufficient.
- **Rejected:** emit only on first build — would lose visibility into
  ongoing refresh health; tick-by-tick line is cheap.

### Q-journal — SQLite journal mode for index DB

- **Chose:** rollback-journal (SQLite default) explicitly; `conn.close()`
  called **before** `os.replace` in refresh thread.
- **Why:** rollback-journal lives in single sidecar `<name>-journal`
  cleaned up by SQLite on commit/close; if no transaction open at
  swap time, no sidecar exists; single-syscall swap stays clean.
- **Rejected:** WAL mode — creates `-wal` and `-shm` sidecars that
  complicate atomic swap.
- **Rejected:** rollback-journal without explicit close-before-swap —
  residual `-journal` sidecar could exist if swap races with build
  transaction.

### Q-sentinel — Cold-start "index not ready" signal type

- **Chose:** **(а1) + (б2) full migration.** Migrate `VgmNotResolved`
  from `src/belegmeister/sb/app.py` to a new file
  `src/belegmeister/datev/exceptions.py`. Add
  `VgmIndexNotReady(VgmNotResolved)` in the same file.
  `resolve_binder_guid_by_number_via_index()` now raises both:
  `VgmNotResolved` on miss against a built index;
  `VgmIndexNotReady` when `IndexStore.current_path` is `None` (no
  index file yet). `sb/app.py` imports both from `datev.exceptions`;
  the line 344 site refactors from `raise VgmNotResolved(...)`
  (sb-layer raises) to:

  ```python
  try:
      guid = resolve_binder_guid_by_number_via_index(number)
  except VgmIndexNotReady:
      <sibling-of-miss render>
  except VgmNotResolved:
      <existing miss render>
  ```

  Order matters: `VgmIndexNotReady` is a subclass of `VgmNotResolved`,
  so its `except` clause MUST come first.
- **Why:** (а1) places exception classes in the layer they semantically
  belong to (datev/); (б2) makes the resolver function the single
  source of failure-mode classification; subclass relation lets the
  render block distinguish via `isinstance` while keeping any non-cold-
  start catch sites (if any are added later) functional at the
  `VgmNotResolved` level.
- **Rejected:** (а1) + (б1) — half-migration; `VgmNotResolved` would
  sit in datev/ but the resolver still returns `None` on miss; future
  readers see the exception class but the call signature contradicts.
- **Rejected:** (а2) + (б1) — cold-start logic scattered:
  `IndexStore.is_ready()` in datev/, the check + raise in sb/app.py;
  ownership of the cold-start contract unclear.
- **Forbidden:** (а2) + (б2) — would require datev/resolver.py to
  raise sb/VgmNotResolved, importing from upper layer; layer inversion.

### Q-cleanup — Orphan `.new` cleanup on startup

- **Chose:** at lifespan startup, **before** the background thread
  starts: if `vgm_index.sqlite.new` exists OR
  `vgm_index.sqlite.new-journal` exists, `os.unlink` both with
  `log.info("removed orphan partial-index file: %s", path)`.
- **Why:** mid-build crashes from a previous run leave `.new` debris;
  explicit cleanup makes startup state deterministic.
- **Rejected:** leave alone, let refresh thread overwrite — because
  `os.replace` handles the overwrite but stale `-new-journal` could
  mislead diagnostics if startup crashes happen frequently.

### Q-test-seam — SQLite IndexStore test strategy

- **Chose:** two-tier.
  - **Unit tests** for resolver lookup logic use
    `sqlite3.connect(":memory:")` with hand-populated rows (fast,
    isolated).
  - **Integration tests** for atomic-swap and crash-recovery use
    `tmp_path` with a **real file** (`os.replace` is meaningless on
    `:memory:`; orphan-cleanup needs real filesystem).
  - **Build-thread tests** use real file with monkeypatched DATEV
    client (avoid network).
- **Why:** keeps fast tests fast; gives realistic-file tests the
  surfaces they need.
- **Rejected:** only `:memory:` — atomic-swap, journal-file behavior,
  orphan-cleanup all require real filesystem.
- **Rejected:** only `tmp_path` real file — unit tests for pure lookup
  logic become slower for no benefit.

### Q-render — Miss-message arithmetic + display contract

(Documented here because it spans IndexStore → render → template;
implementation-detail, but load-bearing per Seam 2b.)

- **Storage:** `meta.value` for `built_at` = ISO-8601 UTC string
  (Q2).
- **Read:** `datetime.fromisoformat(value)`.
- **Arithmetic:**
  `(datetime.now(tz=timezone.utc) - built_at).total_seconds() / 60`
  → float minutes.
- **Display:** `int(max(0, float_minutes))` rendered as
  `"vor ~{N} Min"` — **clamp at 0** (NTP-correction negative case
  becomes `"vor ~0 Min"`, NOT `"vor ~-N Min"`), always `Min` unit, no
  `Std`/`Tag` thresholds in V1 (see D-v).

## Hardest seams (with test approach)

### Seam 1 — atomic-swap concurrency (ADR-locked baseline)

- **Anti-pattern named:** "serial concurrency illusion" — test does
  `swap()` then `read()` sequentially, asserts success. Passes even if
  `IndexStore.lock` is missing or `os.replace` contends with reader-
  held file handles. Single-threaded execution never exercises the race
  window.
- **Test approach:**
  - `threading.Barrier(N+2)` synchronizes start of N=6 reader threads
    + 1 writer thread + main thread.
  - **Writer thread:** M=100 iterations, build `.new` file with
    deterministic content (numbers `1..K` mapped to known GUIDs), then
    `IndexStore.swap()` (acquires lock, `os.replace`, releases).
  - **Reader threads:** until writer signals done, call
    `resolve_binder_guid_by_number_via_index(N)` where `N ∈ 1..K`.
    Acceptance: **`result == expected_GUID[N]` only** — NEVER
    `VgmNotResolved` (would indicate reader saw empty or partially-
    built file — exactly the race the test exists to catch), NEVER
    `PermissionError` on Windows, NEVER `None` from broken connection,
    NEVER partial/corrupt data. Rationale: both builds use IDENTICAL
    population (1..K mapped to same GUIDs); any miss means an
    intermediate state was observed — that IS the bug.
  - After loops complete: assert zero exceptions in any thread via
    `concurrent.futures.as_completed`; zero `"PermissionError"`
    substring matches in `caplog`.
  - **Linux:** pytest in-process sufficient.
  - **Windows:** MUST run as a separate Python subprocess via
    `subprocess.run(["python", "-m", "pytest",
    "tests/integration/test_atomic_swap.py::test_concurrent"])` —
    pytest's runner holds file descriptors with different
    `FILE_SHARE` flags than the production uvicorn process, which can
    mask `MoveFileEx` semantics.
- **Primitives:** `threading.Barrier`,
  `concurrent.futures.ThreadPoolExecutor`, real `tmp_path` (NOT
  `:memory:`), explicit subprocess invocation on
  `sys.platform == "win32"`.

### Seam 2 — cold-start vs miss routing AND `built_at` arithmetic

#### Seam 2a — cold-start vs miss branch routing

- **Anti-pattern named:** "single-substring assertion gap" — cold-start
  test asserts response contains `"wird erstmalig aufgebaut"` and
  stops; miss test asserts `"nicht gefunden"` and stops. If the
  resolver regresses (raises `VgmNotResolved` instead of
  `VgmIndexNotReady` on cold-start, OR sb/app.py `except`-clauses end
  up in wrong order so `VgmNotResolved` catches first via subclass),
  one path silently falls through to the other branch's render.
- **Test approach:**
  - **Test A (cold-start path):** `tmp_path` with NO `.sqlite` file.
    FastAPI `TestClient` POST `/sb/create` with VGM-required body.
    Assert response.text contains `"wird erstmalig aufgebaut"` AND
    `"nicht gefunden"` is NOT in response.text AND status 200.
  - **Test B (miss path):** `tmp_path` with prepopulated `.sqlite`
    containing `dokumentnummer 1001`. POST with UNKNOWN dokumentnummer
    `9999`. Assert `"nicht gefunden"` in response.text AND
    `"wird erstmalig"` NOT in response.text AND status 200.
  - **Test C (resolver unit, source check):**
    `with pytest.raises(VgmIndexNotReady) as exc_info:` —
    `IndexStore(path=tmp_path/"nonexistent.sqlite")`,
    `resolve_binder_guid_by_number_via_index(1001)`. Assert
    `type(exc_info.value) is VgmIndexNotReady` — NOT `isinstance()`
    (which would allow `VgmNotResolved` subclass to pass too — the
    exact regression we are testing against).
- The asymmetric BOTH-presence-AND-absence assertion catches
  fall-through; exact-type-identity check catches mis-classification
  at the source.

#### Seam 2b — `built_at` arithmetic correctness in miss-path render

- **Anti-pattern named:** "substring-only freshness assertion" — test
  asserts `"vor ~" in response.text` and stops. Passes for any
  arithmetic regression: TZ-offset shifts `{X}` by 60-120 min, NTP
  correction makes `{X}` negative, float precision causes off-by-one,
  very-stale renders awkwardly. Substring match catches none of these.
- **Test approach (2 sub-tests, high-signal cases):**
  - **Test 2b-α (positive sane arithmetic):** seed
    `meta(built_at) = (now_utc - 5min).isoformat()`. POST miss
    request. Assert `response.text` matches `r"vor ~5 Min"` via
    `re.search` with anchored format (NOT bare substring). Catches:
    TZ-misparse (would yield `~65` or `~-55`), rounding regression.
  - **Test 2b-β (clock-skew negative clamp):** seed
    `built_at = (now_utc + 10min).isoformat()` — simulates NTP-
    correction. POST miss. Assert `response.text` does NOT match
    `r"vor ~-\d+ Min"` anywhere AND matches `r"vor ~0 Min"` exactly
    (the clamp-to-zero contract per Q-render).
- **Dropped:** just-built case (subsumed by 2b-α's rounding assertion
  at boundary value if N rounds to 0; no extra signal — see X-iv).
- **Dropped:** very-stale unit-switch test (premature precision; V1 UX
  contract is "always Min unit" — see D-v).

### Seam 3 — refresh-thread mid-build interruption + orphan cleanup

- **Anti-pattern named:** "instant-mock build illusion" — test mocks
  `KlardatenClient` to return all pages instantly. Lifespan startup →
  thread builds `.new` in <1ms → swaps → idles → shutdown clean.
  Orphan-cleanup code path NEVER fires; broken cleanup logic ships
  undetected. Real DATEV is slow (up to 30 s timeout per page),
  shutdown lands mid-fetch, `.new` orphan must exist on disk, next
  startup must clean.
- **Test approach (two threading.Events for clear semantics):**
  - `entered_slow_yield = threading.Event()` — **set by the
    monkeypatched generator** when it enters the slow-yield path; test
    `event.wait()`s on this before triggering shutdown.
  - `release_yield = threading.Event()` (optional, for Phase C
    graceful-unblock) — set by the test for graceful unblock when
    needed; Phase A leaves it unset and lets daemon-kill be the
    unblock.
  - `monkeypatch` `KlardatenClient.list_pages` to yield first page
    deterministically, then `entered_slow_yield.set()`, then block
    until `release_yield.wait()` (or indefinitely, with no timeout, in
    Phase A).
  - **Phase A — mid-build interrupt:**
    - `with TestClient(app) as client:` — monkeypatch active; wait
      until `entered_slow_yield.is_set()`; exit context manager.
    - Lifespan shutdown calls `thread.join(timeout=5)`; slow-yield
      exceeds timeout; daemon kill terminates mid-fetch.
    - Assert `os.path.exists(tmp_path / "vgm_index.sqlite.new")` is
      True.
  - **Phase B — clean restart:**
    - Fresh `TestClient(app)` context, monkeypatch removed (DATEV
      calls succeed normally).
    - Assert `caplog.records` contains a record where
      `"removed orphan partial-index file"` in `record.message` AND
      `".new"` in `record.message`.
    - Assert `os.path.exists(tmp_path / "vgm_index.sqlite.new")`
      is False.
    - Assert `os.path.exists(tmp_path / "vgm_index.sqlite.new-journal")`
      is False.
  - **Phase C — confirm rebuild succeeds:** wait for refresh thread to
    complete one full build cycle (poll `IndexStore.is_ready()` with
    5 s timeout); assert resolver hits a known dokumentnummer.
- **Primitives:** `monkeypatch` with two-Event-gated generator
  (deterministic, NOT `time.sleep`), two `TestClient` context managers,
  `caplog.records` inspection, `os.path.exists` triple-check across
  `.new` + `.new-journal`.

### Seam 4 — internal-resolver threshold instrumentation parse-fidelity

- **Anti-pattern named:** "regex matches anything numeric" — smoke
  regex like `r"ms=([\d.]+)"` matches any `"ms=NNN"` anywhere in
  uvicorn log. If log format regresses (refactor changes
  `"vgm resolver: number=42 ms=12.3 hit=True"` to structured JSON,
  OR adds `ms=200` elsewhere in unrelated log lines), regex still
  captures **a** number — but possibly an unrelated field.
- **Test approach:**
  - Smoke regex MUST be:
    ```python
    re.compile(
        r"^.*vgm resolver: number=(?P<n>\d+) ms=(?P<ms>\d+\.\d+) "
        r"hit=(?P<hit>True|False)\s*$",
        re.MULTILINE,
    )
    ```
  - Anchored start (`^.*`), anchored end (`\s*$`), specific keyword
    `"vgm resolver:"`, named capture groups.
  - **Cross-field check:** captured `n` MUST equal the dokumentnummer
    the smoke just submitted (smoke knows what it sent). On mismatch,
    smoke FAILS LOUDLY with `"log line matched but number field N
    captured != N_submitted submitted"` — never silent pass.
  - **Format-tightness check:** `ms` requires `\d+\.\d+` (decimal
    float). If a log refactor changes `%.1f` → `%d`, the regex fails
    to match; smoke FAILS with `"vgm resolver log line not found in
    expected format"`.
  - **Hit-boolean cross-check:** cold-start expects `hit=False`
    alongside `VgmIndexNotReady` render; miss expects `hit=False` with
    miss render; found-item expects `hit=True` with redirect.
  - **Per goal (c):** smoke runs step 8b 3 times consecutively per
    path; parses log fresh each run; records all three captured `ms`
    values in `PROGRESS.md`; `max(3)` MUST satisfy ≤ 50 ms.
- **Primitives:** anchored `re.compile` with named groups, cross-field
  verification, format-strict, explicit FAIL with descriptive message
  on regex non-match.

### Seam 5 — refresh-thread silent-death on non-httpx exception

- **Anti-pattern named:** "happy-path refresh test illusion" — test
  instantiates `IndexStore`, calls `refresh()` once with a mock that
  succeeds, asserts no exception raised. PASSES for any implementation
  regardless of exception-handling coverage. Variant:
  `with pytest.raises(...)` serial test calling `refresh()` directly
  outside the thread context, asserting the exception is caught —
  does NOT verify the THREAD stays alive after the catch.
- **Test approach:**
  - **Test 5a (sqlite storage failure):** `monkeypatch sqlite3.connect`
    to raise `sqlite3.OperationalError("disk full")` ONLY on the BUILD
    connection path (distinguished by path containing `.new`); resolver
    connection still works against the pre-existing index. Start
    lifespan; wait via signal `Event` set by the monkeypatched function
    before raising; assert `refresh_thread.is_alive() is True`; assert
    `caplog` contains a record where `"vgm index refresh"` in
    `record.message` AND `"OperationalError"` in `record.message` AND
    `record.levelno == logging.ERROR`.
  - **Test 5b (filesystem permission failure):** `monkeypatch os.replace`
    to raise `OSError(errno.EACCES, "Permission denied")`. Same three
    assertions: thread alive, log present, level ERROR.
  - **Test 5c (DATEV response shape regression):** `monkeypatch
    KlardatenClient.list_pages` to raise
    `KeyError("dokumentnummer")`. Same three assertions, with type
    name `"KeyError"` in message.
  - **Test 5d (control case — httpx is warning, not error):**
    `monkeypatch KlardatenClient` to raise `httpx.ConnectTimeout(...)`.
    Assert thread alive, `caplog` record exists, but
    `record.levelno == logging.WARNING` (this IS the expected transient
    case; the level distinction must be symmetric).
  - All four tests use a `threading.Event` signal set by the
    monkeypatched function before raising, ensuring assertions run
    AFTER the failure path executed.
  - **Critical:** tests MUST check `refresh_thread.is_alive()` AFTER
    the failure, not just "exception was logged". A naive variant
    asserting only "log line present" passes against an implementation
    that logs then re-raises and lets the thread die.
- **Primitives:** monkeypatch on `connect` / `os.replace` /
  `list_pages`, `threading.Event` for "build attempted" signal,
  refresh_thread reference via `app.state.*` or fixture, `caplog`
  record-level inspection (`.levelno`, not just substring), explicit
  `thread.is_alive()` check.

## Exit criterion

11-step ordered chain. Each step has file/log/SHA/CI-URL evidence.
Smoke is the canonical gate per Seam 1 (live DATEV, not TestClient).
One owner commit at Step 10 (autonomy boundary respected at Step 9).

### Step 0 (HARD BLOCKER) — Owner ratify N

The Phase 2 OPEN cannot remain OPEN at slice exit. Owner commits a
choice `N ∈ {15, 30, 60}` or a counter-value. Decision recorded in
this file's §Open items section (replace `PENDING OWNER` with
`RATIFIED N=NN on YYYY-MM-DD`), and a ledger entry
`"N=NN ratified by owner YYYY-MM-DD"` appended to `.overseer/ledger.md`.

**Until ratified: Steps 1-10 forbidden.**

### Step 1 — Pre-smoke gate: 5 seam-tests verified passing in CI matrix

```bash
pytest tests/ -v --tb=short 2>&1 | tee artifacts/resolver-perf-pytest-${SHA}.log
```

CI workflow `.github/workflows/test.yml` updated with matrix:
```yaml
strategy:
  matrix:
    os: [ubuntu-latest, windows-latest]
runs-on: ${{ matrix.os }}
```

Seam 1 `test_atomic_swap_concurrency_n_readers` runs on both via
`subprocess.run` on win32, in-process on linux (per Seam 1 design).

**Required passes** (names indicative; actual names per implementation):
- Seam 1: `test_atomic_swap_concurrency_n_readers`
  (subprocess on Windows, in-process on Linux).
- Seam 2a: `test_cold_start_render_path` +
  `test_miss_render_path` +
  `test_resolver_raises_VgmIndexNotReady_exact_type`.
- Seam 2b: `test_builtat_arithmetic_positive` +
  `test_builtat_arithmetic_clock_skew_clamp`.
- Seam 3: `test_midbuild_interrupt_then_orphan_cleanup`.
- Seam 4: parser tests for `parse_smoke_results.py`
  (`test_parse_anchors_correctly` +
  `test_parse_fails_loudly_on_malformed_log`).
- Seam 5: `test_5a_sqlite_failure_thread_alive` +
  `test_5b_oserror_thread_alive` +
  `test_5c_unexpected_thread_alive` +
  `test_5d_httpx_warning_not_error`.

All seams are mock / `tmp_path` / subprocess — NO live DATEV.
**Evidence:** CI run URL with both `ubuntu-latest` + `windows-latest`
jobs PASSED; local pytest log captured at
`artifacts/resolver-perf-pytest-${SHA}.log` (Linux only — Windows path
verified via CI URL).

### Step 2 — Pre-smoke environment reset (cold-start precondition)

- **Linux:**
  `rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/Belegmeister/vgm_index.sqlite"*`
- **Windows:**
  `del "%APPDATA%\Belegmeister\vgm_index.sqlite*"`

Glob removes `.sqlite`, `-journal`, `.new`, `.new-journal` sidecars if
present.

**Note for cold-start runs (Step 4):** the cold-start branch renders
the sibling-of-miss message regardless of `dokumentnummer` (it fires
on `IndexStore.is_ready() == False` BEFORE any number lookup); Step 4
can use any valid integer.

**Evidence:** `ls`/`dir` output of user-data dir captured, showing no
`vgm_index.sqlite*` files.

### Step 3 — SB live boot against api.klardaten.com

```bash
uvicorn belegmeister.sb.app:app --port 8080 --log-level info \
  > artifacts/resolver-perf-uvicorn-${SHA}.log 2>&1 &
echo $! > artifacts/resolver-perf-uvicorn.pid
```

Wait until uvicorn log contains `"lifespan startup complete"` AND
`"vgm index refresh: starting first build"`.

**Evidence:** uvicorn log with both startup lines; pid file.

### Step 4 — Cold-start smoke runs (3 consecutive, build still in progress)

```bash
for i in 1 2 3; do
  /usr/bin/time -f "wall=%e" python scripts/smoke_test_sb_form.py \
    --step 8b --target localhost:8080 --dokumentnummer 1 \
    2>&1 | tee -a artifacts/resolver-perf-smoke-cold-${SHA}.log
done
```

Each run MUST complete BEFORE the first refresh build finishes
(cold-start renders the sibling-of-miss message while the background
thread is still building). 3 sub-second smokes fit comfortably in any
N ≥ 5 min.

Each smoke run output MUST contain literal `"wird erstmalig aufgebaut"`
— if a run renders `"nicht gefunden"` instead, the build completed
mid-test and the data is invalid (re-run from Step 2).

**Evidence:** 3 wall-clock values via `/usr/bin/time`; 3 smoke outputs
containing the literal cold-start string.

### Step 5 — Wait for first refresh build to complete

```bash
until grep -q "vgm index refresh complete" \
    artifacts/resolver-perf-uvicorn-${SHA}.log; do
  sleep 5
done
```

**Evidence:** uvicorn log line of form
`"vgm index refresh complete: %d entries, %d ms, source=DATEV-DMS-v2"`
— `N` entries + `T` ms extractable.

### Step 5.5 — Pre-verify MISS dokumentnummer

Direct SQLite query, bypassing in-process resolver wiring:

```bash
python - <<'PY' 2>&1 | tee artifacts/resolver-perf-precondition-${SHA}.log
import sqlite3, sys, os
from pathlib import Path
base = (Path(os.environ["APPDATA"]) / "Belegmeister"
        if sys.platform == "win32"
        else Path(os.environ.get("XDG_DATA_HOME",
                                  os.path.expanduser("~/.local/share")))
             / "Belegmeister")
with sqlite3.connect(str(base / "vgm_index.sqlite")) as conn:
    row = conn.execute(
        "SELECT guid FROM vgm_index WHERE dokumentnummer = ?", (99999999,),
    ).fetchone()
if row is None:
    print("PRECONDITION OK: 99999999 is miss")
    sys.exit(0)
else:
    print(f"PRECONDITION FAIL: 99999999 resolved to {row[0]}")
    sys.exit(1)
PY
```

If output is not `"PRECONDITION OK"` → abort exit chain at this step;
pick a different dokumentnummer (e.g. `99999998`); re-run Step 5.5;
proceed to Step 6 only on OK.

**Evidence:** precondition log file containing exactly
`"PRECONDITION OK: 99999999 is miss"`.

### Step 6 — Steady-state smoke runs (3 consecutive, post-build)

```bash
for i in 1 2 3; do
  /usr/bin/time -f "wall=%e" python scripts/smoke_test_sb_form.py \
    --step 8b --target localhost:8080 --dokumentnummer 99999999 \
    2>&1 | tee -a artifacts/resolver-perf-smoke-steady-${SHA}.log
done
```

Each run produces uvicorn log line
`"vgm resolver: number=99999999 ms=X.X hit=False"`.

**Evidence:** 3 wall-clock values; each smoke output containing literal
`"nicht gefunden"` + literal `"vor ~"` (clamp-safe per Q-render);
3 corresponding `"vgm resolver:"` lines in uvicorn log.

### Step 7 — Graceful SB shutdown

```bash
kill -TERM "$(cat artifacts/resolver-perf-uvicorn.pid)"
wait
```

Lifespan shutdown triggers refresh-thread `join(timeout=5)`;
orphan-cleanup runs on next startup if `.new` debris remains.

**Evidence:** uvicorn log final line `"lifespan shutdown complete"`
with no error trace.

### Step 8 — Parse + compute max(3) + threshold verdict

```bash
python scripts/parse_smoke_results.py \
  --pytest artifacts/resolver-perf-pytest-${SHA}.log \
  --uvicorn artifacts/resolver-perf-uvicorn-${SHA}.log \
  --smoke-cold artifacts/resolver-perf-smoke-cold-${SHA}.log \
  --smoke-steady artifacts/resolver-perf-smoke-steady-${SHA}.log \
  --output artifacts/resolver-perf-summary-${SHA}.json
```

`parse_smoke_results.py` is part of THIS slice's deliverables
(in-scope tooling per PB-P4-4); includes its own unit tests
(`test_parse_anchors_correctly`, `test_parse_fails_loudly_on_malformed_log`).
Uses the Seam 4 anchored regex; FAILS LOUDLY on non-match (never
silent default).

Extracts: 3 cold wall-clocks (s), 3 steady wall-clocks (s), 3 internal
resolver ms values, build duration ms. Computes `max(3)` per path;
PASS/FAIL against ≤ 1 s end-to-end + ≤ 50 ms internal.

**Evidence:** summary JSON with all extracted values + verdict.

### Step 9 — Stage + STOP (no commit)

Dev session:
- Updates `PROGRESS.md:470-471` placeholder → measurements per the
  template below.
- `git add artifacts/resolver-perf-* PROGRESS.md`
- `git status > artifacts/resolver-perf-staged-${SHA}.txt`
- `git diff --cached --stat >> artifacts/resolver-perf-staged-${SHA}.txt`
- **STOPS. Does NOT commit.**

Replace `<TBD — mandatory before close>` at `PROGRESS.md:470-471` with
EXACT template:

```markdown
- Resolver perf measured YYYY-MM-DD against live api.klardaten.com (commit {SHA}):
  - **Cold-start path** (no .sqlite → "VGM-Index wird erstmalig aufgebaut"):
    - 3 runs end-to-end wall-clock: X.XXs, Y.YYs, Z.ZZs
    - max(3) = M.MMs; threshold ≤1.00s → PASS|FAIL
  - **Refresh build duration** (uvicorn log "vgm index refresh complete"):
    - N entries indexed, T ms total wall-clock for full DATEV scan
  - **Steady-state path** (built index, unknown Dokumentnummer 99999999 →
    "nicht gefunden (zuletzt geprüft vor ~N Min)"):
    - 3 runs end-to-end wall-clock: X.XXs, Y.YYs, Z.ZZs
    - max(3) = M.MMs; threshold ≤1.00s → PASS|FAIL
  - **Steady-state internal resolver** (uvicorn log "vgm resolver: ms=..."):
    - 3 ms values: X.Xms, Y.Yms, Z.Zms
    - max(3) = M.Mms; threshold ≤50ms → PASS|FAIL
  - **N (refresh interval)**: NN min — owner-ratified YYYY-MM-DD via
    .overseer/slice/resolver-perf.md Step 0
  - **Artifact bundle**: artifacts/resolver-perf-{SHA}.* (6 files: pytest log,
    CI run URL, uvicorn log, smoke-cold log, smoke-steady log, precondition log,
    summary.json)
  - **Status**: CLOSED if all three max(3) ≤ threshold; otherwise BLOCKED with
    specific failing path + value
```

**Evidence:** staged state captured in
`artifacts/resolver-perf-staged-${SHA}.txt`; no git log entry yet.

### Step 10 — Owner verifies + commits (single commit)

Owner:
- Reviews `artifacts/` bundle: pytest log, CI URL (Windows job), uvicorn
  log, smoke-cold log, smoke-steady log, precondition log, summary JSON.
- Runs `git diff --cached` locally; reads PROGRESS.md replacement.
- Computes PASS/FAIL verdict per `max(3) ≤ threshold` per path.
- **If all PASS:** edits PROGRESS.md slice 4b status line `BLOCKED` →
  `CLOSED`; commits:
  ```
  slice 4b resolver-perf: measurements recorded by dev session, owner
  verified all max(3) ≤ threshold, status CLOSED. Artifact bundle
  artifacts/resolver-perf-${SHA}.*
  ```
- **If any FAIL:** edits PROGRESS.md status line to re-anchor `BLOCKED`
  to the specific failing path + value; commits:
  ```
  slice 4b resolver-perf: measurements recorded, owner verified path X
  failed at M.Mms vs threshold T.Tms, status remains BLOCKED. Next
  slice resolver-perf-v2 starts from this measurement.
  ```

**One owner commit total.**

**Evidence:** git log entry by owner; one commit hash; PROGRESS.md
final state visible via `git show`.

## Deferred to later slices

Each Deferred item has: source, WHY-later-not-now, trigger, negative
bound. Negative bound prevents "will-revisit-someday" drift.

### D-i — Refresh-metrics surface
- **Source:** Phase 1 OOS #1.
- **WHY later, not now:** warn-log is the only observability surface
  needed for V1 — smoke step 8b parses log directly; ops/owner workflow
  uses `tail`/`grep` on uvicorn log. No external monitoring consumer
  exists; surfacing Prometheus now is build-the-pipe-before-the-water.
- **Trigger:** operational complaint surfaces that "index seems stale"
  without log-tail access, OR external monitoring deployment requires
  resolver health probe.
- **Negative bound:** 6 months in production with no such complaint →
  Drop (V1 log surface confirmed sufficient).

### D-ii — Manual "rebuild index now" admin button / CLI command
- **Source:** Phase 1 OOS #2.
- **WHY later, not now:** background-refresh tick at interval N is the
  only rebuild trigger by design (Q1, ADR-locked). Adding manual
  trigger introduces a concurrent-rebuild race surface — manual
  rebuild swaps while scheduled tick is mid-build — that Q3 doesn't
  gracefully handle (would need an `is_refresh_in_progress` sentinel +
  queueing).
- **Trigger:** real operational case where waiting up to N min is
  intolerable AND user/owner has admin/CLI access AND the wait
  demonstrably affects business outcome.
- **Negative bound:** 6 months production with no such case → Drop.

### D-iii — 4c launcher first-launch splash / progress UI
- **Source:** Phase 1 OOS #4.
- **WHY later, not now:** Q3 sibling-of-miss message in the SB form is
  the UX surface for "not ready yet" within THIS slice's render path.
  4c launcher is a separate slice with its own UX surface (standalone
  launcher window, not embedded in SB form rendering) needing a
  different progress treatment.
- **Trigger:** 4c launcher slice begins planning (slice-boundary fires
  automatically — roadmap-bounded).
- **Negative bound:** project pivots away from 4c launcher concept →
  Drop.

### D-iv — Structured metrics emission from resolver
- **Source:** Phase 2 Q-threshold rejected alternative.
- **WHY later, not now:** no consumer for structured metrics exists
  yet. Log-line text with anchored regex (Seam 4) is sufficient for
  smoke parsing within this slice; structured emission would duplicate
  the surface for no gain at V1.
- **Trigger:** D-i fires (consumer appears) → reconsider as part of a
  metrics-surface slice; D-iv is dependent on D-i activation.
- **Negative bound:** subsumed under D-i's negative bound (if D-i
  drops, D-iv drops with it).

### D-v — Very-stale unit-switch display ("vor ~4 Std" / "vor ~2 Tg")
- **Source:** Phase 3 last-call probe 6d drop.
- **WHY later, not now:** V1 UX contract (Q-render) is "always Min
  unit, no Std/Tag thresholds". Most production cases will see N < 60
  min. Very-stale display (`"vor ~NNN Min"` with NNN > 120) is itself
  a useful visible-failure signal that something broke — converting to
  friendlier Std/Tag may mask the signal.
- **Trigger:** UX complaint that `"vor ~NNN Min"` with NNN > 120 looks
  broken/unprofessional, OR D-i monitoring shows freshness > 60 min as
  a common state (indicates refresh-tick frequency wrong or transient
  DATEV failures common).
- **Negative bound:** 6 months production with no such complaint →
  Drop.

## Considered-and-dropped (no trigger for revisit)

### X-i — Index schema migration / versioning for future v2
- **Source:** Phase 1 OOS #3.
- **WHY dropped:** atomic-full-swap means any future schema change
  rebuilds from scratch via a single new Q-rebuild step. DATEV is the
  canonical source of truth; no user data lost on schema change. If
  schema ever changes, that future slice rebuilds the index from DATEV
  API; no migration glue.

### X-ii — Cross-process / multi-instance index coordination
- **Source:** Phase 1 OOS #5.
- **WHY dropped:** architectural assumption — single SB process per
  machine. No two-process scenario in threat model. If a second SB
  ever starts on the same machine, Q4 transient connections + Q3 lock
  serialize SQLite access correctly (data integrity preserved); only
  undefined behavior would be "which process owns refresh", easily
  solved with a file-lock if needed later, but not a real failure mode
  at SB deployment scale (one user, one machine).

### X-iii — Index size / disk-pressure handling
- **Source:** Phase 1 OOS #6.
- **WHY dropped:** SB scale ≤ low hundreds of thousands of documents;
  SQLite point-lookup remains sub-millisecond at millions-of-rows
  scale per published benchmarks. Disk pressure is a deployment
  concern (admin provisions enough disk), not a software concern —
  index file at SB scale is < 100 MB.

### X-iv — "Gerade aktualisiert" display for just-built state
- **Source:** Phase 3 last-call probe 6b drop.
- **WHY dropped:** subsumed by 2b-α rounding contract — Q-render
  `int(max(0, float_minutes))` renders `"vor ~0 Min"` for any
  `built_at` within the last 30s. No separate string needed. If a UX
  complaint surfaces, that is D-v territory.

## Open items requiring human decision

**Owner ratification (2026-05-21, current)**: **N=30 min**. Rationale on amendment: 60 min staleness window deemed too long on reconsideration — no business reason justifies the additional 30 min between DATEV change and SB visibility. N=30 is the middle-ground recommendation from PB7.

**Prior ratification (superseded, 2026-05-21T10:15:17Z)**: N=60 min. Original rationale: dominant pain point is not-found latency (45s baseline → ≤50ms target), staleness window relaxed (1 hour acceptable per owner workflow with DATEV→SB timing). Superseded by owner amendment ~15 min later — see ledger entry `N_AMENDED` at 2026-05-21T10:18:50Z.

- **Source:** Phase 2 OPEN, reframed per PB7.
- **Question:** ADR-0001 Q1 states "biased long" — what value of N?
- **Candidates:**
  - **N = 60 min** — most "biased long"; staleness window ≤ 60 min;
    DATEV API load 24/day.
  - **N = 30 min** — middle; staleness ≤ 30 min; DATEV API load
    48/day.
  - **N = 15 min** — short end of "long"; staleness ≤ 15 min; load
    96/day.
- **Recommended option:** **N = 30** — middle ground between UX
  (acceptable staleness) and ADR's "biased long" constraint; 48/day
  load trivial.
- **Owner ratifies:** `N ∈ {15, 30, 60}` or other value. On
  ratification, edit this section to replace `PENDING OWNER` with
  `RATIFIED N=NN on YYYY-MM-DD`; append ledger entry; Step 0 of
  Exit criterion unblocks.
