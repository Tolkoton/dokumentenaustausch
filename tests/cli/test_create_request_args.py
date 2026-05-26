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
        "to": "mandant@example.com",
        "cc": "kanzlei@example.com",
        "subject": "Unterlagen 2026",
        "body": "Bitte Belege senden.",
        "questions": ["Wie hoch waren die Fahrtkosten?"],
        "expires_at": NOW + timedelta(days=5),
    }
    data.update(overrides)
    return data


def test_RC2_V1_valid_args_strip_headers_and_questions_keep_body_verbatim() -> None:
    args = CreateRequestArgs.model_validate(
        _valid_data(
            to="  mandant@example.com  ",
            subject="\tUnterlagen 2026 ",
            questions=["  Frage eins?  ", "Frage zwei?"],
            body="Zeile eins.\nZeile zwei.",
        ),
        context={"now": NOW},
    )
    assert args.to == "mandant@example.com"
    assert args.subject == "Unterlagen 2026"
    assert args.questions == ["Frage eins?", "Frage zwei?"]
    assert args.body == "Zeile eins.\nZeile zwei."


def test_RC2_V2_body_not_trimmed_leading_trailing_blanks_preserved() -> None:
    # SB content reaches the VGM byte-for-byte: intentional indentation
    # and surrounding blank lines survive validation unchanged.
    body = "\n\n  Sehr geehrte Frau Müller,\n\n  ...\n\nMit freundlichen Grüßen\n\n"
    args = CreateRequestArgs.model_validate(
        _valid_data(body=body), context={"now": NOW}
    )
    assert args.body == body  # NOT stripped


def test_RC2_V3_cc_optional_empty_and_absent_valid() -> None:
    empty = CreateRequestArgs.model_validate(_valid_data(cc=""), context={"now": NOW})
    assert empty.cc == ""
    data = _valid_data()
    del data["cc"]
    absent = CreateRequestArgs.model_validate(data, context={"now": NOW})
    assert absent.cc == ""


def test_RC2_V4_questions_optional_empty_and_absent_valid() -> None:
    empty = CreateRequestArgs.model_validate(
        _valid_data(questions=[]), context={"now": NOW}
    )
    assert empty.questions == []
    data = _valid_data()
    del data["questions"]
    absent = CreateRequestArgs.model_validate(data, context={"now": NOW})
    assert absent.questions == []


@pytest.mark.parametrize("field", ["to", "subject", "body"])
@pytest.mark.parametrize("value", ["", "   ", "\t\n "])
def test_RC2_V5_V6_required_text_blank_rejected(field: str, value: str) -> None:
    with pytest.raises(ValidationError, match=field):
        CreateRequestArgs.model_validate(
            _valid_data(**{field: value}), context={"now": NOW}
        )


@pytest.mark.parametrize("field", ["to", "cc", "subject"])
@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_RC2_V7_header_newline_rejected(field: str, newline: str) -> None:
    with pytest.raises(ValidationError, match=field):
        CreateRequestArgs.model_validate(
            _valid_data(**{field: f"a{newline}b"}), context={"now": NOW}
        )


def test_RC2_V8_body_sentinel_collision_rejected() -> None:
    with pytest.raises(ValidationError, match="body"):
        CreateRequestArgs.model_validate(
            _valid_data(body="ok line\n==BELEGMEISTER== end\nmore"),
            context={"now": NOW},
        )


@pytest.mark.parametrize("bad", ["frage\nzeile2", "==BELEGMEISTER== fragen"])
def test_RC2_V9_bad_question_rejected(bad: str) -> None:
    with pytest.raises(ValidationError, match="question"):
        CreateRequestArgs.model_validate(
            _valid_data(questions=["gut?", bad]), context={"now": NOW}
        )


@pytest.mark.parametrize("blank", ["", "   ", "\t", "\n", "  \t  "])
def test_RC2_V9b_blank_question_drops_silently(blank: str) -> None:
    args = CreateRequestArgs.model_validate(
        _valid_data(questions=["gut?", blank, "auch gut?"]), context={"now": NOW}
    )
    assert args.questions == ["gut?", "auch gut?"]


def test_RC2_V9c_all_blank_questions_collapse_to_empty() -> None:
    args = CreateRequestArgs.model_validate(
        _valid_data(questions=["", "   ", "\t"]), context={"now": NOW}
    )
    assert args.questions == []


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
