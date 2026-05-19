"""Codec tests for belegmeister.request_format.

The codec's real proof is the round-trip property
`parse(serialize(x)) == x`; serializer-only assertions would be a
brittle string-match in a vacuum. Test-code prefix: RF<N>.
"""

from __future__ import annotations

import pytest

from belegmeister.request_format import (
    RequestLetter,
    RequestLetterMalformed,
    parse_request_letter,
    serialize_request_letter,
)


def test_RF1_full_letter_round_trips() -> None:
    letter = RequestLetter(
        to="client@example.com",
        cc="sb@example.com",
        subject="Unterlagen für Steuererklärung 2025",
        body="Sehr geehrte Frau Müller, bitte reichen Sie die Belege ein.",
        questions=("Wie hoch waren die Fahrtkosten?", "Gab es Nebeneinkünfte?"),
    )

    assert parse_request_letter(serialize_request_letter(letter)) == letter


def test_RF2_empty_cc_round_trips() -> None:
    letter = RequestLetter(
        to="client@example.com",
        cc="",
        subject="Unterlagen 2025",
        body="Bitte Belege einreichen.",
        questions=("Eine Frage?",),
    )

    assert parse_request_letter(serialize_request_letter(letter)) == letter


def test_RF3_zero_questions_round_trips() -> None:
    letter = RequestLetter(
        to="client@example.com",
        cc="",
        subject="Unterlagen 2025",
        body="Bitte Belege einreichen.",
        questions=(),
    )

    assert parse_request_letter(serialize_request_letter(letter)) == letter


def test_RF4_multiline_markdown_body_with_internal_blank_line_round_trips() -> None:
    # Binding requirement: body MUST contain a real empty line (not just
    # markdown markup) — proves `lines.index("")` keys on the header/body
    # separator, with body's own blank lines preserved verbatim after it.
    body = "# Überschrift\n\nAbsatz eins.\n\n- Punkt A\n- Punkt B"
    assert "\n\n" in body  # guards the fixture itself

    letter = RequestLetter(
        to="client@example.com",
        cc="sb@example.com",
        subject="Unterlagen 2025",
        body=body,
        questions=("Frage eins?",),
    )

    assert parse_request_letter(serialize_request_letter(letter)) == letter


def test_RF5_subject_with_internal_colon_round_trips() -> None:
    letter = RequestLetter(
        to="client@example.com",
        cc="",
        subject="Steuererklärung 2025: Unterlagen",
        body="Bitte einreichen.",
        questions=(),
    )

    round_tripped = parse_request_letter(serialize_request_letter(letter))
    assert round_tripped == letter
    assert round_tripped.subject == "Steuererklärung 2025: Unterlagen"


def test_RF6_body_lines_looking_like_headers_round_trip() -> None:
    # Body AFTER the separator — must not be mis-parsed as headers.
    letter = RequestLetter(
        to="client@example.com",
        cc="",
        subject="Unterlagen 2025",
        body="To: das ist kein Header\nSubject: auch nicht\nCc: ebenfalls nicht",
        questions=("Frage?",),
    )

    round_tripped = parse_request_letter(serialize_request_letter(letter))
    assert round_tripped == letter
    assert round_tripped.to == "client@example.com"


def test_RF_wire_literal_format_anchor() -> None:
    # Absolute format correctness — anchors against serialize/parse
    # co-drift (a mirrored bug stays green under round-trip alone).
    letter = RequestLetter(
        to="a@b.de",
        cc="c@d.de",
        subject="Subj",
        body="Hallo Welt",
        questions=("Q1", "Q2"),
    )

    expected = (
        "==BELEGMEISTER== request/v1\n"
        "To: a@b.de\n"
        "Cc: c@d.de\n"
        "Subject: Subj\n"
        "\n"
        "Hallo Welt\n"
        "==BELEGMEISTER== fragen\n"
        "Q1\n"
        "Q2\n"
        "==BELEGMEISTER== end\n"
    )

    assert serialize_request_letter(letter) == expected


