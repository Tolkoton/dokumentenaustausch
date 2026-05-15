"""Unit tests for magic-link token generation and verification.

All tests are deterministic and pure (no I/O). They exercise the
HMAC-signed token contract described in `belegmeister.magic_link.token`.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest

from belegmeister.magic_link.token import (
    InvalidToken,
    TokenPayload,
    generate_token,
    verify_token,
)

SECRET = "a" * 48  # >=32 bytes so realistic usage passes the boundary check


def _b64url_decode(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)


def test_TG1_generate_returns_two_b64_segments_with_payload_fields() -> None:
    vgm_id = "11111111-1111-1111-1111-111111111111"
    expires_at = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    token = generate_token(vgm_id=vgm_id, expires_at=expires_at, secret=SECRET)

    assert isinstance(token, str)
    parts = token.split(".")
    assert len(parts) == 2, f"expected '<payload>.<sig>', got {token!r}"
    payload_b64, sig_b64 = parts
    assert payload_b64 and sig_b64

    decoded_payload = json.loads(_b64url_decode(payload_b64))
    assert decoded_payload == {
        "vgm_id": vgm_id,
        "exp": int(expires_at.timestamp()),
    }


def test_TG2_two_calls_with_identical_args_produce_identical_token() -> None:
    """Determinism guard: catches accidental randomness (e.g. a jti field,
    a salted signature, or expires_at being overwritten by wall-clock).
    HMAC-SHA256 is deterministic by construction; this test pins that
    contract at the module surface."""
    vgm_id = "22222222-2222-2222-2222-222222222222"
    expires_at = datetime(2030, 6, 15, 8, 30, 0, tzinfo=timezone.utc)

    t1 = generate_token(vgm_id=vgm_id, expires_at=expires_at, secret=SECRET)
    t2 = generate_token(vgm_id=vgm_id, expires_at=expires_at, secret=SECRET)

    assert t1 == t2


def test_TV1_round_trip_returns_same_payload() -> None:
    """generate → verify with same secret, before expiry → identical
    TokenPayload. Forces a real HMAC implementation (placeholder sig
    cannot survive this test)."""
    vgm_id = "33333333-3333-3333-3333-333333333333"
    expires_at = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    now = expires_at - timedelta(days=7)  # comfortably before expiry

    token = generate_token(vgm_id=vgm_id, expires_at=expires_at, secret=SECRET)
    payload = verify_token(token=token, secret=SECRET, now=now)

    assert payload == TokenPayload(vgm_id=vgm_id, exp=int(expires_at.timestamp()))


def test_TV2_expired_token_raises_invalid_token() -> None:
    vgm_id = "44444444-4444-4444-4444-444444444444"
    expires_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    now = expires_at + timedelta(seconds=1)  # one second past expiry

    token = generate_token(vgm_id=vgm_id, expires_at=expires_at, secret=SECRET)

    with pytest.raises(InvalidToken, match="expired"):
        verify_token(token=token, secret=SECRET, now=now)


def test_TV2_now_equal_to_exp_is_expired() -> None:
    """Boundary: now == exp must be treated as expired (>=, not >)."""
    vgm_id = "55555555-5555-5555-5555-555555555555"
    expires_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    token = generate_token(vgm_id=vgm_id, expires_at=expires_at, secret=SECRET)

    with pytest.raises(InvalidToken, match="expired"):
        verify_token(token=token, secret=SECRET, now=expires_at)


def test_TV3_wrong_secret_raises_signature_mismatch() -> None:
    vgm_id = "66666666-6666-6666-6666-666666666666"
    expires_at = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    now = expires_at - timedelta(days=1)
    other_secret = "b" * 48

    token = generate_token(vgm_id=vgm_id, expires_at=expires_at, secret=SECRET)

    with pytest.raises(InvalidToken, match="signature mismatch"):
        verify_token(token=token, secret=other_secret, now=now)


def test_TV4_token_without_dot_raises_malformed() -> None:
    now = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(InvalidToken, match="malformed"):
        verify_token(token="no-dot-here", secret=SECRET, now=now)


def test_TV4_non_b64_segment_raises_malformed() -> None:
    """Token shaped like '<payload>.<sig>' but with characters outside the
    base64url alphabet must surface as InvalidToken, not raw binascii."""
    now = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(InvalidToken, match="malformed"):
        verify_token(token="!!!.@@@", secret=SECRET, now=now)


def test_TV4_payload_not_json_raises_malformed() -> None:
    """A token whose signature matches but whose payload is not valid JSON
    must raise InvalidToken (not bare json.JSONDecodeError)."""
    now = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)
    payload_b64 = _b64url_encode_for_test(b"not-json-at-all")
    # sign the bad payload so we get past the sig check
    import hashlib
    import hmac as _hmac

    sig = _hmac.new(
        SECRET.encode(), payload_b64.encode("ascii"), hashlib.sha256
    ).digest()
    sig_b64 = _b64url_encode_for_test(sig)
    token = f"{payload_b64}.{sig_b64}"

    with pytest.raises(InvalidToken, match="malformed"):
        verify_token(token=token, secret=SECRET, now=now)


def _b64url_encode_for_test(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _sign_test_payload(payload_obj: object) -> str:
    """Build a sig-valid token with arbitrary JSON-able payload — used to
    exercise validation past the signature check."""
    import hashlib
    import hmac as _hmac

    payload_bytes = json.dumps(
        payload_obj, sort_keys=True, separators=(",", ":")
    ).encode()
    payload_b64 = _b64url_encode_for_test(payload_bytes)
    sig = _hmac.new(
        SECRET.encode(), payload_b64.encode("ascii"), hashlib.sha256
    ).digest()
    sig_b64 = _b64url_encode_for_test(sig)
    return f"{payload_b64}.{sig_b64}"


def test_TV5_payload_missing_vgm_id_raises() -> None:
    now = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)
    token = _sign_test_payload({"exp": int((now + timedelta(days=1)).timestamp())})
    with pytest.raises(InvalidToken, match="vgm_id"):
        verify_token(token=token, secret=SECRET, now=now)


def test_TV5_payload_vgm_id_wrong_type_raises() -> None:
    now = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)
    token = _sign_test_payload(
        {"vgm_id": 12345, "exp": int((now + timedelta(days=1)).timestamp())}
    )
    with pytest.raises(InvalidToken, match="vgm_id"):
        verify_token(token=token, secret=SECRET, now=now)


def test_TV5_payload_exp_wrong_type_raises() -> None:
    now = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)
    token = _sign_test_payload({"vgm_id": "abc", "exp": "soon"})
    with pytest.raises(InvalidToken, match="exp"):
        verify_token(token=token, secret=SECRET, now=now)


def test_TV5_payload_is_array_not_object_raises() -> None:
    now = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)
    token = _sign_test_payload(["vgm_id", "exp"])
    with pytest.raises(InvalidToken, match="payload"):
        verify_token(token=token, secret=SECRET, now=now)
