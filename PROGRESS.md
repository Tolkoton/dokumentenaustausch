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

## Slice 3 — HTTP handler for the client magic-link page (DONE 2026-05-15)

The client clicks the Slice-2 link → `GET /r/{token}` verifies the token
(Slice-2 `verify_token`, imported not copied), lists the VGM's children,
picks the newest `_request_letter_*.md`, downloads + UTF-8 decodes it,
renders an HTML page (letter text + drag-drop zone + freeform response
textarea + submit button). Any failure → one generic 404 page; the
specific cause goes only to a structured server log (never the token).
`POST /r/{token}/submit` is the next slice (form posts there; a click
404s until then — intentional, verified not 405/500).

### Spike first (download API was unproven)

`GET /documents/{guid}` does NOT include children (Slice-1 memory was
wrong). `scripts/probe_download_2026-05-15.py` (read-only, kept for
reference) reverse-engineered against #395239:
- children: `GET /documents/{guid}/structure-items` → JSON array
  (type=1 file w/ `document_file_id`+`size`; type=2 sub-folder).
- bytes: `GET /document-files/{id}` with **`Accept: application/
  octet-stream`** (server self-describes the requirement in a 400).
  Same upload API key works for download. Memory
  `project-datev-dms-v2-schema` updated with a download section.

### Modules

- `src/belegmeister/web/request_view.py` (~159 LOC) — `resolve_request_view`
  flow over SRP helpers (`_verify`, `_list_children`, `_pick_newest_letter`,
  `_download_text`), `RequestView`, `RequestLinkInvalid` (structured
  `log_reason` from a canonical list + `log_context`; token never in it),
  `LetterSource` Protocol (public DI seam, same rationale as Slice-2
  `BinderClient`).
- `src/belegmeister/web/app.py` (~100 LOC) — FastAPI glue: `get_letter_source`
  / `get_secret` / `get_now` deps (overridable in tests), `GET /r/{token}`,
  `load_dotenv()` at import, explicit `jinja2.Environment(autoescape=True)`
  (filename-independent XSS protection).
- `templates/request.html`, `templates/invalid.html` (Tailwind CDN, `<pre>`
  letter — no markdown render, autoescaped).
- `KlardatenClient.list_structure_items` + `download_document_file` —
  spike-proven thin wrappers, smoke-first (no mock-TDD, Slice-1 pattern).

### Tests (21 web, 46 total, all green)

- `test_request_view.py` — RV1 (happy), RV2 (token_invalid + no-DATEV-on-bad-
  token), RV3 (token_expired, pins cross-module `"expired"` literal), RV4
  (404→vgm_not_found vs 503/timeout→datev_error — narrowed from over-broad
  catch), RV5 (download httpx→download_failed, non-httpx propagates as bug,
  invalid-UTF8→letter_not_utf8). RV6 absorbed into RV5b.
- `test_pick_newest_letter.py` — FS1-4 (newest/mixed/empty/single, all
  test-as-contract) + FS5 (driven: added `.md` suffix check — a real gap
  the test-as-contract streak had masked).
- `test_app_route.py` — RT1 (200 HTML + form attrs), RT2 (404 generic, no
  cause disclosure, structured log, token NOT in log), RT3 (XSS:
  `<script>`→`&lt;script&gt;`).

### Gates

- ruff clean, mypy `--strict` (14 src), pytest 46/46.

### Smoke (live uvicorn + real CLI links)

- Bug caught: `app.py` never called `load_dotenv()` → under uvicorn
  `KeyError: KLARDATEN_API_KEY` in `solve_dependencies` → bare 500. Unit
  tests override deps so they were green. Fixed (load_dotenv at import).
- Verified against fresh `python -m belegmeister create-request` links
  for #395239 and #395357: happy 200 + letter HTML + correct form
  (`/r/{token}/submit`, multipart, file+response inputs); corrupted
  token → 404 generic; expired → 404 generic; `POST .../submit` → 404
  (not 405/500); app logger clean (`reason=token_invalid context={}`,
  no token). Browser/mobile visual check: user-side, post-commit.

### Surprises

- **Children are a sub-resource**, not part of the binder doc. Slice-1's
  "structure_items in GET /documents" note was wrong.
- **Download mandates `Accept: application/octet-stream`** — any other
  Accept → 400 (the 400 body self-documents the requirement).
- **Magic-link token leaks into ACCESS logs** — uvicorn (and any nginx/
  LB) logs the request line `GET /r/<token>`, so the token lands in
  access logs / browser history / Referer. Our *application* logger is
  clean (RT2 verified); this is an inherent property of token-in-URL-
  path, not a code leak. Mitigation deferred (open item).
