# Belegmeister — slice progress log

## Slice 1 — DATEV DMS v2 upload INTO a Vorgangsmappe via klardaten (DONE 2026-05-13)

The slice underwent one mid-flight semantics change: an initial reading of "folder 395239" placed the upload as a *sibling* of doc #395239 in `Mandanten / Sonstiges`. UI verification showed the binder #395239 itself was still empty, and the real intent — "place the file *inside* the Vorgangsmappe 395239" — was clarified. The slice was refactored to take a binder GUID, validate `is_binder + extension==VGM`, and attach via the structure-items sub-resource. Final smoke verified two files inside the binder.

### Modules

- `src/belegmeister/datev/upload.py` (152 LOC) — `upload_to_binder(file_path, binder_guid, klardaten_client)`, `UploadResult`, `InvalidUploadTarget` (named exception carrying `binder_guid` + `reason`).
- `src/belegmeister/datev/resolver.py` (47 LOC) — `resolve_binder_guid_by_number`, kept deliberately separate from upload. Paginates and scans in-memory until DATEV's filter syntax is known.
- `src/belegmeister/klardaten/client.py` (~140 LOC) — `KlardatenClient` with `get_document`, `list_documents`, `attach_file_to_binder` (two-step: bytes → structure-item).

### Tests

- 3 import/contract tests, green:
  - module surface
  - `upload_to_binder` short-circuits on missing file without calling the client
  - `InvalidUploadTarget.__str__` includes both target id and reason (operational logging contract)
- No mock-based behavioural tests yet; smoke is the truth source. Real branching (validation, 2-step flow, response mapping) now exists — mock tests are warranted in the next slice.

### Smoke

- `scripts/smoke_test_datev_upload.py` — given a Dokumentnummer, resolves to a GUID, validates Vorgangsmappe, attaches a freshly-generated `.txt`.
- Verified end-to-end against binder #395239 on 2026-05-13: structure-item id `1170065` (final smoke), plus `probe_inside_binder.txt` from earlier probe. Both visible inside the binder in the DATEV UI.
- `scripts/probe_dms.py` retained for future field-name reconnaissance (GET-only).

### Gates

- ruff clean
- mypy `--strict` on 11 source files
- pytest 3/3

### Surprises (this slice)

- **DATEV developer portal is a JS-SPA** — `WebFetch` cannot render it. Schema was fully reverse-engineered from successive 400 responses and GETs. Captured in user-level memory `project-datev-dms-v2-schema`.
- **Wire vs error case.** Error messages use PascalCase (`Class`, `StructureItems.Counter`); the JSON wire is snake_case (`class`, `structure_items[].counter`). Same fields, different surface.
- **`structure_items` ≠ folder path** — it is the *file-attachment list* inside a document. Folder path lives top-level as `folder` + optional `register` object refs.
- **`document_file_id` is an int** (returned as a string from `/document-files`, sent back as int in the structure-item). Each id is one-shot — re-using it on a second structure-item POST yields `"document_file_id N is not available"`.
- **Upload is intrinsically two HTTP calls** (`POST /document-files` then `POST /documents` or `POST /documents/{binder}/structure-items`). Hidden behind one public method; the seam stays one method. Reinforces the seam-vs-impl-detail principle.
- **"Folder 395239" was a Dokumentnummer, not a folder ID.** Real folder IDs are tiny ints (Sonstiges=11, Steuern=5). Worse, 395239 is a *binder*, so "upload to folder 395239" really meant "upload INTO the Vorgangsmappe 395239". Took one wrong-target smoke + UI feedback to surface the true intent.
- **Binder state is not API-enforced.** Attaching to `erledigt` and `in Bearbeitung` binders both returned `200`. Any "don't upload to closed cases" rule is a business decision, not a DATEV constraint.

### Open for next slice

