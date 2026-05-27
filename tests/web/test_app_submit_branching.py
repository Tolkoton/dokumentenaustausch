"""S1 Hardest-Seam: D6 four-branch dispatcher matrix — slice
submit-handler UNIT 2. Exercises the POST handler END-TO-END through
FastAPI TestClient with controllable mocked inventory (per slice
contract: UNIT 2 stubs the upload loop, tests inject inventory via
the `get_upload_orchestrator` dependency override).

Per slice contract Phase 3 Seam 1:

- 4 branches × 3 assertion axes = 12 assertion-axes per matrix run.
- Naive 1-property collapse fails — e.g. if "all failed" is
  incorrectly collapsed with "partial", `response_doc_committed=True`
  for the all-failed case violates the spec.

Three properties per branch:

1. ``response_doc_committed``: pinned regex = ``^_response_<letter_id>_.*\\.txt$``
   over the mock binder's recorded `attach_file_to_binder` calls.
2. ``token_burned``: presence of the response-doc structure-item in the
   mock binder state post-flow (same predicate the production replay
   check uses).
3. ``http_response_class``: "200 + specific banner template identity"
   vs "non-2xx + error template identity" — not pinning specific
   5xx number per slice contract (handler chose 500; test asserts
   "non-2xx" via inequality).

Anti-pattern named in the slice contract: *"per-branch tests that
pass without touching the branch decision."* The matrix detects
collapse by requiring all three properties to match per branch — any
two branches that collapse to the same code path will produce
identical property tuples and contradict the spec for at least one
branch.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from belegmeister.magic_link.token import generate_token
from belegmeister.request_format import RequestLetter, serialize_request_letter
from belegmeister.web.app import (
    app,
    get_letter_source,
    get_now,
    get_secret,
    get_upload_orchestrator,
)
from belegmeister.web.response_format import AttachmentOutcome

SECRET = "z" * 48
NOW = datetime(2026, 5, 27, 10, 30, 0, tzinfo=timezone.utc)
VGM = "3bf17a53-42ca-4a03-9275-213bd1c6b263"
LETTER_ID = "1170198"
DOC_FILE_ID = 1152156

# Pinned regex per slice contract Phase 3 Seam 1: `response_doc_committed`
# precise definition.
_RESPONSE_DOC_NAME_RE = re.compile(rf"^_response_{LETTER_ID}_.*\.txt$")

# Realistic request letter with one question so Q/A pairs surface in
# the response doc (matrix's response_doc_committed assertion is
# blind to the doc's content, but a non-trivial letter exercises the
# whole flow).
_LETTER = serialize_request_letter(
    RequestLetter(
        to="client@example.com",
        cc="",
        subject="Belege 2026",
        body="Sehr geehrte Damen und Herren, bitte Belege senden.",
        questions=("Welche Bank?",),
    )
)


class _StatefulBinder:
    """Fake LetterSource + BinderClient combined: serves the existing
    request letter for the letter-fetch step AND records
    `attach_file_to_binder` calls. After an attach, the new
    structure-item appears in subsequent `list_structure_items` —
    so the test can assert `token_burned` by inspecting state."""

    def __init__(self) -> None:
        self._items: list[dict[str, Any]] = [
            {
                "name": "_request_letter_2026-05-15T080805Z.txt",
                "type": 1,
                "counter": 2,
                "document_file_id": DOC_FILE_ID,
                "id": LETTER_ID,
            }
        ]
        self._next_id = 9000000
        # Recorded calls for the response_doc_committed assertion.
        self.attach_calls: list[dict[str, Any]] = []

    def list_structure_items(self, binder_guid: str) -> list[dict[str, Any]]:
        return list(self._items)

    def download_document_file(self, document_file_id: int) -> bytes:
        if document_file_id == DOC_FILE_ID:
            return _LETTER.encode("utf-8")
        raise AssertionError(f"unexpected download_document_file({document_file_id})")

    def attach_file_to_binder(
        self, *, binder_guid: str, file_name: str, file_bytes: bytes
    ) -> dict[str, Any]:
        sid = str(self._next_id)
        self._next_id += 1
        self.attach_calls.append(
            {
                "binder_guid": binder_guid,
                "file_name": file_name,
                "n_bytes": len(file_bytes),
            }
        )
        item = {
            "id": sid,
            "name": file_name,
            "type": 1,
            "counter": len(self._items) + 1,
            "document_file_id": self._next_id,
        }
        self._items.append(item)
        return item


def _valid_token() -> str:
    return generate_token(
        vgm_id=VGM,
        letter_id=LETTER_ID,
        expires_at=NOW + timedelta(days=3),
        secret=SECRET,
    )


def _succeeded(name: str) -> AttachmentOutcome:
    return AttachmentOutcome(
        original_filename=name,
        stored_filename=f"_attachment_{LETTER_ID}_aaaaaaaa_{name}",
        structure_item_id="8888888",
        document_file_id=7777777,
        status="succeeded",
        failure_reason=None,
        elapsed_s=1.0,
    )


def _failed(name: str) -> AttachmentOutcome:
    return AttachmentOutcome(
        original_filename=name,
        stored_filename=None,
        structure_item_id=None,
        document_file_id=None,
        status="failed",
        failure_reason="klardaten_5xx",
        elapsed_s=0.4,
    )


def _client_with_inventory(
    binder: _StatefulBinder, inventory: tuple[AttachmentOutcome, ...]
) -> TestClient:
    """Set up a TestClient with the upload orchestrator overridden to
    return the given inventory."""

    def fake_orchestrator(
        files: list[Any], letter_id: str, vgm_id: str, letter_source: Any
    ) -> tuple[AttachmentOutcome, ...]:
        return inventory

    app.dependency_overrides[get_letter_source] = lambda: binder
    app.dependency_overrides[get_secret] = lambda: SECRET
    app.dependency_overrides[get_now] = lambda: NOW
    app.dependency_overrides[get_upload_orchestrator] = lambda: fake_orchestrator
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(autouse=True)
def _clear_overrides() -> Any:
    yield
    app.dependency_overrides.clear()


def _multipart_files_for(inventory: tuple[AttachmentOutcome, ...]) -> list[Any]:
    """Build a multipart `files` list matching the inventory's
    cardinality. Per slice contract D7, the empty-submit predicate
    accepts answers-only — so when inventory is empty we still
    submit an answer to satisfy D7. When inventory is non-empty we
    submit one synthetic file per inventory entry so the handler's
    file count matches the mocked orchestrator's perspective.
    """
    return [
        ("files", (f"placeholder_{i}.bin", b"x", "application/octet-stream"))
        for i, _ in enumerate(inventory)
    ]


@pytest.mark.parametrize(
    (
        "inventory",
        "expected_response_doc_committed",
        "expected_status_2xx",
        "expected_template_marker",
    ),
    [
        # Branch 1: answers-only (empty inventory) → commit + full_success page.
        # Mandant submits an answer (no files). Response doc commits;
        # token burns; 200 + full_success banner.
        ((), True, True, "Vielen Dank"),
        # Branch 2: all-files-failed bailout.
        # 1 failed file, 0 succeeded → no commit; no burn; non-2xx error page.
        ((_failed("a.pdf"),), False, False, "Übermittlung fehlgeschlagen"),
        (
            (_failed("a.pdf"), _failed("b.pdf")),
            False,
            False,
            "Übermittlung fehlgeschlagen",
        ),
        # Branch 3: partial success.
        # 1 ok + 1 failed → commit; burn; 200 + partial_success banner.
        ((_succeeded("ok.pdf"), _failed("bad.pdf")), True, True, "Teilweise empfangen"),
        # Branch 4: full success.
        ((_succeeded("a.pdf"),), True, True, "Vielen Dank"),
        ((_succeeded("a.pdf"), _succeeded("b.pdf")), True, True, "Vielen Dank"),
    ],
)
def test_d6_four_branch_matrix(
    inventory: tuple[AttachmentOutcome, ...],
    expected_response_doc_committed: bool,
    expected_status_2xx: bool,
    expected_template_marker: str,
) -> None:
    """S1 Hardest-Seam matrix: 4 branches × 3 properties per branch.

    For each branch, asserts simultaneously:

    1. ``response_doc_committed`` — any `attach_file_to_binder` call
       whose `file_name` matches the response-doc regex.
    2. ``token_burned`` — `_response_<letter_id>_*` structure-item
       present in the mock binder state post-flow.
    3. HTTP response identity — 2xx + banner-text marker (full_success
       or partial_success) vs non-2xx + error-template marker.

    Bug shapes this catches (per slice contract):
    - "always commits response doc" — branch 2 violates property 1.
    - "always burns token" — branch 2 violates property 2.
    - "bailout fires on files_attempted == 0" — branch 1 violates
      property 1 (no commit when one is expected).
    - "partial branch never fires (collapsed with full)" — branch 3
      violates property 3 (wrong banner text marker).

    The fixture submits a non-empty `response` (Anmerkungen) field
    AND a file-per-inventory-entry, so D7's empty-submit predicate is
    satisfied for all branches. Branch 1 (answers-only) gets the
    Anmerkungen-only path because `_multipart_files_for(())` returns
    []; the handler's `len(files) == 0` matches the orchestrator's
    empty inventory.
    """
    binder = _StatefulBinder()
    client = _client_with_inventory(binder, inventory)
    token = _valid_token()
    form_data: dict[str, str] = {
        "response": "Anbei wie gewünscht.",  # Anmerkungen — satisfies D7
        "answer_0": "Sparkasse.",  # one answer for the one-question letter
    }

    r = client.post(
        f"/r/{token}/submit",
        data=form_data,
        files=_multipart_files_for(inventory),
    )

    # Axis 1: response_doc_committed (regex match against recorded calls).
    matching_attach_calls = [
        call
        for call in binder.attach_calls
        if _RESPONSE_DOC_NAME_RE.match(str(call["file_name"]))
    ]
    actual_response_doc_committed = len(matching_attach_calls) >= 1
    assert actual_response_doc_committed is expected_response_doc_committed, (
        f"response_doc_committed axis violated for inventory shape "
        f"(attempted={len(inventory)}, "
        f"succeeded={sum(1 for a in inventory if a.status == 'succeeded')}): "
        f"recorded attach calls = {binder.attach_calls!r}"
    )

    # Axis 2: token_burned — same predicate the production replay
    # check uses. Post-flow binder state must contain a
    # _response_<letter_id>_* item iff the response doc was committed.
    post_state = binder.list_structure_items(VGM)
    response_prefix = f"_response_{LETTER_ID}_"
    actual_token_burned = any(
        isinstance(item.get("name"), str)
        and str(item["name"]).startswith(response_prefix)
        for item in post_state
    )
    assert actual_token_burned is expected_response_doc_committed, (
        f"token_burned axis violated: post-flow binder state = {post_state!r}"
    )

    # Axis 3: HTTP class + template-identity marker.
    is_2xx = 200 <= r.status_code < 300
    assert is_2xx is expected_status_2xx, (
        f"HTTP status class violated: got {r.status_code}, "
        f"expected {'2xx' if expected_status_2xx else 'non-2xx'}"
    )
    assert expected_template_marker in r.text, (
        f"template-identity marker not found: expected "
        f"{expected_template_marker!r} in response body"
    )
