"""B11 (security) — startup env fail-fast for the LOCAL SB app.

A mirror of the Slice-3 web C1 guard, asserted here against the SEPARATE
`belegmeister.sb.app` object (a public deploy must never be the only
thing C1-guarded). The sb lifespan calls the SHARED
`belegmeister.env_validation` helpers — this file pins that the new app
object is wired to them, not that the helpers themselves work (their own
unit tests own that). `TestClient(app)` as a context manager triggers
the lifespan; a startup failure surfaces on `__enter__`.

This is test-as-contract: the lifespan was written in the skeleton as a
verbatim C1 mirror, so no RED is expected — the value is regression
pinning of a security guard on the new app object.
"""

from __future__ import annotations

import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient

from belegmeister.sb.app import app

# MAGIC_LINK_BASE_URL here is the PUBLIC client-handler URL embedded in
# magic links — NOT the sb app's own localhost bind (:8731, a 4c
# launcher concern). validate_base_url checks THIS value.
_REQUIRED = {
    "MAGIC_LINK_SECRET": "z" * 48,
    "MAGIC_LINK_BASE_URL": "https://app.example.com",
    "KLARDATEN_API_KEY": "uk-test",
    "KLARDATEN_INSTANCE_ID": "inst-123",
}


def _set_all(mp: MonkeyPatch) -> None:
    for k, v in _REQUIRED.items():
        mp.setenv(k, v)


def test_B11_lifespan_ok_with_full_valid_env(monkeypatch: MonkeyPatch) -> None:
    _set_all(monkeypatch)
    with TestClient(app):
        pass  # startup completed without raising


@pytest.mark.parametrize("missing", sorted(_REQUIRED))
def test_B11_lifespan_raises_on_each_missing_required(
    monkeypatch: MonkeyPatch, missing: str
) -> None:
    _set_all(monkeypatch)
    monkeypatch.delenv(missing, raising=False)
    with pytest.raises(RuntimeError, match="Environment validation failed"):
        with TestClient(app):
            pass


def test_B11_lifespan_short_secret_exact_boundary(
    monkeypatch: MonkeyPatch,
) -> None:
    """Pin the exact MIN_SECRET_BYTES=32 boundary: 31 bytes rejected,
    32 bytes accepted (measured in BYTES, as the helper does)."""
    _set_all(monkeypatch)

    monkeypatch.setenv("MAGIC_LINK_SECRET", "z" * 31)
    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        with TestClient(app):
            pass

    monkeypatch.setenv("MAGIC_LINK_SECRET", "z" * 32)
    with TestClient(app):
        pass  # exactly 32 bytes boots


def test_B11_lifespan_non_https_magic_link_base_url_raises(
    monkeypatch: MonkeyPatch,
) -> None:
    # This is MAGIC_LINK_BASE_URL (the public client handler), NOT the
    # sb app's loopback bind — the two must not be conflated.
    _set_all(monkeypatch)
    monkeypatch.setenv("MAGIC_LINK_BASE_URL", "http://evil.example.com")
    with pytest.raises(RuntimeError, match="must start with 'https://'"):
        with TestClient(app):
            pass


def test_B11_lifespan_localhost_base_url_ok(monkeypatch: MonkeyPatch) -> None:
    _set_all(monkeypatch)
    monkeypatch.setenv("MAGIC_LINK_BASE_URL", "http://localhost:8000")
    with TestClient(app):
        pass  # dev exception allowed by the shared validator