- **Verify-after-upload** — GET the binder's structure-items after attach, confirm the new item's `size` matches `len(file_bytes)`.
- **Retry / backoff** — no retries today. Transient 5xx and network errors bubble straight into `UploadResult.error`.
- **Mock-based unit tests** — the slice now has real branching (validate → fetch → ensure → upload → map response) that's worth fake-driven testing. The thin-wrapper waiver no longer applies.
- **Filter query syntax** — `$filter=number eq X` and `?number=X` are silently ignored. Resolver scans up to `page_size * max_pages` records (50_000 by default) — adequate for now, but a real filter would be cleaner.
- **Multi-file documents** — we always send one structure-item. Existing binders carry several; bulk attach is plausible but untested.
- **Filename generation, .env reading, structured logging** — explicitly out of scope per the slice contract.
- **`abgeschlossen` binder state** — not seen on this instance; behaviour speculative. If/when one appears, add a probe.
- **Optional `allowed_states` business rule** — opt-in arg on `upload_to_binder` to reject e.g. `erledigt` binders. Deferred.

### Files added / changed

- New: `src/belegmeister/{,datev/,klardaten/}__init__.py`, `src/belegmeister/datev/upload.py`, `src/belegmeister/datev/resolver.py`, `src/belegmeister/klardaten/client.py`, `tests/{,datev/}__init__.py`, `tests/datev/test_upload_smoke.py`, `scripts/smoke_test_datev_upload.py`, `scripts/probe_dms.py`, `PROGRESS.md`.
- Modified: `pyproject.toml` (deps: `httpx`, `python-dotenv`; dev: `pytest`, `mypy`, `ruff`; src layout via hatchling; mypy strict).
- Deleted: `README.md` (pre-existing deletion in working tree; `readme = "README.md"` removed from `pyproject.toml` to unblock the build).

### Test pollution to clean up in DATEV UI (optional)

- Inside binder #395239: `probe_inside_binder.txt`, `belegmeister_smoke_*.txt` (final smoke), and an earlier counter=2 probe.
- Inside binder #395295 (erledigt): `probe_state_erledigt.txt`.
- Inside binder #393068 (in Bearbeitung): `probe_state_in.txt`.
- Sibling of binder #395239 in Mandanten/Sonstiges: doc #395317 (first wrong-semantics smoke).

Suggested commit message:

```
feat(datev): upload a file INTO a DMS Vorgangsmappe via klardaten

- upload_to_binder validates is_binder + extension=="VGM" before any bytes;
  invalid target raises InvalidUploadTarget(binder_guid, reason)
- KlardatenClient.attach_file_to_binder is a two-step flow internally
  (POST /document-files -> POST /documents/{binder}/structure-items),
  exposed as one method; the seam stays unchanged
- resolve_binder_guid_by_number is a separate function: "find the target"
  and "act on the target" are not mixed
- smoke_test_datev_upload resolves a Dokumentnummer and attaches a fresh
  .txt to that binder; probe_dms kept for future reconnaissance
- README.md stayed deleted (was already removed in working tree)
```

## Slice 2 — create-request CLI: HMAC magic-link + letter upload into VGM (DONE 2026-05-15)

A SB runs `python -m belegmeister create-request --vgm-id <guid> --letter-file <path> --ttl-days 7`; the letter body is uploaded into the VGM as `_request_letter_<ISO>.md`, an HMAC-signed token `{vgm_id, exp}` is generated, and a magic-link URL `<base>/r/<token>` is printed to stdout. State lives entirely in DATEV (one Request = one VGM). The token module is built to be re-used verbatim by the next slice's HTTP handler.

### Modules

