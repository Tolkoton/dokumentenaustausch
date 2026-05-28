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

## Slice 4b — SB request-creation web form (DONE 2026-05-21)

Code-complete, all gates green, shipped. Was briefly BLOCKED on resolver
miss-latency (~45 s O(all-docs) scan); unblocked 2026-05-21 via a
single-line `max_pages` fix (see "Resolver miss-latency — RESOLVED"
below, which records the 44.3 s → ~3 s measurement). Status: CLOSED.

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

## magic-link-ui — CODE COMPLETE 2026-05-26

**Smoke verified:**
- VGM #395357 (Dokumentnummer; resolved GUID via /sb create flow; observed in uvicorn log)
- Question strings: "q1", "q2", "q3" (smoke fixtures; future smokes per artifact use distinctive alpha/beta/gamma to avoid substring collisions)
- Browser: Chrome on Linux
- Desktop viewport: PASS for parsed-letter rendering, indexed inputs, slate-styled submit, view-source absent of To/Cc
- Mobile viewport (375×667 iPhone SE preset, Chrome DevTools): not tested in this session — owner deferred to pre-production smoke per D-4 deployment gating
- Invalid-token branch (one char modified): not tested in this session — covered by test_RT2_invalid_token_404_generic_no_disclosure_structured_log unit-level guard
- Zero-questions case: not tested in this session — covered by test_question_section_hidden_when_no_questions S4 unit-level guard
- New label "Anmerkungen (optional)" renders, browser does not block empty submit
- POST /r/{token}/submit → 404 verified-as-expected per artifact D-4 (live submit blocked until submit-slice ships); GET /r/{token} → 200 with successful resolver chain through Klardaten API (structure-items + document-files calls observed in uvicorn log) — strong signal that frontend is production-ready pending submit handler

**Tests:** 190 baseline → 201 final (+10 magic-link-ui net; +1 chore test_10)
- Added (magic-link-ui, 11 new): test_parsed_subject_renders_in_h1, test_parsed_body_renders_without_wire_markers, test_per_question_inputs_have_distinct_indexed_names, test_per_question_inputs_ordered_with_question_text, test_subject_html_escaped, test_body_html_escaped, test_question_text_html_escaped, test_question_section_hidden_when_no_questions, test_letter_malformed_logs_reason_and_returns_404, test_to_and_cc_not_in_rendered_page, test_response_textarea_is_optional (UNIT 7)
- Deleted (1): test_RT3_xss_letter_text_is_html_escaped — replaced by S3-T1/T2/T3 per D-S3
- Mechanical: RequestView field rename sweep in tests/web/ per Phase 0 C
- Chore (+1): test_overseer_stop test_10 for CONTINUE-injection idempotency

**Surprises / Pre-G4 notes:**
- UNIT 1 discovered artifact test-count baseline (165) was stale; actual baseline 190 (project gained tests between 4b and slice start). Flagged, no functional impact.
- Pre-existing ruff-format drift in .claude/hooks/auto-approve-web.py — flagged at UNIT 1, NOT touched (scope discipline).
- Infrastructure churn during slice: autonomy-clause revert at UNIT 2 + hook contract change at UNIT 5 (paired chore commit covers it). Loop reliability lesson — infrastructure changes do not belong mid-slice.
- UNIT 6 smoke-revealed: textarea label "Ihre Antworten / Kommentare" conflated with per-question answer inputs; renamed to "Anmerkungen".
- UNIT 7 smoke-revealed: response textarea was incorrectly marked required at HTML level; D-P1.2 specified handler-level policy; corrected to optional with visible "(optional)" indicator.
- UNIT 7 devil's-advocate finding (informational, deferred): <input name=files required> retains HTML-level required; D-P1.2 was specified for answer fields and was not extended to files at planning time. Owner decision: defer to submit-slice planning to define file-count policy holistically.

**Token-to-request-instance binding — BLOCKS PRODUCTION /r/ HOSTING:** smoke revealed that creating a new request in the same VGM serves the new letter content under previously-issued tokens. Token currently references VGM identity only, not request-instance identity. Must be resolved before any public /r/ exposure. Needs dedicated slice (or addressed in submit-slice planning where wire/persistence decisions are already on the table).

