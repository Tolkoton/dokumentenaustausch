"""Resolve a magic-link token into the data needed to render the client
upload page. Pure logic, no HTTP framework — `web.app` is the glue.

Flow: verify token (Slice-2 `verify_token`, imported not copied) → list
the VGM's children → pick the newest `_request_letter_*.txt` by ISO name
→ download + UTF-8 decode its bytes → `RequestView`.

Any failure becomes a single generic `RequestLinkInvalid`. The specific
cause is NEVER surfaced to the client (information disclosure); it is
carried in `.log_reason` / `.log_context` for server-side structured
logging. The token string is NEVER placed in a log field.

This module does NOT: render HTML, serve HTTP, handle the submit POST,
store client uploads, or read env (the route layer injects deps).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import httpx

from belegmeister.magic_link.token import (
    InvalidToken,
    InvalidTokenReason,
    verify_token,
)
from belegmeister.vgm_files import (
    REQUEST_LETTER_PREFIX,
    REQUEST_LETTER_SUFFIX,
)


class LetterSource(Protocol):
    """Structural DI seam — the subset of KlardatenClient this needs.

    Public Protocol (same rationale as Slice-2's `BinderClient`): lets
    the route inject the real client and tests inject a fake, both under
    mypy strict, without duplicating the shape.
    """

    def list_structure_items(self, binder_guid: str) -> list[dict[str, Any]]: ...

    def download_document_file(self, document_file_id: int) -> bytes: ...


class RequestLinkInvalid(Exception):
    """Generic client-facing failure → HTTP 404 with a fixed message.

    The constructor takes a short grep-able code, never free text, so log
    queries stay stable. Canonical `log_reason` values (the ONLY allowed
    forms — do not invent variants):

      - "token_invalid"   : HMAC mismatch / malformed / structurally bad
      - "token_expired"   : signature OK but `now >= exp`
      - "vgm_not_found"   : DATEV returned 404 for the VGM (likely the
                            SB typed a wrong id) — tell the SB
      - "datev_error"     : any other DATEV failure (5xx, auth, timeout,
                            decode) — operational, may need on-call
      - "letter_missing"  : no `_request_letter_*.txt` child in the VGM
      - "download_failed" : document-file GET errored / non-200
      - "letter_not_utf8" : letter bytes are not valid UTF-8

    `log_context` is structured (e.g. {"vgm_id": ...}); the token string
    is NEVER added to it.
    """

    def __init__(
        self, *, log_reason: str, log_context: dict[str, Any] | None = None
    ) -> None:
        super().__init__(log_reason)
        self.log_reason = log_reason
        self.log_context: dict[str, Any] = log_context or {}


@dataclass(frozen=True)
class RequestView:
    vgm_id: str
    letter_filename: str
    letter_text: str


# Shared with the writer (see request_format) — single source of truth
# for the request-letter filename so writer/reader never diverge.
_LETTER_PREFIX = REQUEST_LETTER_PREFIX

# Token rejection → server-side log_reason. Exhaustive over
# InvalidTokenReason; a new reason without an entry raises KeyError
# (loud bug, by design — we never want a silent fallthrough here).
_TOKEN_LOG_REASON: dict[InvalidTokenReason, str] = {
    InvalidTokenReason.EXPIRED: "token_expired",
    InvalidTokenReason.BAD_SIGNATURE: "token_bad_signature",
    InvalidTokenReason.MALFORMED: "token_malformed",
}


def resolve_request_view(
    token: str,
    *,
    letter_source: LetterSource,
    secret: str,
    now: datetime,
) -> RequestView:
    """Flow: verify token → list children → pick newest letter → download
    + decode. Any failure → generic RequestLinkInvalid (cause in
    .log_reason)."""
    vgm_id = _verify(token, secret=secret, now=now)
    children = _list_children(vgm_id, letter_source)
    item = _pick_newest_letter(children, vgm_id=vgm_id)
    text = _download_text(item, letter_source, vgm_id=vgm_id)
    return RequestView(
        vgm_id=vgm_id,
        letter_filename=str(item["name"]),
        letter_text=text,
    )


def _verify(token: str, *, secret: str, now: datetime) -> str:
    try:
        payload = verify_token(token=token, secret=secret, now=now)
    except InvalidToken as exc:
        # Three distinct server-side log_reasons. The CLIENT always sees
        # the same generic 404 (no disclosure); the split exists only in
        # the log, giving free tamper-detection: a spike of
        # token_bad_signature = someone forging tokens; a spike of
        # token_malformed = benign email-truncation / copy-paste.
        reason = _TOKEN_LOG_REASON[exc.reason]
        raise RequestLinkInvalid(log_reason=reason) from exc
    return payload.vgm_id


def _list_children(vgm_id: str, source: LetterSource) -> list[dict[str, Any]]:
    try:
        return source.list_structure_items(vgm_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise RequestLinkInvalid(
                log_reason="vgm_not_found", log_context={"vgm_id": vgm_id}
            ) from exc
        raise RequestLinkInvalid(
            log_reason="datev_error",
            log_context={"vgm_id": vgm_id, "status": exc.response.status_code},
        ) from exc
    except httpx.HTTPError as exc:
        raise RequestLinkInvalid(
            log_reason="datev_error", log_context={"vgm_id": vgm_id}
        ) from exc


def _pick_newest_letter(
    children: list[dict[str, Any]], *, vgm_id: str
) -> dict[str, Any]:
    letters = [
        c
        for c in children
        if c.get("type") == 1
        and isinstance(c.get("name"), str)
        and c["name"].startswith(_LETTER_PREFIX)
        and c["name"].endswith(REQUEST_LETTER_SUFFIX)
    ]
    if not letters:
        raise RequestLinkInvalid(
            log_reason="letter_missing", log_context={"vgm_id": vgm_id}
        )
    return max(letters, key=lambda c: str(c["name"]))


def _download_text(item: dict[str, Any], source: LetterSource, *, vgm_id: str) -> str:
    file_id = item["document_file_id"]
    try:
        raw = source.download_document_file(int(file_id))
    except httpx.HTTPError as exc:
        raise RequestLinkInvalid(
            log_reason="download_failed", log_context={"vgm_id": vgm_id}
        ) from exc
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RequestLinkInvalid(
            log_reason="letter_not_utf8", log_context={"vgm_id": vgm_id}
        ) from exc
