"""Unit tests for the shared env-validation helpers. Pure, no FastAPI,
no os.environ — values are passed in."""

from __future__ import annotations

import pytest

from belegmeister.env_validation import (
    MIN_SECRET_BYTES,
    validate_base_url,
    validate_required,
    validate_secret,
)


def test_validate_required_returns_value_when_present() -> None:
    assert validate_required("KLARDATEN_API_KEY", "uk-abc") == "uk-abc"


@pytest.mark.parametrize("bad", [None, ""])
def test_validate_required_raises_on_missing_or_empty(bad: str | None) -> None:
    with pytest.raises(ValueError, match="KLARDATEN_API_KEY.*required"):
        validate_required("KLARDATEN_API_KEY", bad)


def test_validate_secret_accepts_32_bytes_exactly() -> None:
    validate_secret("a" * MIN_SECRET_BYTES)  # no raise


def test_validate_secret_rejects_under_32_bytes() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        validate_secret("a" * (MIN_SECRET_BYTES - 1))


def test_validate_secret_counts_bytes_not_chars() -> None:
    """31 multi-byte chars are >=32 bytes — must pass (bytes, not len)."""
    value = "ä" * 31  # 'ä' is 2 bytes in UTF-8 -> 62 bytes
    validate_secret(value)  # no raise


@pytest.mark.parametrize(
    "url",
    [
        "https://app.example.com",
        "http://localhost:8000",
        "http://localhost",
    ],
)
def test_validate_base_url_accepts_https_or_localhost(url: str) -> None:
    validate_base_url(url)  # no raise


@pytest.mark.parametrize(
    "url",
    ["http://app.example.com", "ftp://x", "app.example.com", ""],
)
def test_validate_base_url_rejects_non_https_non_localhost(url: str) -> None:
    with pytest.raises(ValueError, match="must start with 'https://'"):
        validate_base_url(url)