**Artifact deviations on slice work:** none. All Bucket 1 tests carry planned names and assertions. D-1/D-2/D-E/D-S3/D-S8/D-P1.2/P1.1 implemented per artifact. RT1 wire-contract pin preserved verbatim. Smoke and G4 owner-driven per Phase 4.

**Suggested commits:** see git status — split into feat(web) magic-link-ui and chore(overseer) loop infrastructure.

## token-instance-binding — CODE COMPLETE 2026-05-26 (awaiting owner smoke)

**Smoke pending owner walkthrough** (slice exit-criterion #5 — owner-runnable, ~30 s against dev klardaten):

```bash
uv run python scripts/smoke_token_instance_binding.py [VGM_NUMBER]
```

- Default VGM: 395357 (configurable via positional arg).
- Output: `artifacts/spikes/token-instance-binding-smoke-<DATE>.json` —
  records `smoke_id`, both created `letter_id`s + `structure_item_id`s,
  HTTP response statuses + body lengths, and the four cross-assertion
  booleans. Exit code 0 = all four PASS; 1 = any failed.
- Mutates: two `_request_letter_*.txt` structure-items per run inside
  the target VGM. Cleanup is OUT-of-scope this slice (per slice contract
  "Deferred" section); the JSON output records the created
  `structure_item_id`s so future cleanup can target them precisely. No
  distinctive `_smoke_letter_<UUID>.txt` filename prefix because changing
  it would mean touching production source for the smoke's convenience —
  the per-run UUID smoke_id + JSON breadcrumb is the trade-off.
- The four load-bearing assertions (per slice Seam 3):
  `L1_marker IN /r/T1`, `L2_marker IN /r/T2`,
  `L2_marker NOT IN /r/T1`, `L1_marker NOT IN /r/T2`. The NOT-in
  cross-assertions are the original-bug regression guard.
- HTTP layer: in-process via FastAPI's `TestClient` (real Starlette
  stack against real klardaten), NOT a browser. Per slice Phase 1 the
  smoke is automatable.

**Tests:** 207 baseline → 216 final (+9 token-instance-binding net)

- Pre-slice baseline 207 = 201 (magic-link-ui closure) + 6 (`tests/datev/test_resolver.py` added under commit `8f45faa "GUID to UI mapping fixed"` / ADR-0005 resolver rewrite; the +6 was the test-count "drift" the UNIT 1 audit flagged as soft).
- Added (token-instance-binding, 9 new):
  - **UNIT 1 (5)**: `test_TV5_payload_missing_letter_id_raises`,
    `test_TV5_payload_letter_id_wrong_type_raises`,
    `test_TV5_payload_letter_id_empty_string_raises`,
    `test_old_vgm_only_token_rejects_as_malformed_under_new_schema`
    (`tests/magic_link/test_token.py`),
    `test_mint_threads_upload_result_id_into_token_letter_id`
    (`tests/cli/test_create_request_flow.py` — Seam-2 round-trip).
  - **UNIT 2 (4)**: `test_find_letter_by_id_selects_target_in_multi_letter_binder` (Seam-1),
    `test_letter_id_not_in_binder_emits_distinct_log_reason` (Seam-5a),
    `test_empty_binder_still_emits_letter_missing` (Seam-5b)
    (all `tests/web/test_request_view.py`);
    `test_FS6_id_not_in_letters_raises_letter_id_not_in_binder`
    (`tests/web/test_find_letter_by_id.py` — unit-level Seam-5).
- Migrated (7, no count change): `tests/web/test_pick_newest_letter.py` →
  `tests/web/test_find_letter_by_id.py` via `git mv` (history
  preserved). FS1 rewritten from "newest-by-name picks newest" to
  "id-match picks target NOT newest" (unit-level counterpart to
  Seam-1). FS2–FS5 preserved verbatim with id-match assertion adapter
  (filter-edge coverage — `.md` legacy letter exclusion — intact).
- Mechanical (no count change):
  `test_TV5_payload_exp_wrong_type_raises` extended with `letter_id`
  field so the decode order (vgm_id → letter_id → exp) reaches the
  `exp` check; `LETTER_ID` constants aligned in
  `tests/web/test_request_view.py` + `tests/web/test_app_route.py`
  with default fixture ids so RV1 / RT1 happy paths remain green
  under id-match.
- Disappearance-or-explain on `_pick_newest_letter`: deleted from
  `src/belegmeister/web/request_view.py`; replaced by
  `_find_letter_by_id`. Dedicated test file renamed via `git mv`; no
  test deletion. UNIT 2 audit verdict explicitly recorded the
  disposition.

