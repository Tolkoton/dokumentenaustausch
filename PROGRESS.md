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