def test_RF7_serialize_rejects_sentinel_line_in_body() -> None:
    # parse-side hostile input is B15; THIS guards serialize so a
    # crafted body can never emit a file that misparses on its way back.
    letter = RequestLetter(
        to="client@example.com",
        cc="",
        subject="Unterlagen 2025",
        body="Bitte einreichen.\n  ==BELEGMEISTER== end\nDanke.",
        questions=(),
    )

    with pytest.raises(RequestLetterMalformed) as exc:
        serialize_request_letter(letter)
    assert "==BELEGMEISTER==" in str(exc.value)


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("field", ["to", "cc", "subject"])
def test_RF8_serialize_rejects_newline_in_headers(field: str, newline: str) -> None:
    # Windows SB box + copy-paste => \r\n and bare \r are real, not
    # theoretical. This guard also transitively closes header sentinel
    # injection (a value with no newline cannot become its own line).
    base = {
        "to": "client@example.com",
        "cc": "sb@example.com",
        "subject": "Unterlagen 2025",
        "body": "Bitte einreichen.",
        "questions": (),
    }
    base[field] = f"value{newline}injected"
    letter = RequestLetter(**base)  # type: ignore[arg-type]

    with pytest.raises(RequestLetterMalformed) as exc:
        serialize_request_letter(letter)
    assert field in str(exc.value)


@pytest.mark.parametrize("body", ["", "   ", "  \n\t "])
def test_RF8b_serialize_rejects_empty_or_whitespace_body(body: str) -> None:
    # Folded serialize-guard decision: codec owns its own integrity
    # independent of CreateRequestArgs's min_length=1.
    letter = RequestLetter(
        to="client@example.com",
        cc="",
        subject="Unterlagen 2025",
        body=body,
        questions=(),
    )

    with pytest.raises(RequestLetterMalformed) as exc:
        serialize_request_letter(letter)
    assert "body" in str(exc.value)


def _valid_wire() -> str:
    return serialize_request_letter(
        RequestLetter(to="a@b.de", cc="", subject="S", body="B", questions=())
    )


def _with_first_line(line1: str) -> str:
    rest = _valid_wire().split("\n", 1)[1]
    return f"{line1}\n{rest}"


def test_RF9_parse_rejects_unrecognizable_first_line() -> None:
    with pytest.raises(RequestLetterMalformed) as exc:
        parse_request_letter(_with_first_line("Sehr geehrte Damen und Herren"))
    assert "missing or unrecognizable version marker" in str(exc.value)


def test_RF9_parse_does_not_quote_garbage_first_line() -> None:
    garbage = "Z" * 500
    with pytest.raises(RequestLetterMalformed) as exc:
        parse_request_letter(_with_first_line(garbage))
    msg = str(exc.value)
    assert garbage not in msg  # hostile content must NOT reach logs
    assert "missing or unrecognizable version marker" in msg


def test_RF9_parse_does_not_quote_oversized_version_token() -> None:
    # Structurally sentinel-prefixed but token fails the sane pattern
    # (too long) -> generic reason, NOT a quoted 500-char token.
    token = "x" * 500
    with pytest.raises(RequestLetterMalformed) as exc:
        parse_request_letter(_with_first_line(f"==BELEGMEISTER== {token}"))
    msg = str(exc.value)
    assert token not in msg
    assert "missing or unrecognizable version marker" in msg


@pytest.mark.parametrize("token", ["request/v2", "request/v99"])
def test_RF13_parse_rejects_known_structure_unknown_version(token: str) -> None:
    with pytest.raises(RequestLetterMalformed) as exc:
        parse_request_letter(_with_first_line(f"==BELEGMEISTER== {token}"))
    msg = str(exc.value)
    assert "unknown version" in msg
    assert token in msg  # token quoted only because it passed sane pattern


_FRAGEN = "==BELEGMEISTER== fragen"
_END = "==BELEGMEISTER== end"


def _wire_lines() -> list[str]:
    return _valid_wire().rstrip("\n").split("\n")