**Wire-format change — no backwards-compat:** the pre-slice
`{vgm_id, exp}`-only token payload is no longer honored. Per planning
artifact + the prior magic-link-ui section's "BLOCKS PRODUCTION /r/
HOSTING" finding, no production tokens existed (no public `/r/`
host). An explicitly-forged old-format token is rejected as
`InvalidTokenReason.MALFORMED` with "letter_id" in `exc.value.detail`.
`test_old_vgm_only_token_rejects_as_malformed_under_new_schema`
embodies this decision and locks it.

**New `log_reason` taxonomy member:** `letter_id_not_in_binder` added
to `RequestLinkInvalid` canonical taxonomy in
`src/belegmeister/web/request_view.py`. Distinguishes "binder has
letters but none with matching id" (Mandant stale link / letter
deleted server-side after mint) from `letter_missing` (no letters at
all) and `vgm_not_found` (VGM 404). Per slice decision D2 the
distinction is preserved for operational observability — collapsing
the taxonomy is irreversible (once merged, on-call cannot
reverse-engineer which 404s were which class). Three Seam-5 tests
pin the discriminator.

**Surprises / Pre-G4 notes:**

- **Hook fix shipped mid-slice as out-of-slice infrastructure work.**
  Investigation during UNIT 1 → UNIT 2 transition revealed that
  `stop_hook_active`-based "Guard 1" in `.claude/hooks/overseer_stop.py`
  short-circuited BEFORE the per-branch SHA idempotency checks on
  every hook-initiated turn, making both the audit-request and
  PASS→CONTINUE injection branches unreachable in the autonomous
  loop. Empirical proof via synthetic-envelope tests. Fix landed as
  commit `328052f "fix loop x32"` (along with planning artifact,
  spike artifacts, ADR-0005 renumber). First audit through the
  corrected loop fired on UNIT 1 PASS; CONTINUE injection on UNIT 2
  → UNIT 3 transition fired correctly. Empirical production
  validation. Out-of-slice followup: `tests/test_overseer_stop.py`
  `test_2` rewritten to assert the new contract (was: `test_2_stop_hook_active_short_circuits` pinning the broken
  contract; now: `test_2_stop_hook_active_does_not_preempt_named_branches`).
  The test rewrite is on disk but NOT in the hook-fix commit —
  owner choice whether to fold into this slice's commit or run a
  separate `chore(hook)` followup.
- **`UploadResult.success`/`document_id` invariant not type-encoded.**
  `src/belegmeister/cli/create_request.py` threads
  `result.document_id` into `generate_token(letter_id=...)` with an
  explicit `if result.document_id is None: raise UploadFailed(...)`
  narrowing on the "should-never-happen" branch (mypy strict cannot
  infer the invariant from a boolean). Consistent with the existing
  `UploadFailed` pattern in the module. Tightening the dataclass to
  encode the invariant (e.g., split into `UploadOK(document_id: str)`
  and `UploadErr(error: str)`) is out-of-slice — deferred.
- **`tests/web/test_app_route.py` LETTER_ID alignment.** Folded into
  UNIT 2 mechanically (planning-artifact UNIT 2 file list was
  incomplete — `test_app_route.py` calls `generate_token` and needed
  the same LETTER_ID alignment as `test_request_view.py` to keep RT1
  happy path green). Same fold-in pattern as UNIT 1's tests/web/*
  signature propagation. Pre-disclosed at each unit's start; recorded
  in both UNITs' OVERSEER_PASS audit entries.
- **Test count "drift" between magic-link-ui closure and slice start.**
  UNIT 1 audit flagged "+6 chore-drift" as soft language under
  overseer check #6. UNIT 3 enumerated: the +6 was
  `tests/datev/test_resolver.py` added under commit `8f45faa "GUID to
  UI mapping fixed"` (ADR-0005 resolver rewrite). Soft observation
  resolved.

**Files (added / changed) — staged, NOT committed (human checkpoint)**

- New: `scripts/smoke_token_instance_binding.py`,
  `tests/web/test_find_letter_by_id.py` (renamed via `git mv` from
  `tests/web/test_pick_newest_letter.py`).
