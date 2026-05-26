"""Flow tests for `resolve_request_view` with an in-memory fake
LetterSource (the KlardatenClient subset this needs).

The fake serves a structure-items list and file bytes; tests assert the
resolved RequestView or the generic RequestLinkInvalid + its log_reason
(never leaked to the client, but checked here for the logging contract).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from belegmeister.magic_link.token import generate_token
from belegmeister.request_format import RequestLetter, serialize_request_letter
from belegmeister.web.request_view import (
    RequestLinkInvalid,
    RequestView,
    resolve_request_view,
)

SECRET = "w" * 48
NOW = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)
VGM = "3bf17a53-42ca-4a03-9275-213bd1c6b263"

# Wire-format `request/v1` payload. After the Step 0 refactor,
# `resolve_request_view` parses what `download_document_file` returns,
# so the fixture must be a serializable letter rather than plain text.
_LETTER_BODY = "Sehr geehrte Damen und Herren, bitte Belege 2026."
_LETTER_OBJ = RequestLetter(
    to="client@example.com",
    cc="",
    subject="Belege 2026",
    body=_LETTER_BODY,
    questions=(),
)
_LETTER_BYTES = serialize_request_letter(_LETTER_OBJ).encode("utf-8")


class _FakeLetterSource:
    def __init__(
        self,
        *,
        children: list[dict[str, Any]] | None = None,
        files: dict[int, bytes] | None = None,
        list_error: Exception | None = None,
        download_error: Exception | None = None,
    ) -> None:
        self._children = (
            children
            if children is not None
            else [
                {
                    "name": "_request_letter_2026-05-15T080805Z.txt",
                    "counter": 2,
                    "type": 1,
                    "parent_counter": 0,
                    "document_file_id": 1152156,
                    "size": len(_LETTER_BYTES),
                    "id": "1170198",
                }
            ]
        )
        self._files = files if files is not None else {1152156: _LETTER_BYTES}
        self._list_error = list_error
        self._download_error = download_error
        self.list_calls: list[str] = []
        self.download_calls: list[int] = []

    def list_structure_items(self, binder_guid: str) -> list[dict[str, Any]]:
        self.list_calls.append(binder_guid)
        if self._list_error is not None:
            raise self._list_error
        return self._children

    def download_document_file(self, document_file_id: int) -> bytes:
        self.download_calls.append(document_file_id)
        if self._download_error is not None:
            raise self._download_error
        return self._files[document_file_id]


def _token(*, vgm: str = VGM, exp_delta: timedelta = timedelta(days=3)) -> str:
    return generate_token(vgm_id=vgm, expires_at=NOW + exp_delta, secret=SECRET)


def test_RV1_valid_token_single_letter_returns_request_view() -> None:
    src = _FakeLetterSource()

    view = resolve_request_view(_token(), letter_source=src, secret=SECRET, now=NOW)

    assert isinstance(view, RequestView)
    assert view.vgm_id == VGM
    assert view.letter_filename == "_request_letter_2026-05-15T080805Z.txt"
    assert view.letter == _LETTER_OBJ
    assert view.letter.body == _LETTER_BODY
    assert src.list_calls == [VGM]
    assert src.download_calls == [1152156]


def test_RV2_bad_signature_raises_token_bad_signature() -> None:
    """Forged signature → distinct log_reason. A spike of these in the
    server log is a tamper signal (someone forging tokens). Client still
    sees a generic 404 — no disclosure."""
    src = _FakeLetterSource()
    forged = generate_token(
        vgm_id=VGM, expires_at=NOW + timedelta(days=3), secret="DIFFERENT" * 6
    )

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(forged, letter_source=src, secret=SECRET, now=NOW)

    assert exc.value.log_reason == "token_bad_signature"
    assert src.list_calls == [], "must not touch DATEV on a bad token"


def test_RV2_malformed_token_raises_token_malformed() -> None:
    """Structurally broken token → distinct log_reason. A spike of these
    is a benign signal (email truncation / copy-paste), not an attack."""
    src = _FakeLetterSource()

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(
            "not-a-valid-token", letter_source=src, secret=SECRET, now=NOW
        )

    assert exc.value.log_reason == "token_malformed"
    assert src.list_calls == []


def test_RV3_expired_token_raises_token_expired() -> None:
    """Real token, real verify_token, expiry in the past. Pins the
    cross-module contract that an expired token maps to token_expired.
    Coupling is now typed (InvalidTokenReason.EXPIRED identity), not a
    string-match — a wording change can no longer silently degrade it."""
    src = _FakeLetterSource()
    expired = generate_token(
        vgm_id=VGM, expires_at=NOW - timedelta(seconds=1), secret=SECRET
    )

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(expired, letter_source=src, secret=SECRET, now=NOW)

    assert exc.value.log_reason == "token_expired"
    assert src.list_calls == []


def _http_status_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://api.klardaten.com/x")
    resp = httpx.Response(code, request=req)
    return httpx.HTTPStatusError(f"HTTP {code}", request=req, response=resp)


def test_RV4_listing_404_raises_vgm_not_found() -> None:
    src = _FakeLetterSource(list_error=_http_status_error(404))

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(_token(), letter_source=src, secret=SECRET, now=NOW)

    assert exc.value.log_reason == "vgm_not_found"
    assert exc.value.log_context.get("vgm_id") == VGM
    assert src.list_calls == [VGM]  # dispatched with the token's vgm_id


def test_RV4_listing_503_raises_datev_error_not_vgm_not_found() -> None:
    """A DATEV outage must NOT be logged as 'SB typed a bad id'. Different
    operational response (page on-call vs. tell the SB)."""
    src = _FakeLetterSource(list_error=_http_status_error(503))

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(_token(), letter_source=src, secret=SECRET, now=NOW)

    assert exc.value.log_reason == "datev_error"
    assert exc.value.log_context.get("status") == 503


def test_RV4_listing_timeout_raises_datev_error() -> None:
    src = _FakeLetterSource(list_error=httpx.ConnectTimeout("timed out"))

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(_token(), letter_source=src, secret=SECRET, now=NOW)

    assert exc.value.log_reason == "datev_error"


def test_RV5a_download_http_error_raises_download_failed() -> None:
    src = _FakeLetterSource(download_error=_http_status_error(503))

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(_token(), letter_source=src, secret=SECRET, now=NOW)

    assert exc.value.log_reason == "download_failed"
    assert exc.value.log_context.get("vgm_id") == VGM


def test_RV5a_download_timeout_raises_download_failed() -> None:
    src = _FakeLetterSource(download_error=httpx.ReadTimeout("slow"))

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(_token(), letter_source=src, secret=SECRET, now=NOW)

    assert exc.value.log_reason == "download_failed"


def test_RV5a_non_httpx_download_error_propagates_as_bug() -> None:
    """A non-httpx exception from the client is a bug, not a download
    failure — it must propagate with its traceback, not be laundered
    into a generic RequestLinkInvalid."""
    src = _FakeLetterSource(download_error=RuntimeError("client bug"))

    with pytest.raises(RuntimeError, match="client bug"):
        resolve_request_view(_token(), letter_source=src, secret=SECRET, now=NOW)


def test_RV5b_non_utf8_letter_raises_letter_not_utf8() -> None:
    """Letter bytes manually replaced / corrupted to invalid UTF-8 in
    DATEV → content signal, distinct from a transport failure."""
    bad = b"\xff\xfe\x00\x01 not utf-8"
    src = _FakeLetterSource(files={1152156: bad})

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(_token(), letter_source=src, secret=SECRET, now=NOW)

    assert exc.value.log_reason == "letter_not_utf8"
    assert exc.value.log_context.get("vgm_id") == VGM
