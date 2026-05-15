"""HMAC-signed magic-link tokens.

Seam: `generate_token(*, vgm_id, expires_at, secret) -> str` and
`verify_token(*, token, secret, now) -> TokenPayload` (raises InvalidToken).

Token wire format
-----------------
    base64url(json_payload) + "." + base64url(hmac_sha256_sig)

Where `json_payload` is a canonical, sorted-keys JSON encoding of
`{"vgm_id": str, "exp": int}` (exp = unix seconds). HMAC is computed over
the base64url(payload) bytes (not the raw JSON), so verifiers don't need
to round-trip the JSON to recompute the signature.

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


class InvalidToken(Exception):
    """The token is malformed, signed with a different secret, or expired.

    The message embeds the rejection reason. The token itself is NEVER
    embedded in the message — including it in logs/exceptions would leak
    a still-valid credential.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Invalid magic-link token: {reason}")


@dataclass(frozen=True)
class TokenPayload:
    """Decoded magic-link payload. `exp` is unix seconds (UTC)."""

    vgm_id: str
    exp: int


def generate_token(*, vgm_id: str, expires_at: datetime, secret: str) -> str:
    """Encode `{vgm_id, exp}` and sign with HMAC-SHA256.

    Flow: build payload → encode → sign → join.
    """
    payload_b64 = _encode_payload(vgm_id=vgm_id, exp=int(expires_at.timestamp()))
    sig_b64 = _b64url_encode(_compute_sig(payload_b64=payload_b64, secret=secret))
    return f"{payload_b64}.{sig_b64}"


def verify_token(*, token: str, secret: str, now: datetime) -> TokenPayload:
    """Flow: split → verify signature → decode payload → check expiry."""
    payload_b64, sig_b64 = _split_token(token)
    _verify_signature(payload_b64=payload_b64, sig_b64=sig_b64, secret=secret)
    payload = _decode_payload(payload_b64)
    _check_not_expired(payload, now=now)
    return payload


def _encode_payload(*, vgm_id: str, exp: int) -> str:
    """Canonical JSON encode + base64url. Keys sorted, no whitespace, so
    the same logical payload always serializes to the same bytes."""
    payload_bytes = json.dumps(
        {"vgm_id": vgm_id, "exp": exp}, sort_keys=True, separators=(",", ":")
    ).encode()
    return _b64url_encode(payload_bytes)


def _compute_sig(*, payload_b64: str, secret: str) -> bytes:
    return hmac.new(
        secret.encode(), payload_b64.encode("ascii"), hashlib.sha256
    ).digest()


def _split_token(token: str) -> tuple[str, str]:
    parts = token.split(".", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise InvalidToken("malformed: expected '<payload>.<sig>'")
    return parts[0], parts[1]


def _verify_signature(*, payload_b64: str, sig_b64: str, secret: str) -> None:
    try:
        actual_sig = _b64url_decode(sig_b64)
    except (ValueError, binascii.Error) as exc:
        raise InvalidToken(f"malformed: signature not base64url ({exc})") from exc
    expected_sig = _compute_sig(payload_b64=payload_b64, secret=secret)
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise InvalidToken("signature mismatch")


def _decode_payload(payload_b64: str) -> TokenPayload:
    try:
        payload_bytes = _b64url_decode(payload_b64)
    except (ValueError, binascii.Error) as exc:
        raise InvalidToken(f"malformed: payload not base64url ({exc})") from exc
    try:
        data = json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        raise InvalidToken(f"malformed: payload not JSON ({exc.msg})") from exc
    if not isinstance(data, dict):
        raise InvalidToken("malformed: payload is not a JSON object")
    vgm_id_raw = data.get("vgm_id")
    exp_raw = data.get("exp")
    if not isinstance(vgm_id_raw, str) or not vgm_id_raw:
        raise InvalidToken("payload missing or invalid 'vgm_id'")
    if not isinstance(exp_raw, int) or isinstance(exp_raw, bool):
        raise InvalidToken("payload missing or invalid 'exp'")
    return TokenPayload(vgm_id=vgm_id_raw, exp=exp_raw)


def _check_not_expired(payload: TokenPayload, *, now: datetime) -> None:
    if int(now.timestamp()) >= payload.exp:
        raise InvalidToken("expired")


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