- Modified (src): `src/belegmeister/magic_link/token.py`,
  `src/belegmeister/cli/create_request.py`,
  `src/belegmeister/web/request_view.py`.
- Modified (tests): `tests/magic_link/test_token.py`,
  `tests/cli/test_create_request_flow.py`,
  `tests/web/test_request_view.py`,
  `tests/web/test_app_route.py`.
- Deleted (via `git mv`): `tests/web/test_pick_newest_letter.py`.
- Modified (out-of-slice followup, owner choice — not auto-staged
  with the slice): `tests/test_overseer_stop.py` (`test_2` rewrite
  to match the new hook contract).

**Artifact deviations on slice work:** none material.
`_smoke_letter_<UUID>.txt` distinctive filename prefix (suggested in
the slice contract's pollution-mitigation note) was NOT used — the
production `_request_letter_*.txt` naming via `run_create_request`
was kept to avoid touching production source for smoke convenience.
Per-run `smoke_id` UUID + recorded `structure_item_id`s in the smoke
JSON serve as the cleanup breadcrumb. The trade-off favors
smoke-mirrors-production over filename-grepability. Recorded in the
smoke script's docstring.

**Suggested commit message (for the human to run — see file list above):**

```
feat(token): bind magic-link tokens to specific letter (token-instance-binding)

Token payload becomes {vgm_id, letter_id, exp}; read path uses
list+find-by-id selection (not newest-by-name), so two requests in
the same VGM are deterministically distinguished. Fixes the
magic-link-ui smoke bug ("new request in same VGM serves new letter
under old tokens") by construction.

- UNIT 1: TokenPayload + generate_token gain letter_id; mint side
  threads UploadResult.document_id; old {vgm_id, exp}-only tokens
  rejected as MALFORMED (no production tokens to migrate per
  PROGRESS.md magic-link-ui section).
- UNIT 2: _pick_newest_letter → _find_letter_by_id (id-match, not
  heuristic); new log_reason "letter_id_not_in_binder" distinguishes
  Mandant-stale-link from empty-VGM and VGM-404 cases (slice D2
  observability — collapsing the taxonomy is irreversible).
- UNIT 3: scripts/smoke_token_instance_binding.py exercises the
  full mint → /r/<token> loop with cross-assertions (NOT-in checks
  catch the original magic-link-ui smoke bug by construction).

Tests: 207 → 216 (+9 slice net). test_pick_newest_letter.py renamed
to test_find_letter_by_id.py via git mv (history preserved).

Slice contract: .overseer/slice/token-instance-binding.md
Smoke awaiting owner walkthrough; output target:
artifacts/spikes/token-instance-binding-smoke-<DATE>.json
```

## submit-handler — CODE COMPLETE 2026-05-27 (awaiting owner smoke)

**Smoke pending owner walkthrough** (slice exit-criterion #8 —
owner-runnable, ~30 s against dev klardaten):

```bash
uv run python scripts/smoke_submit_handler.py [VGM_NUMBER]
```

- Default VGM: 395357 (configurable via positional arg).
- Output: `artifacts/spikes/submit-handler-smoke-<DATE>.json` — records
  per-sub-scenario cross-assertion booleans + the `overall_pass` flag.
  Exit code 0 = all three sub-scenarios PASS; 1 = any failed.
- Mutates: 2 request letters (via `run_create_request`) + 1 response
  doc + 2 attachment files (Sub-A) + 1 response doc (Sub-C) = 7 new
  structure-items per run inside the target VGM. Sub-B adds nothing
  (replay rejection short-circuits before any upload). Cleanup is
  OUT-of-scope this slice (per ADR-0007 no-DELETE; manual DATEV-UO
  only). Distinctive Mandant filenames
  `_smoke_attachment_<smoke_id>_<i>.pdf` make grep-cleanup trivial; the
  JSON output records all created `structure_item_id`s for precise
  targeting.
- The three sub-scenarios (per slice contract Phase 4):
  - **Sub-A (full_success with files)**: mint L1 → POST 2 synthetic
    PDF blobs + answer + Anmerkungen → assert HTTP 200 + "Vielen Dank"
    template marker + response doc exists with both attachment UUIDs
    in `==ATTACHMENTS==` section + binder count delta = 3.
  - **Sub-B (replay_rejected)**: re-POST same token → assert HTTP 200
    + "Bereits eingereicht" template marker + binder count unchanged
    from end of Sub-A.
  - **Sub-C (full_success answers-only)**: mint L2 → POST 0 files +
    non-empty answer → assert HTTP 200 + "Vielen Dank" + response doc
    exists with EMPTY `==ATTACHMENTS==` section + binder count delta = 1.
- HTTP layer: in-process via FastAPI's `TestClient` (real Starlette
  stack against real klardaten), NOT a browser. Per slice Phase 4 the
  smoke is automatable.