def test_RF10_parse_rejects_missing_fragen_marker() -> None:
    text = "\n".join(line for line in _wire_lines() if line != _FRAGEN)
    with pytest.raises(RequestLetterMalformed) as exc:
        parse_request_letter(text)
    assert "fragen" in str(exc.value)


def test_RF11_parse_rejects_missing_end_marker() -> None:
    text = "\n".join(line for line in _wire_lines() if line != _END)
    with pytest.raises(RequestLetterMalformed) as exc:
        parse_request_letter(text)
    assert "end" in str(exc.value)


def test_RF15_parse_rejects_marker_injected_inside_body() -> None:
    # fragen marker appears twice (once in body, once structural) ->
    # first-match index() would silently truncate body. count != 1.
    lines = _wire_lines()
    body_idx = lines.index("B")
    lines.insert(body_idx + 1, _FRAGEN)
    with pytest.raises(RequestLetterMalformed) as exc:
        parse_request_letter("\n".join(lines))
    assert "fragen" in str(exc.value)


def test_RF16_parse_rejects_missing_header_body_separator() -> None:
    # No blank line at all -> lines.index("") would raise bare
    # ValueError; must be a clean domain error instead.
    text = "\n".join(line for line in _wire_lines() if line != "")
    with pytest.raises(RequestLetterMalformed) as exc:
        parse_request_letter(text)
    assert "separator" in str(exc.value)


def test_RF17_parse_rejects_end_before_fragen() -> None:
    lines = _wire_lines()
    f_idx, e_idx = lines.index(_FRAGEN), lines.index(_END)
    lines[f_idx], lines[e_idx] = lines[e_idx], lines[f_idx]  # swap order
    with pytest.raises(RequestLetterMalformed) as exc:
        parse_request_letter("\n".join(lines))
    msg = str(exc.value)
    assert "end" in msg and "fragen" in msg  # specific, not generic


def test_RF17_parse_rejects_separator_after_fragen() -> None:
    # No header/body blank, but a blank in the questions section ->
    # first "" lands AFTER fragen. _verify_separator passes; order must
    # still reject (silent misparse otherwise).
    lines = [line for line in _wire_lines() if line != ""]
    f_idx = lines.index(_FRAGEN)
    lines.insert(f_idx + 1, "")  # blank between fragen and end
    with pytest.raises(RequestLetterMalformed) as exc:
        parse_request_letter("\n".join(lines))
    assert "separator" in str(exc.value)


def test_RF17_regression_internal_body_blanks_not_flagged() -> None:
    # B4-class: body's own blank lines must NOT trip the order guard
    # (sep_idx = FIRST "" = the real header/body separator, before
    # fragen). Expected green before AND after the B17 impl.
    letter = RequestLetter(
        to="a@b.de",
        cc="",
        subject="S",
        body="Absatz eins.\n\nAbsatz zwei.\n\nAbsatz drei.",
        questions=("Eine Frage?",),
    )
    assert parse_request_letter(serialize_request_letter(letter)) == letter


def test_RF14_parse_rejects_duplicate_header() -> None:
    # Two `To:` lines: silently last-wins today (injection vector).
    lines = _wire_lines()
    lines.insert(2, "To: angreifer@evil.example")
    with pytest.raises(RequestLetterMalformed) as exc:
        parse_request_letter("\n".join(lines))
    msg = str(exc.value)
    assert "duplicate" in msg and "To" in msg


def test_RF12_parse_strips_header_value_whitespace() -> None:
    # Contract lock-in for the agreed whitespace ruling: parser .strip()s
    # the value. Direct parse assertion (NOT round-trip identity, since
    # RequestLetter only ever holds already-clean values).
    lines = _wire_lines()
    subj_idx = next(i for i, line in enumerate(lines) if line.startswith("Subject:"))
    lines[subj_idx] = "Subject:    Steuererklärung 2025    "
    parsed = parse_request_letter("\n".join(lines))
    assert parsed.subject == "Steuererklärung 2025"
