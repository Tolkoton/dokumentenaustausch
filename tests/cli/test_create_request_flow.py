"""Flow tests for `run_create_request` with an in-memory fake BinderClient.

The fake speaks the same shape as `KlardatenClient` (the `BinderClient`
Protocol) — `get_document` returns a Vorgangsmappe-shaped dict;
`attach_file_to_binder` records the call and returns a fixed structure-
item id. Tests assert observable side-effects: which file name was sent,
what URL was returned, and that the URL's token round-trips.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from belegmeister.cli.create_request import (
    CreateRequestArgs,
    UploadFailed,
    run_create_request,
)
from belegmeister.datev.upload import InvalidUploadTarget

SECRET = "k" * 48
BASE_URL = "https://app.example.com"
NOW = datetime(2026, 5, 15, 12, 30, 22, tzinfo=timezone.utc)


class _FakeBinderClient:
    """Records every call; serves a VGM-shaped get_document by default."""

    def __init__(
        self,
        *,
        binder_doc: dict[str, Any] | None = None,
        attach_result: dict[str, Any] | None = None,
    ) -> None:
        self._binder_doc = binder_doc or {"is_binder": True, "extension": "VGM"}
        self._attach_result = attach_result or {"id": "structure-item-xyz"}
        self.get_calls: list[str] = []
        self.attach_calls: list[dict[str, Any]] = []

    def get_document(self, guid: str) -> dict[str, Any]:
        self.get_calls.append(guid)
        return self._binder_doc

    def attach_file_to_binder(
        self, *, binder_guid: str, file_name: str, file_bytes: bytes
    ) -> dict[str, Any]:
        self.attach_calls.append(
            {
                "binder_guid": binder_guid,
                "file_name": file_name,
                "file_bytes": file_bytes,
            }
        )
        return self._attach_result


def _make_args(
    *,
    vgm_id: str = "11111111-1111-1111-1111-111111111111",
    letter_text: str = "Bitte senden Sie uns Belege für 2026.",
    ttl_days: int = 7,
) -> CreateRequestArgs:
    return CreateRequestArgs.model_validate(
        {
            "vgm_id": vgm_id,
            "letter_text": letter_text,
            "expires_at": NOW + timedelta(days=ttl_days),
        },
        context={"now": NOW},
    )


def test_RC1_happy_path_uploads_letter_and_returns_magic_link_url() -> None:
    args = _make_args()
    client = _FakeBinderClient()

    url = run_create_request(
        args,
        klardaten_client=client,
        magic_link_secret=SECRET,
        magic_link_base_url=BASE_URL,
        now=NOW,
    )

    # Side-effect: exactly one attach with the expected file name and bytes
    assert len(client.attach_calls) == 1
    call = client.attach_calls[0]
    assert call["binder_guid"] == args.vgm_id
    assert call["file_name"].startswith("_request_letter_")
    assert call["file_name"].endswith(".md")
    assert call["file_bytes"].decode("utf-8") == args.letter_text

    # URL shape: <base>/r/<token>
    assert url.startswith(f"{BASE_URL}/r/")
    token = url.removeprefix(f"{BASE_URL}/r/")
    assert "." in token  # payload.sig

    # Token round-trip: payload encodes the vgm_id and exp
    payload_b64 = token.split(".", 1)[0]
    padding = "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
    assert payload == {
        "vgm_id": args.vgm_id,
        "exp": int(args.expires_at.timestamp()),
    }


def test_RC5_invalid_upload_target_bubbles_up_with_no_attach() -> None:
    """If the target is not a Vorgangsmappe, `upload_to_binder` raises
    `InvalidUploadTarget` (carries vgm_id + reason). The flow must NOT
    swallow it: callers (CLI / future HTTP handler) need the named
    exception to distinguish a wrong-target from a transient HTTP error.

    Side-effect check: no attach was attempted, no URL composed."""
    args = _make_args()
    client = _FakeBinderClient(binder_doc={"is_binder": False, "extension": "PDF"})

    with pytest.raises(InvalidUploadTarget) as exc_info:
        run_create_request(
            args,
            klardaten_client=client,
            magic_link_secret=SECRET,
            magic_link_base_url=BASE_URL,
            now=NOW,
        )

    assert exc_info.value.binder_guid == args.vgm_id
    assert "Vorgangsmappe" in exc_info.value.reason
    assert client.attach_calls == [], "letter must not be attached on bad target"


def test_RC6_upload_failure_raises_UploadFailed_no_url_returned() -> None:
    """If `upload_to_binder` returns success=False, the flow MUST NOT
    produce a magic-link URL whose backing letter wasn't actually stored.
    A wrong URL on stdout would mislead the SB into emailing a link to
    an empty VGM. We raise a named domain exception instead."""
    args = _make_args()
    # Make _map_response fail by returning an attach payload without `id`.
    client = _FakeBinderClient(attach_result={"not_an_id": "garbage"})

    with pytest.raises(UploadFailed) as exc_info:
        run_create_request(
            args,
            klardaten_client=client,
            magic_link_secret=SECRET,
            magic_link_base_url=BASE_URL,
            now=NOW,
        )

    assert exc_info.value.vgm_id == args.vgm_id
    assert exc_info.value.reason  # carries upstream error text
    assert f"upload to {args.vgm_id} failed" in str(exc_info.value)