- Sub-D (partial_success) and Sub-E (all-files-failed) deferred to S1
  unit-test coverage only — deterministically inducing klardaten-side
  per-file rejection requires gateway-version-specific malformed
  payloads. S1 matrix mock-drives all 4 branches.

**Tests:** 216 baseline (token-instance-binding closure) → **254** final
(+38 submit-handler net across 4 UNITs)

- **UNIT 1** (+6 = 222): wire-format anchor + S4 (`_in_answer`,
  `_in_anmerkungen`, `_in_filename`, `_preserves_near_miss_content_verbatim`)
  + S6 codec-level (`test_serializer_embeds_filename_verbatim_with_umlaut`).
  All in `tests/web/test_response_format.py` (new).
- **UNIT 2** (+20 = 242): 4 D7 predicate cases + 3 in-binder replay
  check cases + 6 banner-state derivation parametrized cases (all in
  `tests/web/test_app_submit.py`, new); 6 S1 four-branch matrix
  parametrized cases × 3 assertion axes (`tests/web/test_app_submit_branching.py`,
  new); 1 lockSubmit pin (`test_get_form_renders_lock_submit_js` in
  `tests/web/test_app_route.py`, added adjacent to existing :125
  form-action pin).
- **UNIT 3** (+12 = 254): 11 S2 `failure_reason_from_klardaten_outcome`
  parametrized cases (added to `tests/web/test_response_format.py`);
  1 S6 integration test (`test_response_doc_embeds_stored_not_original_filenames`
  in `tests/web/test_app_submit_inventory.py`, new — two-files-same-original
  fixture forcing UUID disambiguation observability).
- **UNIT 4** (+0 = 254): smoke is owner-runnable, NOT pytest-covered.

**Wire-format additions:**
- New `response/v1` codec via `==BELEGMEISTER== response/v1` header +
  bare `==ANTWORTEN==` / `==ANMERKUNGEN==` / `==ATTACHMENTS==` /
  `==FAILED_ATTACHMENTS==` section markers + `==BELEGMEISTER== end`
  terminator. Mirrors 4a's header pattern; section markers are bare
  per the slice contract S4 fixture wording. Sentinel-collision
  predicate (`has_sentinel_collision`) was REFACTORED in
  `belegmeister.request_format` to accept an optional
  `sentinel_prefixes` tuple (default preserves 4a behavior); response
  codec calls with the full 5-marker tuple (`==BELEGMEISTER==` +
  4 bare section markers). Per CLAUDE.md "Single source of truth for
  cross-layer logic" + MEMORY[feedback_cross_layer_validation_extract]:
  ONE predicate, both layers call it, no copy-paste.

**New error class:** `RequestSubmitFailed` (in `web/app.py`, distinct
from existing GET-side `RequestLinkInvalid`) with five `log_reason`
values per ADR-0007 + slice contract D4:
`upload_failed_all_files` / `upload_failed_response_doc` /
`replay_rejected` / `empty_submit` / `multipart_parse_error`.

**Protocol widen:** `LetterSource` (in `web/request_view.py`) gained
`attach_file_to_binder` as a third method so the POST handler can
commit the response doc via the same injected client it uses for
reads. The real `KlardatenClient` already satisfies; 3 GET-side test
fakes gained raise-on-call attach stubs (catches stray invocations
from a refactor regression).

**ADRs ratified mid-planning:**
- [ADR-0006](docs/adr/0006-binder-as-state-store-for-replay-policy.md)
  — in-binder presence of `_response_<letter_id>_*` is the
  single-use replay marker. Zero new infrastructure; recovery
  discoverable from DATEV-UO; TOCTOU window accepted as residual risk.
- [ADR-0007](docs/adr/0007-best-effort-multi-file-upload-no-rollback.md)
  — driven by Phase-0 premise A9 falsification (klardaten gateway has
  NO DELETE proxy; every DELETE returns 404 empty body). Original
  all-or-nothing design unimplementable; falls back to best-effort
  continue-past-failures with 4-branch D6 state machine.

