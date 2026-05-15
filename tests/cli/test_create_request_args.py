"""Pydantic validation of `CreateRequestArgs`.

These tests pin the input contract independent of the flow (no upload,
no token, no fakes). They exercise the validators directly via
`model_validate(data, context={"now": now})`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from belegmeister.cli.create_request import CreateRequestArgs

NOW = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)


def _valid_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "vgm_id": "11111111-1111-1111-1111-111111111111",
        "letter_text": "Bitte Belege senden.",
        "expires_at": NOW + timedelta(days=14),
    }
    data.update(overrides)
    return data


def test_RC2_empty_letter_text_rejected() -> None:
    with pytest.raises(ValidationError, match="letter_text"):
        CreateRequestArgs.model_validate(
            _valid_data(letter_text=""), context={"now": NOW}
        )


def test_RC3_expires_at_in_past_rejected() -> None:
    past = NOW - timedelta(seconds=1)
    with pytest.raises(ValidationError, match="future"):
        CreateRequestArgs.model_validate(
            _valid_data(expires_at=past), context={"now": NOW}
        )


def test_RC3_expires_at_equal_to_now_rejected() -> None:
    """Symmetric with verify_token's `now >= exp` rule: a token whose exp
    equals creation-time is already expired, so reject at construction."""
    with pytest.raises(ValidationError, match="future"):
        CreateRequestArgs.model_validate(
            _valid_data(expires_at=NOW), context={"now": NOW}
        )


def test_RC4_ttl_over_seven_days_rejected() -> None:
    too_long = NOW + timedelta(days=8)
    with pytest.raises(ValidationError, match="7-day"):
        CreateRequestArgs.model_validate(
            _valid_data(expires_at=too_long), context={"now": NOW}
        )


def test_RC4_ttl_exactly_seven_days_accepted() -> None:
    """Boundary: 7 days to the second is allowed (cap is strict-greater-than)."""
    on_the_dot = NOW + timedelta(days=7)
    args = CreateRequestArgs.model_validate(
        _valid_data(expires_at=on_the_dot), context={"now": NOW}
    )
    assert args.expires_at == on_the_dot


def test_RC4_ttl_seven_days_plus_one_second_rejected() -> None:
    """Pedantic: `.total_seconds()` semantics — one second past the cap rejects.
    With `.days` floor semantics this would slip through (7 < 8); we don't
    want a credential whose lifetime can quietly extend up to 23h 59m past
    the documented cap."""
    just_over = NOW + timedelta(days=7, seconds=1)
    with pytest.raises(ValidationError, match="7-day"):
        CreateRequestArgs.model_validate(
            _valid_data(expires_at=just_over), context={"now": NOW}
        )
