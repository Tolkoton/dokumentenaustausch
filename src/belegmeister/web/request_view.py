"""Resolve a magic-link token into the data needed to render the client
upload page. Pure logic, no HTTP framework — `web.app` is the glue.

Flow: verify token (Slice-2 `verify_token`, imported not copied) → list
the VGM's children → pick the newest `_request_letter_*.txt` by ISO name
→ download + UTF-8 decode its bytes → `parse_request_letter` into a
typed `RequestLetter` → `RequestView`.

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
from belegmeister.request_format import (
    RequestLetter,
    RequestLetterMalformed,
    parse_request_letter,
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

      - "token_bad_signature": HMAC mismatch (forgery signal)
      - "token_malformed"    : structurally broken token (benign, e.g.
                               email truncation / copy-paste)
      - "token_expired"      : signature OK but `now >= exp`
      - "vgm_not_found"      : DATEV returned 404 for the VGM (likely the
                               SB typed a wrong id) — tell the SB
      - "datev_error"        : any other DATEV failure (5xx, auth,
                               timeout, decode) — operational, may need
                               on-call
      - "letter_missing"     : no `_request_letter_*.txt` child in the
                               VGM
      - "download_failed"    : document-file GET errored / non-200
      - "letter_not_utf8"    : letter bytes are not valid UTF-8
      - "letter_malformed"   : bytes decode as UTF-8 but fail the
                               `request/v1` codec (`parse_request_letter`).
                               `log_context["reason"]` carries the
                               codec's short reason code.

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
    """The data a Mandant's magic-link page needs to render.

    Produced by ``resolve_request_view`` after the token is verified,
    the corresponding request letter has been fetched from DATEV, and
    its bytes have been parsed via the ``request/v1`` codec
    (``parse_request_letter``). Carries no token (the route holds that
    separately) and no transport metadata — just the parsed letter.

    Attributes:
        vgm_id: The VGM (Vorgangsmappe) GUID the token bound to.
            Useful for log correlation; not shown to the Mandant.
        letter_filename: The selected letter's filename inside the VGM
            (``_request_letter_<iso>.txt``); informational, used for
            debugging / smoke output rather than display.
        letter: The parsed ``RequestLetter`` (subject, body, questions,
            to, cc). The route handler is responsible for narrowing the
            Jinja2 template context — ``letter.to`` and ``letter.cc``
            are NEVER passed to the Mandant page (see Decision D-S8 in
            ``.overseer/slice/magic-link-ui.md``: privacy +
            XSS-surface reduction by construction). They remain on the
            view because the future email-slice consumes them as SMTP
            header values.
    """

    vgm_id: str
    letter_filename: str
    letter: RequestLetter


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


def _parse_letter(text: str, *, vgm_id: str) -> RequestLetter:
    """Parse the wire-format letter text via the ``request/v1`` codec.

    Any ``RequestLetterMalformed`` raised by the codec collapses into a
    ``RequestLinkInvalid`` with ``log_reason="letter_malformed"`` and
    the codec's short ``reason`` carried in ``log_context["reason"]``
    (NEVER the file content). The client still sees the generic 404.
    """
    try:
        return parse_request_letter(text)
    except RequestLetterMalformed as exc:
        raise RequestLinkInvalid(
            log_reason="letter_malformed",
            log_context={"vgm_id": vgm_id, "reason": exc.reason},
        ) from exc


def resolve_request_view(
    token: str,
    *,
    letter_source: LetterSource,
    secret: str,
    now: datetime,
) -> RequestView:
    """Verify a magic-link token and load the request letter it points at.

    The core logic behind ``GET /r/{token}``. Steps:

    1. ``verify_token`` (``belegmeister.magic_link.token``) — HMAC
       check + expiry. Each ``InvalidTokenReason`` maps to a distinct
       server-side ``log_reason`` (``token_expired``,
       ``token_bad_signature``, ``token_malformed``) so a spike of
       ``token_bad_signature`` surfaces as a tamper signal. The client
       still sees the same generic 404 regardless of which reason
       fired.
    2. ``letter_source.list_structure_items(vgm_id)`` — klardaten
       ``GET /datevconnect/dms/v2/documents/{vgm}/structure-items``.
       A 404 here means the VGM id baked into the (verified!) token
       no longer exists in DATEV — extremely unlikely under normal
       use; logged as ``vgm_not_found``.
    3. Pick the lexicographically-largest child whose name matches
       ``_request_letter_*.txt``. The producer
       (``cli.create_request.run_create_request``) writes
       ISO-stamped names, so newest-by-name = newest-in-time. If no
       letter is found, ``log_reason="letter_missing"``.
    4. ``letter_source.download_document_file(int(file_id))`` —
       klardaten ``GET /document-files/{id}``; decoded as UTF-8.
       Errors map to ``download_failed`` (transport) or
       ``letter_not_utf8`` (bytes are not valid UTF-8).
    5. ``parse_request_letter`` — decode the ``request/v1`` wire format
       into a typed ``RequestLetter``. A ``RequestLetterMalformed``
       collapses into ``log_reason="letter_malformed"``; the codec's
       short reason rides in ``log_context["reason"]``.

    All failures collapse into a single ``RequestLinkInvalid`` whose
    ``log_reason`` and ``log_context`` carry the cause for server-side
    structured logging. The token string is NEVER added to
    ``log_context``.

    Args:
        token: Raw token from the URL path. Opaque to this function.
        letter_source: ``LetterSource``-shaped object — a
            ``KlardatenClient`` in production, a fake in tests.
        secret: HMAC key. Caller has validated length upstream.
        now: Reference wall-clock for expiry. Injected for
            deterministic tests.

    Returns:
        A ``RequestView`` carrying the verified ``vgm_id``, the chosen
        ``letter_filename``, and the parsed ``RequestLetter``. The
        route handler is responsible for narrowing the Jinja2 template
        context — ``letter.to`` / ``letter.cc`` are NEVER passed to the
        Mandant page (Decision D-S8).

    Raises:
        RequestLinkInvalid: With one of the canonical ``log_reason``
            values documented on the exception class
            (``token_expired``, ``token_bad_signature``,
            ``token_malformed``, ``vgm_not_found``, ``datev_error``,
            ``letter_missing``, ``download_failed``,
            ``letter_not_utf8``, ``letter_malformed``). Includes a
            ``log_context`` ``dict`` where applicable — typically
            ``{"vgm_id": ...}`` and, for HTTP errors, the status code;
            for ``letter_malformed`` also the codec's ``reason``.

    Side effects:
        Up to two HTTP requests to klardaten via ``letter_source`` on
        the happy path. No local I/O, no log emission (the route layer
        owns logging so the token never leaves this function with
        free-text context).
    """
    vgm_id = _verify(token, secret=secret, now=now)
    children = _list_children(vgm_id, letter_source)
    item = _pick_newest_letter(children, vgm_id=vgm_id)
    text = _download_text(item, letter_source, vgm_id=vgm_id)
    letter = _parse_letter(text, vgm_id=vgm_id)
    return RequestView(
        vgm_id=vgm_id,
        letter_filename=str(item["name"]),
        letter=letter,
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