- **Premature SRP error-mapping in RV1 GREEN → false completeness.** The
  test-as-contract streak (RV2/RV3, FS1-4) *felt* done but masked the
  missing `.md` filter; only an extra spec-derived fixture (FS5) caught
  it. Captured as a cross-session memory.
- **`load_dotenv` gap invisible to unit tests** — dependency overrides
  meant the env-reading path was never exercised until smoke.

### Housekeeping log (2026-05-15)

- ✅ **Root `main.py` stub deleted** (`git rm`, unreferenced uv-init
  boilerplate). `mypy .` clean without it.
- ✅ **mypy `files=` — closed without change.** The Slice-2 note to set
  `["src","tests"]` was based on a misread: the Stop hook runs `mypy .`
  (no-arg, ignores pyproject `files=`), so deleting `main.py` was the
  real fix. `scripts` stays in `files=` (probe/smoke want type-checking).
- ✅ **`InvalidToken` → `InvalidTokenReason` (StrEnum) — DONE.** Typed
  `.reason` {MALFORMED, BAD_SIGNATURE, EXPIRED} + `.detail` (human text
  for logs). All 9 raise sites + `request_view._verify` (enum identity,
  no more `"expired"` string-match) + `test_token.py` (assert `.reason`,
  not `match=`). Behaviour-preserving; 46/46.
- ✅ **3-way log_reason split (done).** `_verify` maps each
  `InvalidTokenReason` to a distinct server log_reason via
  `_TOKEN_LOG_REASON`: `token_expired` / `token_malformed` /
  `token_bad_signature`. Client still sees ONE generic 404 (no
  disclosure); the split is log-only → free tamper-detection (spike of
  `token_bad_signature` = forgery; `token_malformed` = benign
  truncation). 5-line `_verify` change + 3 test-assertion updates,
  RED+GREEN. Initially deferred as a future enhancement; user pulled it
  into housekeeping scope. `log_reason` is a tested contract so this is
  a small logging-boundary change, not pure refactor (honest framing).
- ✅ **Token-in-access-log — documented, not fixed.** Inherent magic-link
  property (token in URL path → uvicorn/proxy access logs, browser
  history, Referer). App logger is clean (RT2 + smoke). Written up in
  `docs/SECURITY.md` with deployment-time mitigations + the now-
  implemented tamper-detection table. No code change for this item.

