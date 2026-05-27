"""HMAC-signed magic-link tokens.

Seam: `generate_token(*, vgm_id, letter_id, expires_at, secret) -> str`
and `verify_token(*, token, secret, now) -> TokenPayload` (raises
InvalidToken).

Token wire format
-----------------
    base64url(json_payload) + "." + base64url(hmac_sha256_sig)

Where `json_payload` is a canonical, sorted-keys JSON encoding of
`{"vgm_id": str, "letter_id": str, "exp": int}` (exp = unix seconds).
HMAC is computed over the base64url(payload) bytes (not the raw JSON),
so verifiers don't need to round-trip the JSON to recompute the
signature.

The `letter_id` field binds the token to a specific `_request_letter_*`
structure-item inside the VGM (the structure-item `id` returned by
klardaten's DMS — see `datev.upload.UploadResult.document_id`). A token
no longer says "any current letter in this VGM"; it says "this letter,
in this VGM." The pre-slice `{vgm_id, exp}` wire shape is no longer
honored — `verify_token` rejects it as `MALFORMED`. See ADR / slice
`token-instance-binding` for the rationale.

Both halves use URL-safe base64 with `=` padding stripped — safe to embed
in a URL path segment without further escaping.

This module does NOT:
- read MAGIC_LINK_SECRET from env (callers do that at the boundary,
  with the >=32-byte fail-fast check)
- maintain a revocation list / blacklist (stateless tokens; revocation
  is a future slice)
- emit any logging — callers must never log a full token or URL
- depend on a wall-clock; `verify_token` takes `now` as an argument so
  expiry can be tested deterministically
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class InvalidTokenReason(StrEnum):
    """Structured rejection code. Consumers branch on identity, not on
    the human message text (was a fragile cross-module string-match)."""

    MALFORMED = "malformed"
    BAD_SIGNATURE = "bad_signature"
    EXPIRED = "expired"


class InvalidToken(Exception):
    """The token is malformed, signed with a different secret, or expired.

    `.reason` is a typed `InvalidTokenReason`; `.detail` is the human
    description for logs. The token itself is NEVER passed in — including
    it would leak a still-valid credential into logs/tracebacks.
    """

    def __init__(self, reason: InvalidTokenReason, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"Invalid magic-link token: {detail or reason.value}")


@dataclass(frozen=True)
class TokenPayload:
    """Decoded magic-link payload.

    Attributes:
        vgm_id: The DATEV Vorgangsmappe GUID this token binds to.
        letter_id: The structure-item `id` (string) of the specific
            `_request_letter_*` inside the VGM that the token grants
            access to. Mints from `UploadResult.document_id` (see
            `belegmeister.datev.upload`); never empty.
        exp: Hard expiry, unix seconds (UTC).
    """

    vgm_id: str
    letter_id: str
    exp: int


def generate_token(
    *, vgm_id: str, letter_id: str, expires_at: datetime, secret: str
) -> str:
    """Mint a signed magic-link token binding a Mandant to one VGM.

    The returned string is the path segment in ``/r/<token>`` URLs.
    Flow: build canonical JSON payload → base64url-encode → HMAC-SHA256
    over the encoded payload bytes → base64url-encode the signature →
    join with ``"."``. Signing the encoded payload (not the raw JSON)
    means verifiers do not need to round-trip JSON to recompute the
    signature.

    Args:
        vgm_id: The DATEV Vorgangsmappe GUID the link grants access to.
            Embedded into the JSON payload verbatim. The caller is
            responsible for using a real GUID (e.g. from
            ``resolve_binder_guid_by_number`` then
            ``upload_to_binder``).
        letter_id: The structure-item ``id`` of the specific
            ``_request_letter_*`` inside the VGM the token grants
            access to. Mints from ``UploadResult.document_id`` returned
            by ``upload_to_binder``. Must be non-empty; an empty string
            is rejected at the verify side as ``MALFORMED``.
        expires_at: Hard expiry, in any timezone. Truncated to integer
            unix seconds (``int(expires_at.timestamp())``) inside the
            payload; sub-second precision is intentionally lost so the
            payload is stable across serializations. Callers enforce
            their own TTL cap upstream (see
            ``belegmeister.cli.create_request.MAX_TTL_DAYS``).
        secret: HMAC key, encoded to UTF-8 bytes. Callers must have
            validated this via
            ``belegmeister.env_validation.validate_secret`` (≥32 bytes)
            BEFORE getting here; this function does not re-check.

    Returns:
        The token as ``"<payload_b64url>.<sig_b64url>"``. Both halves
        use URL-safe base64 with ``=`` padding stripped — safe to embed
        in a URL path segment without further escaping.

    Side effects:
        None. Pure function over its arguments; deterministic for fixed
        ``(vgm_id, expires_at, secret)``.
    """
    payload_b64 = _encode_payload(
        vgm_id=vgm_id, letter_id=letter_id, exp=int(expires_at.timestamp())
    )
    sig_b64 = _b64url_encode(_compute_sig(payload_b64=payload_b64, secret=secret))
    return f"{payload_b64}.{sig_b64}"


def verify_token(*, token: str, secret: str, now: datetime) -> TokenPayload:
    """Verify a magic-link token and return its decoded payload.

    Flow: split on ``"."`` → constant-time HMAC compare → base64url-
    decode the payload → JSON-decode → check ``exp`` against ``now``.
    Signature verification runs BEFORE payload decoding so that any
    structural defect in an unsigned-or-tampered token (corrupt JSON,
    missing fields, wrong types) cannot leak information about the
    payload's contents through a different error path.

    Args:
        token: The token string from the URL path segment in
            ``/r/<token>``. Trailing/leading whitespace and embedded
            slashes are NOT trimmed — the caller (the FastAPI route)
            already constrains the path-param shape.
        secret: HMAC key, must be the same one used by
            ``generate_token``. Validated for length upstream.
        now: Reference wall-clock for the expiry check. Passed in
            (rather than read from ``datetime.now``) so tests can pin a
            deterministic time.

    Returns:
        The decoded ``TokenPayload`` (``vgm_id`` ``str``, ``exp`` unix
        seconds ``int``) when every check passes.

    Raises:
        InvalidToken: Always with a typed ``reason``. The token string
            itself is NEVER included in the exception (or in any log
            message the route emits) — including it would leak a
            still-valid credential into tracebacks and aggregator logs.
            ``reason`` values, in the order they are checked:

            * ``InvalidTokenReason.MALFORMED`` — wrong number of dots,
              empty halves, non-base64url characters in either half,
              payload is not valid JSON / not a JSON object, or
              ``vgm_id`` / ``letter_id`` / ``exp`` is missing or the
              wrong type (incl. an empty-string ``letter_id``, which
              is no identity at all — same rejection class as missing).
              The pre-slice ``{vgm_id, exp}``-only payload shape is
              rejected here because ``letter_id`` is missing.
            * ``InvalidTokenReason.BAD_SIGNATURE`` — both halves are
              well-formed but HMAC compare fails (forged or
              wrong-secret token). Free tamper-detection signal — log
              maps this to ``log_reason="token_bad_signature"`` (see
              ``docs/SECURITY.md``).
            * ``InvalidTokenReason.EXPIRED`` — signature is valid but
              ``now`` is at or past the payload's ``exp``.
    """
    payload_b64, sig_b64 = _split_token(token)
    _verify_signature(payload_b64=payload_b64, sig_b64=sig_b64, secret=secret)
    payload = _decode_payload(payload_b64)
    _check_not_expired(payload, now=now)
    return payload


def _encode_payload(*, vgm_id: str, letter_id: str, exp: int) -> str:
    """Canonical JSON encode + base64url. Keys sorted, no whitespace, so
    the same logical payload always serializes to the same bytes."""
    payload_bytes = json.dumps(
        {"vgm_id": vgm_id, "letter_id": letter_id, "exp": exp},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return _b64url_encode(payload_bytes)


def _compute_sig(*, payload_b64: str, secret: str) -> bytes:
    return hmac.new(
        secret.encode(), payload_b64.encode("ascii"), hashlib.sha256
    ).digest()


def _split_token(token: str) -> tuple[str, str]:
    parts = token.split(".", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise InvalidToken(InvalidTokenReason.MALFORMED, "expected '<payload>.<sig>'")
    return parts[0], parts[1]


def _verify_signature(*, payload_b64: str, sig_b64: str, secret: str) -> None:
    try:
        actual_sig = _b64url_decode(sig_b64)
    except (ValueError, binascii.Error) as exc:
        raise InvalidToken(
            InvalidTokenReason.MALFORMED,
            f"signature not base64url ({exc})",
        ) from exc
    expected_sig = _compute_sig(payload_b64=payload_b64, secret=secret)
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise InvalidToken(InvalidTokenReason.BAD_SIGNATURE, "signature mismatch")


def _decode_payload(payload_b64: str) -> TokenPayload:
    try:
        payload_bytes = _b64url_decode(payload_b64)
    except (ValueError, binascii.Error) as exc:
        raise InvalidToken(
            InvalidTokenReason.MALFORMED,
            f"payload not base64url ({exc})",
        ) from exc
    try:
        data = json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        raise InvalidToken(
            InvalidTokenReason.MALFORMED,
            f"payload not JSON ({exc.msg})",
        ) from exc
    if not isinstance(data, dict):
        raise InvalidToken(InvalidTokenReason.MALFORMED, "payload is not a JSON object")
    vgm_id_raw = data.get("vgm_id")
    letter_id_raw = data.get("letter_id")
    exp_raw = data.get("exp")
    if not isinstance(vgm_id_raw, str) or not vgm_id_raw:
        raise InvalidToken(
            InvalidTokenReason.MALFORMED, "payload missing or invalid 'vgm_id'"
        )
    if not isinstance(letter_id_raw, str) or not letter_id_raw:
        # Empty-string letter_id is no identity at all — same rejection
        # class as missing. Also where pre-slice {vgm_id, exp}-only
        # tokens land (no-backwards-compat lockin per slice
        # token-instance-binding).
        raise InvalidToken(
            InvalidTokenReason.MALFORMED, "payload missing or invalid 'letter_id'"
        )
    if not isinstance(exp_raw, int) or isinstance(exp_raw, bool):
        raise InvalidToken(
            InvalidTokenReason.MALFORMED, "payload missing or invalid 'exp'"
        )
    return TokenPayload(vgm_id=vgm_id_raw, letter_id=letter_id_raw, exp=exp_raw)


def _check_not_expired(payload: TokenPayload, *, now: datetime) -> None:
    if int(now.timestamp()) >= payload.exp:
        raise InvalidToken(InvalidTokenReason.EXPIRED, "expired")


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """Strict base64url decode: raises on any character outside the alphabet.

    Standard `urlsafe_b64decode` silently drops unknown bytes; we want a
    hard error so malformed tokens surface as InvalidToken (not as
    spurious signature mismatches against random truncated bytes).
    """
    s_standard = s.translate(str.maketrans("-_", "+/"))
    return base64.b64decode(s_standard + "=" * (-len(s) % 4), validate=True)