- `src/belegmeister/magic_link/token.py` (~115 LOC) — `generate_token` / `verify_token` (flow methods over SRP helpers), `TokenPayload` (frozen dataclass, `exp: int` unix seconds), `InvalidToken(reason)`. Wire format `base64url(json).base64url(hmac_sha256)`; canonical sorted-keys JSON so signing is deterministic.
- `src/belegmeister/cli/create_request.py` (~110 LOC) — `CreateRequestArgs` (Pydantic v2, validated via `model_validate(data, context={"now": now})`), `run_create_request` flow, `UploadFailed(vgm_id, reason)` named exception.
- `src/belegmeister/__main__.py` (~190 LOC) — humble glue: `.env` load, boundary security checks, argparse subparsers, exception→exit-code. Deliberately NOT unit-tested (covered by smoke + the flow tests beneath it).
- `src/belegmeister/datev/upload.py` — one-line change: `_BinderClient` → public `BinderClient` (Protocol promoted so three modules share one DI shape; no methods added).

### Tests (25 total, all green)

- `tests/magic_link/test_token.py` — 13: TG1-2 (gen structure + determinism), TV1-5 (round-trip, expiry incl. `now==exp` boundary, wrong-secret sig mismatch, three malformed shapes, four bad-payload shapes).
- `tests/cli/test_create_request_args.py` — 7: RC2 (empty letter/vgm_id), RC3 (expires_at ≤ now incl. equality boundary), RC4 (TTL > 7d, exactly 7d accepted, 7d+1s rejected via `.total_seconds()`).
- `tests/cli/test_create_request_flow.py` — 5: RC1 (happy path with in-memory fake `BinderClient`, asserts file name + bytes + URL + token round-trip), RC5 (`InvalidUploadTarget` bubbles up, no attach), RC6 (`UploadFailed` on `success=False`, no URL).

### Smoke

- `scripts/smoke_test_create_request.py` — resolves a Dokumentnummer, writes a German tax-doc letter, invokes `python -m belegmeister create-request` as a **subprocess** (exercises real env-load + argparse + exit-code path), prints URL + UI verification instructions.
- Verified end-to-end against **VGM #395239** (`_request_letter_2026-05-15T080805Z.md`) and **VGM #395357** (`_request_letter_2026-05-15T082815Z.md`) — both files visible inside the binders in DATEV UI; both emitted tokens round-trip via `verify_token` with the real `.env` secret (proves the next slice's handler can verify them).

### Gates

- ruff clean, mypy `--strict` (22 files), pytest 25/25.

### Security (baked in, per checklist)

- `MAGIC_LINK_SECRET` ≥32 bytes, fail-fast at env load (before argparse side-effects); never logged.
- `verify_token` uses `hmac.compare_digest` (timing-safe), not `==`.
- `MAGIC_LINK_BASE_URL` must be `https://` (or `http://localhost` for dev) — checked at env load.
- TTL hard-capped at 7 days via `.total_seconds()` strict-greater-than (floor-by-`.days` would silently extend lifetime up to 23h59m).
- `InvalidToken.__init__` takes only `reason`, never the token — no path to leak a live credential into logs/tracebacks.
- Full magic-link URL printed to stdout only (in `__main__`); never logged elsewhere.
- `_b64url_decode` strict (`b64decode(validate=True)` + alphabet translate): malformed tokens raise `InvalidToken("malformed: …")` instead of decoding to truncated garbage that masquerades as a signature mismatch.

### Surprises (this slice)

- **`base64.urlsafe_b64decode` is lenient** — silently drops out-of-alphabet bytes. `"!!!.@@@"` decoded to short garbage and surfaced as "signature mismatch" instead of "malformed". Switched to `b64decode(translate("-_","+/"), validate=True)`. (Caught by TV4 RED.)
- **mypy strict + `json.loads`→`Any`** forced isinstance-narrowing in `_decode_payload` as early as TV1 GREEN — so TV3 (wrong secret) and all four TV5 (bad payload) tests passed *immediately with no impl change*; the narrowing was already compelled by the type system.
- **Stop hook vs strict-RED-STOP conflict** — `verify-on-stop.sh` blocks turn-end on red pytest, incompatible with pausing between RED and GREEN across turns. Resolved by keeping RED+GREEN in the same turn (RED shown, then GREEN) — preserves both TDD visibility and green-commit discipline.
- **Stop hook runs `mypy .` not `mypy src/`** — picked up the uv-init `main.py` stub at repo root (untyped). Patched its signature to `-> None` to unblock; flagged for housekeeping.
- **`python-dotenv could not parse statement starting at line 7`** — non-fatal warning on every run; env vars still load correctly. `.env` line 7 has a line dotenv can't parse (likely a comment/quoting issue from the appended block or a pre-existing Slice-1 line). Cosmetic but noisy.