**Hardest-Seam coverage** (slice contract Phase 3):
- **S1** (D6 four-branch dispatcher matrix): 6 parametrized cases × 3
  assertion axes = 18 assertion-axes. Tests the full POST handler
  end-to-end through `TestClient` with `_StatefulBinder` (records
  `attach_file_to_binder` calls) + `get_upload_orchestrator`
  overridden to inject controllable inventory. Mental-mutation-tested
  for all 4 bug shapes named in slice contract: always-commits,
  always-burns, bailout-on-empty, partial-collapses-into-full. All
  caught.
- **S4** (codec sentinel-collision): 3 positive + 1 negative
  (assertion-b form: no-raise AND verbatim content preserved).
- **S6** (response doc references stored filenames, not originals):
  codec-level umlaut-verbatim test + integration-level
  two-files-same-original fixture forcing observable UUID
  disambiguation.

**Surprises / mid-slice findings:**

- **A9 falsified pre-Phase-3 (precise resolver-perf precedent).**
  Original Phase-2 D6 picked all-or-nothing rollback. Phase-0 A9 spike
  script (`scripts/probe_klardaten_delete_semantics_2026-05-26.py`)
  caught the falsification at 10 min effort — every DELETE returned
  404 with empty body, file persisted post-DELETE. Cascade through
  D6 / D8 / D4 / D5 ratified WITHIN Phase 2 rather than post-Phase 3.
  Exact MEMORY[feedback_verify_premise_before_design] application.

- **A5 (klardaten size envelope) verified to 200 MB.** Spike script
  (`scripts/probe_klardaten_size_envelope_2026-05-26.py`) confirmed
  25/50/100/200 MB all 200 OK; linear ~4 MB/s sustained throughput.
  Above 200 MB untested by design (stop-on-first-failure with no
  failures). `max_confirmed_mb=200` in
  `artifacts/spikes/klardaten-size-envelope-2026-05-26.json`.

- **A4 (SB notification path) CONFIRMED via colleague-eyeball** — no
  notification mechanism; SB sees Mandant uploads via manual DATEV-UO
  inspection. Caveat: not owner-direct observation. Banner copy
  explicitly bans "SB has been notified" claim per ADR-0007.

- **Starlette vs FastAPI UploadFile subclass mismatch caught at
  UNIT 3 S6 integration.** UNIT 2 wrote `_collect_upload_files` with
  `isinstance(item, fastapi.UploadFile)`. `request.form()` returns
  the Starlette PARENT class (`fastapi.UploadFile` is a subclass), so
  the isinstance check silently dropped every uploaded file. UNIT 2's
  S1 matrix never exercised this codepath (orchestrator was
  overridden to bypass file collection). UNIT 3's S6 integration test
  was the first to use the REAL orchestrator with REAL multipart
  files; the isinstance check silently dropped everything → orchestrator
  returned empty inventory → branch-1 (answers-only) fired → 1
  response doc attached instead of expected 3 structure-items. Two
  ~10-line diagnostic scripts (cleaned up) confirmed
  `fastapi.UploadFile is not starlette.datastructures.UploadFile` —
  fixed by switching the import to `starlette.datastructures.UploadFile`
  consistently. Exactly the "test-as-contract pass with broken impl"
  the S6 wide-fixture exists to surface.

- **TDD discipline gap in UNIT 2 (flagged in audit).** UNIT 2 was
  written code-first / tests-after / batch-verify rather than
  per-seam RED→GREEN. UNIT 3 corrected: S2 RED captured at
  `ImportError`; S6 integration RED captured at `NotImplementedError`
  from the stub orchestrator; both GREEN after impl. No fabricated
  RED claims in either unit's close-out.

- **LetterSource Protocol widen** with `attach_file_to_binder` (1
  method added). Pre-disclosed in UNIT 2 close-out; ratified by
  overseer audit as locally-optimal-not-ADR-worthy (small Protocol
  extension; alternatives explicitly considered; behavior-preserving
  for existing GET tests via raise-on-call stubs on 3 fakes).

**Premise verification artifacts:**

- `artifacts/spikes/submit-letter-discovery-2026-05-26.md` — A1/A3
  multi-letter binder discovery (informed token-instance-binding;
  carry-forward).
