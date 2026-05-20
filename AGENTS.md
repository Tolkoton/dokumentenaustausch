# Belegmeister

Internal automation for a German Steuerbüro's **Beleganforderung** workflow:
detect missing receipts in DATEV bookings, request them from clients via
magic-link upload pages, and (v2) push received files back into DATEV
Unternehmen Online via the klardaten gateway. Python 3.12, FastAPI,
Pydantic v2, strict mypy.

## Commands

All commands run with `uv` (lockfile is `uv.lock`).

- Install:   `uv sync`
- Test:      `uv run pytest`
- Lint:      `uv run ruff check .`
- Format:    `uv run ruff format .`
- Typecheck: `uv run mypy --strict src/ tests/ scripts/`
- CLI:       `uv run python -m belegmeister create-request --help`
- SB web:    `uv run uvicorn belegmeister.sb.app:app --reload`
- Magic-link web: `uv run uvicorn belegmeister.web.app:app --reload`

Smoke / probe / spike scripts live in `scripts/` and mutate live DATEV.
Read the header of each file before running it; use the dev instance.

## Project layout

- `src/belegmeister/__main__.py` — CLI entrypoint; argparse + env validation only.
- `src/belegmeister/cli/`         — testable CLI command logic.
- `src/belegmeister/sb/`          — Steuerbüro-facing FastAPI app (request-creation form).
- `src/belegmeister/web/`         — Mandant-facing FastAPI app (magic-link upload page).
- `src/belegmeister/magic_link/`  — HMAC token mint / verify (`token.py`).
- `src/belegmeister/datev/`       — DATEV adapters: `upload.py`, `resolver.py`.
- `src/belegmeister/klardaten/`   — `KlardatenClient` (httpx wrapper around the klardaten REST API).
- `src/belegmeister/{env_validation,request_format,validation_errors,vgm_files}.py` — shared boundary helpers.
- `tests/`         — mirrors `src/`; `tests/foo/test_bar.py` for `src/belegmeister/foo/bar.py`.
- `scripts/`       — smokes, probes, spikes. Dated filenames for spikes (`spike_*_YYYY-MM-DD.py`).
- `docs/`          — human + agent docs; see `docs/index.md`.
- `docs/adr/`      — append-only architecture decisions.
- `.architecture/` — phase artifacts from the master-architect skill (Phase 0–1).
- `PROGRESS.md`    — chronological slice log; append-only journal.

## Coding conventions

### Single source of truth for cross-layer logic

