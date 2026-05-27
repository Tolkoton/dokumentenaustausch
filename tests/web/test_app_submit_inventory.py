"""S6 integration-level Hardest-Seam: response doc references stored
filenames (with per-file UUIDs), NOT the original Mandant filenames.

End-to-end through FastAPI TestClient against the **real** upload
orchestrator (NOT the UNIT 2 stub) — this is the test that proves
UNIT 3's loop produces inventory whose `stored_filename` is what the
response doc actually serializes.

Per slice contract Phase 3 Seam 6 wide test design:
- Two Mandant files SHARING the same original name (`scan.pdf` × 2)
  force UUID disambiguation observably (under a naive bug embedding
  originals, the doc would have `"scan.pdf"` twice, indistinguishable).
- Assert both distinct UUIDs are present in the response doc body.
- Negative regex assertion: bare `"scan.pdf"` (NOT preceded by the
  `_attachment_<lid>_<uuid>_` pattern) does NOT appear.

The codec-level S6 (umlaut-filename verbatim preservation) is in
`tests/web/test_response_format.py::test_serializer_embeds_filename_verbatim_with_umlaut`
and is UNIT 1's scope.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from belegmeister.magic_link.token import generate_token
from belegmeister.request_format import RequestLetter, serialize_request_letter
from belegmeister.web.app import app, get_letter_source, get_now, get_secret

SECRET = "y" * 48
NOW = datetime(2026, 5, 27, 12, 0, 0, tzinfo=timezone.utc)
VGM = "3bf17a53-42ca-4a03-9275-213bd1c6b263"
LETTER_ID = "1170198"
DOC_FILE_ID = 1152156

_LETTER = serialize_request_letter(
    RequestLetter(
        to="client@example.com",
        cc="",
        subject="Belege 2026",
        body="Bitte zwei Scans senden.",
        questions=(),
    )
)


class _RecordingBinder:
    """Fake LetterSource that records every `attach_file_to_binder`
    call (binder_guid, file_name, file_bytes) for later inventory
    inspection. Each attach succeeds with monotonically-increasing
    structure-item ids."""

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
        dfid = self._next_id + 1
        self._next_id += 2
        self.attach_calls.append(
            {
                "binder_guid": binder_guid,
                "file_name": file_name,
                "file_bytes": file_bytes,
            }
        )
        item = {
            "id": sid,
            "name": file_name,
            "type": 1,
            "counter": len(self._items) + 1,
            "document_file_id": dfid,
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


def _client(binder: _RecordingBinder) -> TestClient:
    app.dependency_overrides[get_letter_source] = lambda: binder
    app.dependency_overrides[get_secret] = lambda: SECRET
    app.dependency_overrides[get_now] = lambda: NOW
    # NOTE: NOT overriding get_upload_orchestrator — the real orchestrator
    # is what this test exercises.
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(autouse=True)
def _clear_overrides() -> Any:
    yield
    app.dependency_overrides.clear()


def test_response_doc_embeds_stored_not_original_filenames() -> None:
    """S6 wide test: two Mandant files sharing the same original name
    `scan.pdf` force the orchestrator to generate distinct UUID-prefixed
    stored filenames (per slice contract D3). The response doc body
    MUST embed both stored names (with their distinct UUIDs), not the
    bare `scan.pdf` original.

    Bug shape caught: response doc embeds Mandant's original filename
    instead of the D3-stored filename. Under a single-file fixture,
    naive substring assertions like `"scan.pdf" in body` pass either
    way (original is substring of stored). With TWO files sharing
    `scan.pdf`, the naive bug produces `"scan.pdf"` twice
    indistinguishably; correct impl produces two distinct UUID-prefixed
    names.

    Per slice contract anti-pattern: *"original name is substring of
    stored name; substring assertion is contentless."*
    """
    binder = _RecordingBinder()
    client = _client(binder)
    token = _valid_token()

    # Two "scan.pdf" uploads with DIFFERENT content (so a downstream
    # bug that dedupes by content-hash also surfaces — though that's
    # not in scope for this slice).
    files = [
        ("files", ("scan.pdf", b"first scan content", "application/pdf")),
        ("files", ("scan.pdf", b"second scan content", "application/pdf")),
    ]

    r = client.post(
        f"/r/{token}/submit",
        data={"response": "Anbei zwei Scans."},
        files=files,
    )

    assert r.status_code == 200, (
        f"submit failed unexpectedly: status={r.status_code}, body={r.text[:500]}"
    )

    # Find the response doc among the recorded attach calls. Per D3
    # the response doc filename matches `_response_<letter_id>_*.txt`;
    # attachments match `_attachment_<letter_id>_*`. Both go through
    # the same `attach_file_to_binder` seam.
    response_doc_calls = [
        c
        for c in binder.attach_calls
        if str(c["file_name"]).startswith(f"_response_{LETTER_ID}_")
    ]
    attachment_calls = [
        c
        for c in binder.attach_calls
        if str(c["file_name"]).startswith(f"_attachment_{LETTER_ID}_")
    ]
    assert len(response_doc_calls) == 1, (
        f"expected exactly 1 response doc upload, recorded "
        f"{[c['file_name'] for c in binder.attach_calls]}"
    )
    assert len(attachment_calls) == 2, (
        f"expected exactly 2 attachment uploads, recorded "
        f"{[c['file_name'] for c in binder.attach_calls]}"
    )

    # Extract the two distinct UUIDs from the recorded attachment
    # filenames. Per D3 schema: `_attachment_<letter_id>_<8-char-uuid>_<original>`.
    uuid_pattern = re.compile(
        rf"^_attachment_{re.escape(LETTER_ID)}_([0-9a-f]{{8}})_scan\.pdf$"
    )
    uuids: list[str] = []
    for call in attachment_calls:
        match = uuid_pattern.match(str(call["file_name"]))
        assert match is not None, (
            f"attachment filename does not match D3 schema: {call['file_name']}"
        )
        uuids.append(match.group(1))
    assert uuids[0] != uuids[1], (
        f"two same-name uploads got the same UUID prefix: {uuids[0]}"
    )

    # Inspect the response doc body. Both stored filenames (with their
    # distinct UUIDs) MUST appear; the bare original "scan.pdf" alone
    # (not part of an attachment line) MUST NOT.
    response_doc_body = response_doc_calls[0]["file_bytes"].decode("utf-8")

    for uuid in uuids:
        stored_name = f"_attachment_{LETTER_ID}_{uuid}_scan.pdf"
        assert stored_name in response_doc_body, (
            f"stored filename {stored_name!r} missing from response doc body"
        )

    # Negative assertion: bare `scan.pdf` (NOT preceded by the
    # `_attachment_<lid>_<uuid>_` pattern) does NOT appear. This is
    # the load-bearing anti-substring check that catches the
    # "embed original instead of stored" bug.
    bare_original_re = re.compile(
        rf"(?<!_attachment_{re.escape(LETTER_ID)}_[0-9a-f]{{8}}_)scan\.pdf"
    )
    bare_matches = bare_original_re.findall(response_doc_body)
    assert not bare_matches, (
        f"bare 'scan.pdf' (not part of stored name) appears in response doc — "
        f"matched: {bare_matches}; full body:\n{response_doc_body}"
    )