- `artifacts/spikes/submit-sb-discovery-2026-05-26.md` — A4 CONFIRMED.
- `artifacts/spikes/submit-multi-file-upload-2026-05-26.json` — A1
  multi-file upload happy path.
- `artifacts/spikes/klardaten-size-envelope-2026-05-26.json` — A5
  verified to 200 MB.
- `artifacts/spikes/klardaten-delete-semantics-2026-05-26.json` —
  **A9 FALSIFIED**; `supports_all_or_nothing_rollback=false`.

**Files (added / changed) — staged, NOT committed (human checkpoint)**

- New (src):
  `src/belegmeister/web/response_format.py`,
  `src/belegmeister/web/templates/submit_confirmation.html`,
  `src/belegmeister/web/templates/submit_error.html`.
- Modified (src):
  `src/belegmeister/web/app.py` (POST handler + dispatcher + predicate
  + replay check + RequestSubmitFailed + real upload orchestrator),
  `src/belegmeister/web/request_view.py` (LetterSource Protocol widen),
  `src/belegmeister/web/templates/request.html` (lockSubmit JS),
  `src/belegmeister/request_format.py` (has_sentinel_collision refactor:
  optional `sentinel_prefixes` tuple parameter; default preserves 4a).
- New (tests):
  `tests/web/test_response_format.py`,
  `tests/web/test_app_submit.py`,
  `tests/web/test_app_submit_branching.py`,
  `tests/web/test_app_submit_inventory.py`.
- Modified (tests):
  `tests/web/test_app_route.py` (lockSubmit pin),
  `tests/web/test_request_view.py` (LetterSource fake gain attach stub).
- New (scripts / artifacts):
  `scripts/probe_klardaten_size_envelope_2026-05-26.py` (A5 spike),
  `scripts/probe_klardaten_delete_semantics_2026-05-26.py` (A9 spike),
  `scripts/smoke_submit_handler.py` (slice exit-criterion #8 smoke).
- New (docs):
  `docs/adr/0006-binder-as-state-store-for-replay-policy.md` (Accepted),
  `docs/adr/0007-best-effort-multi-file-upload-no-rollback.md` (Accepted).

**Suggested commit message (for the human to run — see file list above):**

```
feat(web): POST /r/<token>/submit — multi-file submit handler (submit-handler)

Mandant POSTs answers + Anmerkungen + N files via the magic link;
handler verifies token, checks in-binder replay marker, validates D7
empty-submit predicate, runs continue-past-failures upload loop,
dispatches D6 four-branch outcome (full_success / partial_success /
all_failed_bailout / answers_only_full_success), serializes a
response_format.py codec'd response doc, uploads it as the burn
marker, renders confirmation with one of three banner states.

- UNIT 1: response_format.py codec (==BELEGMEISTER== response/v1
  + 4 bare section markers); sentinel-collision predicate refactored
  in request_format.py to accept marker tuple (default preserves 4a);
  S4 (3 + 1 negative) + S6 codec-level (umlaut verbatim).
- UNIT 2: POST handler skeleton + D7 server-side predicate +
  D2 in-binder replay + D6 four-branch dispatcher (stubbed loop) +
  3 banner states (confirmation + error templates) +
  RequestSubmitFailed exception (5 log_reasons) + lockSubmit JS +
  S1 matrix (4 branches × 3 axes) + LetterSource Protocol widen.
- UNIT 3: real continue-past-failures upload loop +
  failure_reason_from_klardaten_outcome categorizer (S2) +
  S6 integration two-files-same-original UUID disambiguation +
  Starlette vs FastAPI UploadFile subclass-mismatch fix.
- UNIT 4: scripts/smoke_submit_handler.py owner-runnable
  Sub-A/B/C against real klardaten.

ADRs: ADR-0006 (binder-as-state-store for replay) +
ADR-0007 (best-effort multi-file, no rollback — A9 falsified
klardaten DELETE). Phase 0 spikes (size-envelope + delete-semantics)
shipped alongside; A4/A5/A9 evidence in artifacts/spikes/.

Tests: 216 → 254 (+38 slice net across UNITs 1-3; UNIT 4 smoke is
owner-runnable, not pytest-covered).

Slice contract: .overseer/slice/submit-handler.md
Smoke awaiting owner walkthrough; output target:
artifacts/spikes/submit-handler-smoke-<DATE>.json
```
