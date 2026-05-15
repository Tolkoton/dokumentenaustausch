"""Route tests for GET /r/{token} via FastAPI TestClient.

The route is humble glue. Deps (letter source, secret, now) are FastAPI
dependencies overridden here so no env / real DATEV is touched.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from belegmeister.magic_link.token import generate_token
from belegmeister.web.app import app, get_letter_source, get_now, get_secret

SECRET = "w" * 48
NOW = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)
VGM = "3bf17a53-42ca-4a03-9275-213bd1c6b263"
LETTER = "Sehr geehrte Damen und Herren,\nbitte Belege 2026 senden."


class _FakeSource:
    def __init__(
        self,
        *,
        children: list[dict[str, Any]] | None = None,
        files: dict[int, bytes] | None = None,
    ) -> None:
        self._children = (
            children
            if children is not None
            else [
                {
                    "name": "_request_letter_2026-05-15T080805Z.md",
                    "type": 1,
                    "counter": 2,
                    "document_file_id": 1152156,
                    "id": "1170198",
                }
            ]
        )
        self._files = files if files is not None else {1152156: LETTER.encode("utf-8")}

    def list_structure_items(self, binder_guid: str) -> list[dict[str, Any]]:
        return self._children

    def download_document_file(self, document_file_id: int) -> bytes:
        return self._files[document_file_id]


def _valid_token() -> str:
    return generate_token(vgm_id=VGM, expires_at=NOW + timedelta(days=3), secret=SECRET)


def _client(src: _FakeSource) -> TestClient:
    app.dependency_overrides[get_letter_source] = lambda: src
    app.dependency_overrides[get_secret] = lambda: SECRET
    app.dependency_overrides[get_now] = lambda: NOW
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(autouse=True)
def _clear_overrides() -> Any:
    yield
    app.dependency_overrides.clear()


def test_RT1_valid_token_renders_200_with_letter_and_form() -> None:
    token = _valid_token()
    client = _client(_FakeSource())

    r = client.get(f"/r/{token}")

    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    # letter content present (escaped in <pre>, plain text here)
    assert "Sehr geehrte Damen und Herren," in body
    # form wired for the (future) submit endpoint, multipart + required
    assert f'action="/r/{token}/submit"' in body
    assert 'method="POST"' in body
    assert 'enctype="multipart/form-data"' in body
    assert 'name="files"' in body
    assert "multiple" in body
    assert 'name="response"' in body


def test_RT2_invalid_token_404_generic_no_disclosure_structured_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    forged = generate_token(
        vgm_id=VGM, expires_at=NOW + timedelta(days=3), secret="OTHER" * 8
    )
    client = _client(_FakeSource())

    with caplog.at_level(logging.WARNING, logger="belegmeister.web"):
        r = client.get(f"/r/{forged}")

    assert r.status_code == 404
    assert "text/html" in r.headers["content-type"]
    body = r.text
    # generic message, no cause disclosure to the client
    assert "ungültig" in body or "abgelaufen" in body
    assert "token_invalid" not in body
    assert "token_expired" not in body
    # structured server log: reason present, token NEVER logged
    assert "magic_link_rejected" in caplog.text
    assert "token_invalid" in caplog.text
    assert forged not in caplog.text


def test_RT3_xss_letter_text_is_html_escaped() -> None:
    """Security guard: a letter containing <script> must render escaped.
    Confirms autoescape actually works, not merely that it's configured."""
    payload = "Hallo <script>alert(1)</script> Ende & <b>x</b>"
    src = _FakeSource(files={1152156: payload.encode("utf-8")})
    token = _valid_token()
    client = _client(src)

    r = client.get(f"/r/{token}")

    assert r.status_code == 200
    body = r.text
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
