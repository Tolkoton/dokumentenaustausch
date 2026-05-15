"""Startup env fail-fast: the web app must refuse to start (RuntimeError
out of the lifespan) on missing/invalid env, instead of 500-ing
mid-request. TestClient as a context manager triggers the lifespan;
a startup failure surfaces on `__enter__`.
"""

from __future__ import annotations

import pytest
from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient

from belegmeister.web.app import app

_REQUIRED = {
    "MAGIC_LINK_SECRET": "z" * 48,
    "MAGIC_LINK_BASE_URL": "https://app.example.com",
    "KLARDATEN_API_KEY": "uk-test",
    "KLARDATEN_INSTANCE_ID": "inst-123",
}


def _set_all(mp: MonkeyPatch) -> None:
    for k, v in _REQUIRED.items():
        mp.setenv(k, v)


def test_lifespan_ok_with_full_valid_env(monkeypatch: MonkeyPatch) -> None:
    _set_all(monkeypatch)
    with TestClient(app):
        pass  # startup completed without raising


@pytest.mark.parametrize("missing", sorted(_REQUIRED))
def test_lifespan_raises_on_missing_required(
    monkeypatch: MonkeyPatch, missing: str
) -> None:
    _set_all(monkeypatch)
    monkeypatch.delenv(missing, raising=False)
    with pytest.raises(RuntimeError, match="Environment validation failed"):
        with TestClient(app):
            pass


def test_lifespan_raises_on_short_secret(monkeypatch: MonkeyPatch) -> None:
    _set_all(monkeypatch)
    monkeypatch.setenv("MAGIC_LINK_SECRET", "tooshort")
    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        with TestClient(app):
            pass


def test_lifespan_raises_on_non_https_base_url(
    monkeypatch: MonkeyPatch,
) -> None:
    _set_all(monkeypatch)
    monkeypatch.setenv("MAGIC_LINK_BASE_URL", "http://evil.example.com")
    with pytest.raises(RuntimeError, match="must start with 'https://'"):
        with TestClient(app):
            pass


def test_lifespan_localhost_base_url_ok(monkeypatch: MonkeyPatch) -> None:
    _set_all(monkeypatch)
    monkeypatch.setenv("MAGIC_LINK_BASE_URL", "http://localhost:8000")
    with TestClient(app):
        pass