Validation or business logic that applies at more than one layer (e.g. a
Pydantic boundary model AND a domain codec) MUST be extracted into a shared
function — one source of truth. Each layer MAY wrap the result with its own
exception type (`ValidationError` at the API boundary, a domain error like
`RequestLetterMalformed` in the codec), but the RULE itself lives in exactly
one place. Duplicated validation logic across layers is a paranoid-SRP
violation and a correctness hazard (the copies drift; one gets a fix the
other doesn't).

Concretely: prefer small pure predicates (`is_single_line(s) -> bool`,
`has_sentinel_collision(s) -> bool`, `is_blank(s) -> bool`) that every
layer calls, over re-implementing the check per layer.

### Other conventions

- Strict typing: `mypy --strict` clean. No `Any`, no `# type: ignore`.
- Use Pydantic v2 models or `@dataclass(frozen=True)` for structured data.
- Named exceptions carry `target id + reason` in their message so operational
  logs read self-describingly without traceback diving (see `InvalidUploadTarget`).
- Tests are wide and behaviour-driven; one test per distinct behaviour, not
  one per function. See existing `tests/datev/` and `tests/sb/` for tone.

## DATEV / klardaten integration notes

All DATEV access goes through **klardaten** (`api.klardaten.com`). See
[ADR-0002](docs/adr/0002-klardaten-gateway-for-datev.md) for the choice and
[ADR-0001](docs/adr/0001-resolver-perf-persisted-index.md) for the
resolver-perf decision.

- **No server-side filter exists.** `$filter=number eq X`, `?number=X`, and
  by-number path routes are all silently ignored by klardaten's documents API.
  `$top` is ignored too — page size is fixed at 1000; only `$skip` paginates.
  Settled by `scripts/spike_direct_lookup_2026-05-19.py`; do not re-probe.
- **DATEV developer portal is a JS-SPA.** `WebFetch` returns an empty shell.
  The empirical klardaten / DMS v2 schema is encoded in the upload module and
  tests; high-level notes live in `docs/DATEV-DEVELOPER-PORTAL.md`.
- **Wire vs error casing.** Error messages use PascalCase (`Class`,
  `StructureItems.Counter`); the JSON wire is snake_case (`class`,
  `structure_items[].counter`). Same fields, different surface.
- **`structure_items` ≠ folder path.** It is the file-attachment list inside a
  document. Folder path lives top-level as `folder` + optional `register`.
- **`document_file_id` is single-shot.** Reusing one id on a second
  `structure-items` POST yields `"document_file_id N is not available"`.
- **Upload is intrinsically two HTTP calls** (POST `/document-files` then
  POST `/documents/{binder}/structure-items`). Hidden behind one public method.
- **Binder state is not API-enforced.** `erledigt` and `in Bearbeitung`
  binders both accept attachments. Any "don't upload to closed cases" rule
  is a business decision implemented in our code, not a DATEV constraint.

## Environment

Required env vars (validated at app startup; fail-fast). Loaded via
`python-dotenv` from a local `.env` in dev.

- `KLARDATEN_API_KEY`     — klardaten bearer.
- `KLARDATEN_INSTANCE_ID` — klardaten instance / tenant id.
- `KLARDATEN_BASE_URL`    — defaults to `https://api.klardaten.com`.
- `KLARDATEN_PROFILE_ID`  — optional profile selector.
- `MAGIC_LINK_SECRET`     — HMAC key for magic-link tokens; **≥ 32 bytes**.
- `MAGIC_LINK_BASE_URL`   — public origin for `/r/<token>` URLs; must be
                            `https://…` or `http://localhost…` (dev).

`.env` is hard-denied for editing by the autonomy hooks. Keep credentials
there and never commit it. Full table: `docs/reference/environment.md`.

## Gotchas

- **Magic-link tokens leak into transport logs** (uvicorn access log, reverse
  proxies, `Referer`). Inherent to URL-path tokens; mitigations are
  deployment-time. See `docs/SECURITY.md`.
- **VGM resolver is being rewritten.** Today's `resolve_binder_guid_by_number`
  paginates synchronously and can take ~45 s for a not-found number. The
  replacement is a persisted SQLite number→GUID index — read
  [ADR-0001](docs/adr/0001-resolver-perf-persisted-index.md) before touching
  `src/belegmeister/datev/resolver.py`.
- **`PROGRESS.md` is append-only.** Edit retroactively only to fix factual
  mistakes; otherwise add a new section.
- **Autonomy hooks block `git commit`.** Stage with `git add <files>` and
  print a one-line summary + suggested commit message; the human commits.
  See the `## Autonomy policy` block at the top of `CLAUDE.md`.

## Where to look

- API / CLI / env reference: [`docs/reference/`](docs/reference/).
- Architecture decisions (append-only): [`docs/adr/`](docs/adr/).
- DATEV portal map: [`docs/DATEV-DEVELOPER-PORTAL.md`](docs/DATEV-DEVELOPER-PORTAL.md).
- Security and known limitations: [`docs/SECURITY.md`](docs/SECURITY.md).
- Phase 0 / 1 architecture artifacts: `.architecture/`.
- Slice-by-slice history: `PROGRESS.md`.
- Autonomy rules (commits, hooks, allowed Bash): top of `CLAUDE.md`.
