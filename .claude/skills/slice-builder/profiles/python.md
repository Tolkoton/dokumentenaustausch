# Python profile — slice-builder

Concrete idioms for a **Python** slice. Apply wherever the core says *"per your language profile."*

**Test runner.** `pytest`. Show `pytest` output at every RED / GREEN / REFACTOR transition. Skeleton "it imports" check: `pytest --collect-only` must succeed.

**Type checker / strictness.** `mypy --strict` clean. No `Any`, no `# type: ignore`. Full type hints on every signature.

**Value / data shapes.**
- **Pydantic v2 `BaseModel`** → cross-boundary data (HTTP request/response bodies, external API DTOs, queue messages). Parse external/untrusted data into a model at the edge; pass typed objects inward.
- **`@dataclass(frozen=True)`** → internal value objects / slice-local result types (`UploadResult`, `TokenIssued`).
- If the project has a different convention, follow it.

**Skeleton form.** Signature with `raise NotImplementedError("slice in progress")`; named value objects with fields + types; a module-level docstring stating what the module does and what it explicitly does NOT (echoes Step 0).

**Paranoid-SRP — concrete example.**
NOT this:
```python
def upload_to_folder(file_path, folder_id, client) -> UploadResult:
    if not file_path.exists(): return UploadResult(False, error="missing")
    if file_path.stat().st_size > MAX: return UploadResult(False, error="too big")
    token = client.authenticate()
    resp = client.post(...)
    if resp.status != 200: return UploadResult(False, error=resp.text)
    return UploadResult(True, document_id=resp.json()["id"])
```
THIS:
```python
def upload_to_folder(file_path, folder_id, client) -> UploadResult:
    """Flow: validate → upload → map response."""
    if (err := _validate_file(file_path)) is not None:
        return UploadResult(success=False, error=err)
    raw = _do_upload(file_path, folder_id, client)
    return _map_response(raw)

def _validate_file(p: Path) -> str | None: ...
def _do_upload(p: Path, fid: str, c: KlardatenClient) -> RawResponse: ...
def _map_response(r: RawResponse) -> UploadResult: ...
```
Each helper has one reason to change; the flow's one reason is orchestration order.

**Test style.** Tests are `pytest` functions, one per behavior from the core's rule-6 list, named for the behavior. Integration-default against the test/sandbox endpoint; add a fake-dependency unit test only per the core's test-scope rule (non-trivial logic above the call, or a slow >2 s call).

**Smoke convention.** `scripts/smoke_test_<slice>.py` that loads real creds from `.env`, builds real inputs, calls the slice with its real DI dependencies, prints the result, and prints an EXPLICIT instruction — e.g. `Open https://duo.datev.de/folder/X, look for belegmeister_smoke_<ts>.txt. Reply DONE or FAIL.` Run: `python scripts/smoke_test_<slice>.py`.