### Open for next slice

- **HTTP handler slice** — `GET /r/<token>` serves the upload form, `POST /r/<token>/submit` handles client upload. Re-uses `verify_token` verbatim with the same `MAGIC_LINK_SECRET`. `MAGIC_LINK_BASE_URL` flips from the stub to a real domain (or `http://localhost:8000` / ngrok for dev).
- **`console_scripts` entry** in `pyproject.toml` so the command is `belegmeister create-request …` without `python -m`. Cosmetic; do it once the subparser structure is stable (packaging slice).
- **Housekeeping (separate commit, after this slice closes):** delete the root `main.py` uv-init stub; set `[tool.mypy] files = ["src", "tests"]` so root-level stubs don't block hooks; investigate the dotenv line-7 parse warning.
- **No verify-after-upload** — `run_create_request` trusts `UploadResult.success`; a GET roundtrip confirming the structure-item exists is deferred (same as Slice-1).
- **No idempotency** — re-running `create-request` for the same VGM creates a second `_request_letter_*.md`. Intentional (each run auditable), but a future "re-issue link" command may want to supersede rather than accrete.
- **`--ttl-days` default 7 = max 7** — no room above the cap. If a longer-lived link is ever needed it's a policy change in `MAX_TTL_DAYS` + a conversation about exposure, not a CLI tweak.

### Files added / changed

- New: `src/belegmeister/magic_link/{__init__,token}.py`, `src/belegmeister/cli/{__init__,create_request}.py`, `tests/magic_link/{__init__,test_token}.py`, `tests/cli/{__init__,test_create_request_args,test_create_request_flow}.py`, `scripts/smoke_test_create_request.py`.
- Modified: `src/belegmeister/__main__.py` (skeleton → full glue), `src/belegmeister/datev/upload.py` (`_BinderClient`→`BinderClient`), `src/belegmeister/cli/create_request.py` (skeleton → impl), `main.py` (added `-> None` to unblock Stop hook — slated for deletion), `pyproject.toml` + `uv.lock` (added `pydantic>=2.7`).
- Untracked (gitignored, do NOT commit): `.env` (appended `MAGIC_LINK_SECRET`, `MAGIC_LINK_BASE_URL`).

Suggested commit message:

```
feat(cli): create-request — HMAC magic-link + letter upload into VGM

- magic_link.token: generate/verify HMAC-SHA256 tokens {vgm_id, exp};
  compare_digest, strict base64url, deterministic canonical JSON;
  built for verbatim reuse by the upcoming HTTP handler slice
- cli.create_request: Pydantic-validated args (non-empty letter,
  expires_at in future, 7-day TTL hard-cap), flow uploads letter as
  _request_letter_<ISO>.md into the VGM then emits <base>/r/<token>
- UploadFailed named exception (kw-only vgm_id+reason), mirrors
  Slice-1's InvalidUploadTarget; __main__ catches named domain
  exceptions → stderr+exit 1, lets unknown ones traceback
- __main__: humble glue with boundary security (secret >=32B,
  https-only base URL), argparse subparsers (extensible)
- datev.upload: _BinderClient promoted to public BinderClient so
  cli + future handler share one DI shape (no methods added)
- 25 tests (token 13, args 7, flow 5); smoke verified against
  VGM #395239 and #395357
```