- ✅ **C1: web-startup env fail-fast — DONE.** New shared module
  `belegmeister/env_validation.py` (3 pure helpers: `validate_required`,
  `validate_secret` ≥32 *bytes*, `validate_base_url` https/localhost),
  with its own unit tests. `web/app.py` gained a FastAPI `lifespan` that
  runs the checks at startup and turns `ValueError → RuntimeError` so
  uvicorn refuses to boot (no more mid-request `KeyError` → 500).
  `__main__._load_env_config` migrated to the same helpers (real DRY,
  not duplicated validation) — behaviour-preserving, verified the CLI
  still emits the identical `error: …` message + graceful exit (not a
  traceback). Tests: env_validation unit + lifespan via
  `with TestClient(app)` (ok / each missing required / short secret /
  non-https / localhost-ok). 67/67, mypy --strict (33), ruff clean.
  Corrections from Step-0: env var is `KLARDATEN_INSTANCE_ID` (not
  `X_CLIENT_INSTANCE_ID` — that's the HTTP header); secret threshold is
  bytes not chars; `KLARDATEN_BASE_URL` stays optional (has a default).

### Still open

- Carried: investigate `.env` line-7 dotenv parse warning (user-side —
  `.env` is hard-deny for the agent; `sed -n '5,9p' .env`).

### Files added / changed

- New: `src/belegmeister/web/{__init__,app,request_view}.py`,
  `src/belegmeister/web/templates/{request,invalid}.html`,
  `tests/web/{__init__,test_request_view,test_pick_newest_letter,
  test_app_route}.py`, `scripts/probe_download_2026-05-15.py`.
- Modified: `src/belegmeister/klardaten/client.py` (+`list_structure_items`,
  +`download_document_file`), `pyproject.toml`+`uv.lock` (fastapi,
  uvicorn[standard], jinja2).

Suggested commit message:

```
feat(web): GET /r/{token} — render client magic-link upload page

- resolve_request_view: verify token (reuse Slice-2) -> list VGM
  children -> newest _request_letter_*.md -> download+utf8 -> view;
  any failure -> generic RequestLinkInvalid (structured log_reason,
  token never logged)
- FastAPI app: humble glue, overridable deps, load_dotenv at import,
  explicit autoescape=True (filename-independent XSS guard)
- KlardatenClient.list_structure_items + download_document_file
  (spike-proven; Accept: application/octet-stream mandatory)
- 21 web tests; smoke verified vs VGM #395239 and #395357
- probe_download script + DMS-v2 memory updated with download section
```

## Slice 4 — Structured questions (DESIGN FINALIZED 2026-05-15, impl = separate session)

Origin: after seeing the working freeform Slice-3 page, structured
per-question answer fields are judged real product value (earlier
rejected as premature). Spans Slices 2-4. Design is now locked — Step-0
is closed. Do NOT implement here; implementation is its own session.

Fixed decisions (the contract for the implementation session):

1. **Authoring** — the SB writes questions as plain text, one per line.
   No JSON, no question IDs. New `--questions-file <path>` CLI arg on
   Slice-2 `create-request`, separate from `--letter-file` (letter stays
   for context/instructions). Two-file input.
2. **Storage in the VGM** — a separate `_request_questions_<ISO>.txt`
   alongside `_request_letter_<ISO>.md`. Plain text, copied as-is;
   Slice-2 does NOT parse it.
3. **Required vs optional** — all questions optional; the client may
   skip any. Submit is allowed with empty fields, gated only by a single
   "≥1 file OR ≥1 non-empty answer" guard (no fully-empty submit).
4. **Submit mapping** — the submit slice writes a plain-text
   `_response_<ISO>.txt` into the VGM:
   ```
   Q1: <question text>
   A1: <client answer, or empty>

   Q2: ...
   A2: ...
   ```
   Client-uploaded files go into the VGM with a timestamp prefix as
   already planned.
5. **Backward compatibility** — graceful fallback. No
   `_request_questions_*.txt` in the VGM → handler renders exactly like
   Slice-3 (one textarea, no question fields). Implementation:
   `questions = []` when the file is absent; template guards the
   per-question block with `{% if questions %}`.

Implementation touch points (for the impl session): Slice-2 CLI
(`--questions-file`, upload second file), `request_view` (fetch +
split `_request_questions_*.txt` → `list[str]`, newest by ISO like the
letter; `[]` when absent), `request.html` (`{% if questions %}`
per-question fields else the Slice-3 textarea), and the future submit
slice (`_response_<ISO>.txt` writer + the ≥1-guard).

## Slice 4a — request-letter format (codec) + shared core + CLI (DONE 2026-05-19)

First SB-side slice's foundation. Single `_request_letter_<ISO>.txt`
now carries email metadata + body + questions in one human-readable,
machine-parseable, collision-proof wire format; CLI updated to produce
it; web app (4b) deferred to its own slice.

- Modules:
  - `request_format.py` (~250 LOC) — `request/v1` codec: `RequestLetter`,
    `serialize_request_letter`, `parse_request_letter`,
    `RequestLetterMalformed`, shared predicates `is_single_line` /
    `has_sentinel_collision` / `is_blank` (one source of truth, both
    the codec guards and `CreateRequestArgs` call them).
  - `vgm_files.py` (new, ~35 LOC) — strictly-bounded VGM file-naming
    module: `REQUEST_LETTER_PREFIX/SUFFIX`, `request_letter_filename`.
  - `cli/create_request.py` — `CreateRequestArgs` extended
    (to/cc/subject/body/questions, `letter_text` dropped);
    `run_create_request` serializes via the codec (signature unchanged).
  - `__main__.py` — `--to/--cc/--subject/--body-file/--questions-file`
    replace `--letter-file`; shared `_read_utf8` for symmetric file errs.
  - `web/request_view.py` — filter repointed to the shared affixes.
- Tests: 17 codec behaviors (B1–B17, 34 tests) + V1–V9 model + F1–F3
  flow + M1–M8 CLI + VF1–VF3 vgm_files + Slice-3 FS tests inverted to
  `.txt`. Full suite green, ruff clean, mypy --strict clean (38 files).
- Smoke: PASSED against test VGM #395357 — `_request_letter_<ISO>.txt`
  uploaded, opened in DATEV UI, `request/v1` format confirmed (headers,
  verbatim body, fragen markers, questions). Writer/reader consistency
  is structural (shared `vgm_files`), not smoke-verified end-to-end.
- Surprises / supersedes:
  - **Supersedes Slice-4 design decision #2**: questions are NOT a
    separate `_request_questions_<ISO>.txt`. They are embedded in the
    single `_request_letter_<ISO>.txt` via the `==BELEGMEISTER== fragen`
    machine-marker. The submit slice's `_response_<ISO>.txt` /
    `beantwortete_fragen_<ISO>.txt` mapping must read questions from the
    codec (`parse_request_letter`), not from a separate file.
  - File extension changed `.md` → `.txt` (Notepad-openable on stock
    Windows; content was always plain text). FS5 filter test inverted.
  - Codec parse hardened against silent-misparse (out-of-order markers,
    injected markers, dup headers) — every structural defect raises
    `RequestLetterMalformed`, never a bare ValueError.
- Open for next slice:
  - **Slice 4b** — SB web form (`sb/app.py` on :8731, templates,
    Add-Question JS, lifespan, port helper) calling the ready 4a core.
  - Client-render of questions at `/r/{token}` is still the Slice-3
    layout (deferred, expected). It will consume `parse_request_letter`.
  - `beantwortete_fragen_<ISO>.txt` naming reserved; goes into
    `vgm_files.py` only when the submit slice actually touches it.

## Slice 4b — SB request-creation web form — PENDING RECONCILIATION, **BLOCKED** (2026-05-19)

Code-complete, all gates green, but **NOT shipped, NOT closed**. This is
a flushed ledger, not the final DONE entry — 4b closes only when the
resolver-perf BLOCKER is fixed AND smoke step 8b's measured not-found
duration is recorded here.

### State

- New `belegmeister.sb.app` (separate FastAPI object from `web.app` so a
  public `/r/` deploy never exposes `/sb`). `GET /sb` form, `POST
  /sb/create` reusing the 4a core (`run_create_request` /
  `CreateRequestArgs`) verbatim — no parallel request logic. Lifespan =
  shared `env_validation` (C1 mirror). Templates Jinja2 autoescape.
- `belegmeister/validation_errors.py` — shared `validation_error_items`
  (single source of truth; CLI `__main__._format_validation_error`
  rewired to it, proven byte-identical by `tests/test_validation_errors.py`).
- Behaviours B1–B15, gates: **sb 26/26, full 165/165**, ruff clean,
  `mypy --strict` 46 files clean.
- New dep: `python-multipart` (FastAPI form parsing; added via `uv add`).

### Behaviour map (B1–B15)

B1 GET form · B2 happy create+copyable link · B3 zero-questions · B4
multi-question order · B5 non-numeric vgm (`FormValidationError`, field)
· B6 unknown number (`VgmNotResolved`, field, "nicht gefunden") · B7
scalar `ValidationError` (field) · B8 question `ValidationError`
co-located at the 0-based row (`_QUESTION_INDEX_RE` = cross-layer pin of
the 4a message) · B9 `UploadFailed`/`InvalidUploadTarget` curated banner
· B10 autoescape every echoed surface + `<script`-count invariant · B11
lifespan fail-fast (C1 mirror) · B12 resolver `httpx.HTTPError`
classified (transient vs 4xx, no false "retry") · B13 local `OSError`
distinct banner · B14 pre-handler `RequestValidationError` → salvaged
re-render @200 · B15 `GET /sb/create` → 303 `/sb`. Invariant: every
friendly re-render is HTTP 200 (B5–B14 uniform).

### Resolver miss-latency — RESOLVED 2026-05-21 (single-line fix, no slice)

Resolver-perf slice REJECTED 2026-05-21 after empirical spike against
live `api.klardaten.com`:

- Klardaten `/documents` endpoint does paginate via `$skip` (revised vs
  initial probe finding) but ignores `$top` and filter params.
- Production resolver hit path: ~0.9 s. Miss path: 44.3 s with default
  `max_pages=50`.
- Persisted-index design (ADR-0001, `.overseer/slice/resolver-perf.md`)
  over-engineered for actual constraint: reducing `max_pages` from 50
  to 3 yields ~3 s worst-case miss without any index infrastructure.
- Trade-off: false-negative on VGM numbers >3000 documents deep in API
  rotation. Acceptable per owner decision pending klardaten support
  response on server-side number lookup.

**Slice 4b status: CLOSED** — miss latency dropped 45 s → ~3 s via
single-line fix in `resolver.py` `max_pages` parameter (50 → 3). The
4b UX mitigations (liveness spinner, "wird in DATEV gesucht …") stay
as defensive UI but are no longer load-bearing.

### Conscious decisions / scope (ledger)

- **Launcher → Slice 4c** (port-bind 8731, port-busy→open existing,
  open browser at `/sb` since 4b has no root route by design). 4b run by
  `uvicorn` by hand; it does NOT enforce the loopback bind — 4c must
  bind `127.0.0.1`; running `--host 0.0.0.0` would expose an
  unauthenticated form.
- **Double-submit:** core dedup out-of-scope (intentionally
  non-idempotent — "each run auditable"; future "re-issue/supersede").
  `lockSubmit` JS disables the button (double-click hygiene) — shipped.
  **PRG deliberately rejected** (would put the magic-link token in a GET
  URL / access log — the Slice-3 hazard).
- **Email-format in `to`/`cc` intentionally unvalidated** (the 4a
  validators only enforce non-blank/single-line). Deliverability is the
  future SMTP send-slice's concern; adding it here = scope creep +
  duplicated logic. Deferred.
- **`InvalidUploadTarget` → banner** (not the `vgm_number` field like
  B6): conscious stage-based split (resolve-stage vs upload-stage),
  ratified by the locked B9 spec. Residual UX tension (both mean "wrong
  number"); routing it to the field for B6-consistency is a future
  refinement.
- **B12 4xx-vs-transient split:** `httpx.HTTPError` is too broad; 4xx
  (esp. 401/403 = credentials/config) gets a non-retry-implying banner,
  `RequestError`/5xx/other gets "nicht erreichbar … später erneut".
- **`_split_errors` questions:** 4a short-circuits at the first bad
  question → one entry today; `dict[int,str]` shape supports more if 4a
  ever collects; a questions error with no parseable index falls back to
  the `field_errors["questions"]` group slot (form.html) — not silent.

### Surprises (process)

- **Pre-handler layer was invisible to unit tests.** Every test posted
  a complete body, so FastAPI's `Form(...)` validation (which runs
  BEFORE the handler body, bypassing all B5–B13 try/except) was never
  exercised — smoke caught raw 422/405 JSON. Fixed as B14/B15.
- **Resolver O(N) latency invisible to unit tests.** `_FakeClient` has a
  trivial doc-set so the scan exhausts instantly; only a timed live
  smoke exposed the ~45s. → the BLOCKER above.
- **Browser-keyboard defects invisible to TestClient:** Enter in a
  question `<input>` submitted the whole form (fixed: delegated keydown
  → add row); a slow scan with a static disabled button looked dead
  (fixed: liveness spinner).
- Test-as-contract cycles (B3, B4, B10, B11) passed with no impl change
  — reported, not faked; B10's initial blanket `"<script>" not in body`
  was a flawed assertion (template has first-party `<script>`) →
  replaced with a first-party count invariant.

### Future open-item (NOT this slice) — production hosting of `/r/`

Deployment/ops slice, after the client loop is functionally complete
(submit-slice). `web.app` (`/r/*`) is localhost-only today; magic links
need a public host. Single-tenant deploy, real domain + TLS,
`MAGIC_LINK_BASE_URL`=that domain, always-on, bind `0.0.0.0` +
`--proxy-headers`. Only code touch: a healthcheck endpoint. Hardest
sub-point: `MAGIC_LINK_SECRET` provisioning — every SB instance AND the
hosted `/r/` must share the identical secret or SB-signed tokens fail
verification (generic 404). Carries Slice-3 token-in-access-log (now ×
proxy). Different slice character (no unit-RED for systemd/TLS; gates =
external-device smoke) — discuss in its Step 0.

### Files (added / changed) — staged, NOT committed (human checkpoint)

- New: `src/belegmeister/sb/{__init__,app}.py`,
  `src/belegmeister/sb/templates/{form,result}.html`,
  `src/belegmeister/validation_errors.py`,
  `tests/sb/{__init__,test_app,test_app_lifespan}.py`,
  `tests/test_validation_errors.py`, `scripts/smoke_test_sb_form.py`.
- Modified: `src/belegmeister/__main__.py` (rewired to shared
  `validation_error_items`, behaviour-preserving), `pyproject.toml` +
  `uv.lock` (`python-multipart`).

Suggested commit message (for the human to run — see below):

```
feat(sb): SB request-creation web form (4b) — CODE COMPLETE, BLOCKED

- belegmeister.sb.app: separate FastAPI app, GET /sb + POST /sb/create
  reusing the 4a core; lifespan C1 mirror; Jinja2 autoescape
- B1-B15: full failure ladder (form-shape / resolve / validate / upload
  / local-FS / pre-handler), each a friendly 200 re-render, never 500
- shared validation_errors.validation_error_items (CLI rewired,
  byte-identical); python-multipart added
- sb 26/26, full 165/165, ruff + mypy --strict clean
- BLOCKED: resolver not-found ~45s (O(all-docs) scan) is not shippable;
  next slice = resolver-perf spike-first. Not closed.
```
