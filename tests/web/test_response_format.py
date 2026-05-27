"""Tests for the response-letter codec — slice submit-handler UNIT 1.

Mirrors `tests/test_request_format.py` shape. Covers Phase-3 Hardest
Seam S4 (sentinel-collision safety; 3 positive + 1 negative fixture)
plus S6 codec-level filename-verbatim assertion. The integration-level
S6 (two-files-same-original UUID disambiguation) lives in
`tests/web/test_app_submit_inventory.py` and is UNIT 3's responsibility.

Per the slice contract: this UNIT covers serialization only (no parse
round-trip); the response doc is write-once from the server's
perspective. Downstream consumers needing parse are deferred (Phase 5
item #13).
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from belegmeister.web.response_format import (
    AttachmentOutcome,
    ResponseDocument,
    ResponseLetterMalformed,
    failure_reason_from_klardaten_outcome,
    serialize_response_letter,
)


def _make_doc(
    *,
    qa_pairs: tuple[tuple[str, str], ...] = (
        ("Bitte schicken Sie uns die Rechnung.", "Anbei."),
    ),
    anmerkungen: str = "",
    attachments: tuple[AttachmentOutcome, ...] = (),
) -> ResponseDocument:
    """Build a minimally-filled `ResponseDocument` for tests that only
    care about ONE field. Each test overrides only the field it
    exercises; other fields take innocuous defaults that round-trip
    cleanly through the serializer."""
    return ResponseDocument(
        letter_id="1185519",  # plausible structure-item id from the spike
        submitted_at=datetime(2026, 5, 27, 10, 30, 0, tzinfo=timezone.utc),
        qa_pairs=qa_pairs,
        anmerkungen=anmerkungen,
        attachments=attachments,
    )


def _succeeded_attachment(
    *,
    original_filename: str,
    stored_filename: str | None = None,
    structure_item_id: str = "1186600",
    document_file_id: int = 1166000,
) -> AttachmentOutcome:
    """Build a succeeded `AttachmentOutcome`. `stored_filename` defaults
    to `_attachment_<lid>_aaaaaaaa_<original>`; tests pin it where
    needed (the S6 fixture uses two different UUIDs)."""
    if stored_filename is None:
        stored_filename = f"_attachment_1185519_aaaaaaaa_{original_filename}"
    return AttachmentOutcome(
        original_filename=original_filename,
        stored_filename=stored_filename,
        structure_item_id=structure_item_id,
        document_file_id=document_file_id,
        status="succeeded",
        failure_reason=None,
        elapsed_s=1.2,
    )


def _failed_attachment(
    *, original_filename: str, failure_reason: str = "klardaten_4xx"
) -> AttachmentOutcome:
    return AttachmentOutcome(
        original_filename=original_filename,
        stored_filename=None,
        structure_item_id=None,
        document_file_id=None,
        status="failed",
        failure_reason=failure_reason,
        elapsed_s=0.4,
    )


# --- Happy-path anchor (sanity-only; pins the wire shape) ---


def test_serializer_emits_canonical_wire_format() -> None:
    """Anchor test pinning the exact wire bytes for one realistic input.

    Mirrors 4a's `test_RF_wire_literal_format_anchor` — if this fails
    after a minor edit, the codec's on-wire format has shifted and the
    SB-facing display in DATEV-UO has changed too. A drift detector,
    not a coverage test.
    """
    doc = ResponseDocument(
        letter_id="1185519",
        submitted_at=datetime(2026, 5, 27, 10, 30, 0, tzinfo=timezone.utc),
        qa_pairs=(
            ("Bitte schicken Sie uns die Rechnung.", "Anbei."),
            ("Welche Bank?", "Sparkasse."),
        ),
        anmerkungen="Nur eine Anmerkung zur Sicherheit.",
        attachments=(
            _succeeded_attachment(
                original_filename="rechnung.pdf",
                stored_filename="_attachment_1185519_a1b2c3d4_rechnung.pdf",
            ),
            _failed_attachment(
                original_filename="kaputt.pdf", failure_reason="klardaten_5xx"
            ),
        ),
    )

    expected = (
        "==BELEGMEISTER== response/v1\n"
        "Letter-Id: 1185519\n"
        "Submitted-At: 2026-05-27T10:30:00+00:00\n"
        "\n"
        "==ANTWORTEN==\n"
        "Q1: Bitte schicken Sie uns die Rechnung.\n"
        "A1: Anbei.\n"
        "\n"
        "Q2: Welche Bank?\n"
        "A2: Sparkasse.\n"
        "==ANMERKUNGEN==\n"
        "Nur eine Anmerkung zur Sicherheit.\n"
        "==ATTACHMENTS==\n"
        "_attachment_1185519_a1b2c3d4_rechnung.pdf\n"
        "==FAILED_ATTACHMENTS==\n"
        "kaputt.pdf: klardaten_5xx\n"
        "==BELEGMEISTER== end\n"
    )
    assert serialize_response_letter(doc) == expected


# --- S4: sentinel-collision safety (3 positive + 1 negative) ---


def test_serializer_raises_on_marker_in_answer() -> None:
    """Phase-3 Seam S4 positive: a Mandant answer containing a literal
    section marker MUST trip the predicate."""
    doc = _make_doc(
        qa_pairs=(
            ("Wie war's?", "Schön. Aber:\n==FAILED_ATTACHMENTS==\nwas ist das?"),
        ),
    )
    with pytest.raises(ResponseLetterMalformed) as exc:
        serialize_response_letter(doc)
    # Reason names the field so an operator can locate the offending
    # cell without re-reading raw input.
    assert "answer" in exc.value.reason.lower()


def test_serializer_raises_on_marker_in_anmerkungen() -> None:
    """Phase-3 Seam S4 positive: Anmerkungen freeform containing a
    literal section marker MUST trip the predicate."""
    doc = _make_doc(
        anmerkungen="Vielen Dank.\n==BELEGMEISTER== end\nMfG.",
    )
    with pytest.raises(ResponseLetterMalformed) as exc:
        serialize_response_letter(doc)
    assert "anmerkungen" in exc.value.reason.lower()


def test_serializer_raises_on_marker_in_filename() -> None:
    """Phase-3 Seam S4 positive: an attachment whose original filename
    contains a literal section marker MUST trip the predicate. Per the
    slice contract, this protection applies to BOTH `original_filename`
    and `stored_filename` (the latter would inherit any collision from
    the former). Here we exercise the original-filename axis with a
    bare `==ATTACHMENTS==` marker per the slice contract."""
    doc = _make_doc(
        attachments=(
            _succeeded_attachment(
                original_filename="==ATTACHMENTS==.pdf",
                stored_filename="_attachment_1185519_aaaaaaaa_==ATTACHMENTS==.pdf",
            ),
        ),
    )
    with pytest.raises(ResponseLetterMalformed) as exc:
        serialize_response_letter(doc)
    assert "filename" in exc.value.reason.lower()


def test_serializer_preserves_near_miss_content_verbatim() -> None:
    """Phase-3 Seam S4 negative (assertion-b form, per Pushback 2):
    near-miss content does NOT raise AND survives serialization
    verbatim. Asserting BOTH halves rejects a "silent swallow" bug
    where the predicate fires but the handler logs+ignores it.

    Near-misses exercised (each on a distinct surface):
    - leading-space variant: ``" ==ATTACHMENTS==:"`` (predicate uses
      ``strip().startswith`` so this actually IS a collision — pulled
      out and a different near-miss substituted: the marker shape
      appears mid-line, not at line start).
    - prefix-only without trailing equals: ``"==BELEGMEISTER"`` (no
      closing ``==``, would not match any marker on round-trip).
    - case-shifted: ``"==attachments=="`` lowercase (the markers are
      uppercase by convention; 4a's predicate is case-sensitive via
      raw ``startswith``).
    """
    answer = (
        "Siehe Anhang ==ATTACHMENTS== für die Liste.\n"
        "Marker-Shape ==BELEGMEISTER ohne Schluss.\n"
        "==attachments== klein geschrieben."
    )
    doc = _make_doc(qa_pairs=(("Wie geht's?", answer),))

    # Half (a): no exception raised.
    wire = serialize_response_letter(doc)

    # Half (b): the near-miss content survives verbatim in the output.
    assert "Siehe Anhang ==ATTACHMENTS== für die Liste." in wire
    assert "Marker-Shape ==BELEGMEISTER ohne Schluss." in wire
    assert "==attachments== klein geschrieben." in wire


# --- S6 codec-level: filename verbatim with non-ASCII chars ---


def test_serializer_embeds_filename_verbatim_with_umlaut() -> None:
    """Phase-3 Seam S6 codec-level: a stored filename containing a
    German umlaut survives the serializer verbatim — NOT URL-escaped,
    NOT NFKD-normalized, NOT stripped. Catches an "I 'sanitized' the
    filename" regression that would break SB's ability to visually
    match the filename in DATEV-UO.

    The integration-level S6 (two-files-same-original UUID
    disambiguation) is in `tests/web/test_app_submit_inventory.py` and
    is UNIT 3's scope; this codec-level test is the unit-level
    companion.
    """
    stored = "_attachment_1185519_a1b2c3d4_Rechnung_Müller.pdf"
    doc = _make_doc(
        attachments=(
            _succeeded_attachment(
                original_filename="Rechnung_Müller.pdf", stored_filename=stored
            ),
        ),
    )

    wire = serialize_response_letter(doc)

    # Verbatim substring (umlaut intact, no escaping).
    assert stored in wire
    # Negative: no URL-encoded variant.
    assert "Rechnung_M%C3%BCller.pdf" not in wire
    assert "Rechnung_Mu%CC%88ller.pdf" not in wire
    # Negative: not stripped to ASCII.
    assert "Rechnung_Muller.pdf" not in wire


# --- S2 (regular-difficulty): failure_reason_from_klardaten_outcome ---
#
# Pure-function categorizer. Maps an exception raised during the
# klardaten attach call into one of the 4 stable category strings the
# response codec's ==FAILED_ATTACHMENTS== section consumes. Per
# ADR-0007: ``klardaten_4xx`` / ``klardaten_5xx`` / ``network_timeout``
# / ``other``.
#
# Tested in isolation (no HTTP layer). UNIT 3 wires it into the
# upload orchestrator's exception-handling branch.


def _http_status_error(status: int) -> httpx.HTTPStatusError:
    """Build a minimal ``HTTPStatusError`` with a given status code.
    The constructor needs both a `Request` and a `Response`; both can
    be synthetic since the categorizer reads only `response.status_code`.
    """
    request = httpx.Request("POST", "https://example.com/x")
    response = httpx.Response(status_code=status, request=request)
    return httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)


@pytest.mark.parametrize(
    ("exc", "expected_category"),
    [
        # 4xx status codes → klardaten_4xx (request-side problem).
        (_http_status_error(400), "klardaten_4xx"),
        (_http_status_error(404), "klardaten_4xx"),
        (_http_status_error(413), "klardaten_4xx"),
        # 5xx status codes → klardaten_5xx (server-side problem).
        (_http_status_error(500), "klardaten_5xx"),
        (_http_status_error(503), "klardaten_5xx"),
        # Timeout flavors → network_timeout.
        (httpx.ReadTimeout("read timeout"), "network_timeout"),
        (httpx.ConnectTimeout("connect timeout"), "network_timeout"),
        (httpx.WriteTimeout("write timeout"), "network_timeout"),
        # Other transport errors → other.
        (httpx.ConnectError("connect failed"), "other"),
        (httpx.RemoteProtocolError("garbage"), "other"),
        # Non-httpx surprises → other (defensive fallback).
        (ValueError("random non-httpx error"), "other"),
    ],
)
def test_failure_reason_from_klardaten_outcome(
    exc: BaseException, expected_category: str
) -> None:
    """S2: parametrized over the categorizer's expected outputs.

    Each input is a real exception instance (no mock library); the
    function reads `response.status_code` for HTTPStatusError and
    isinstance-checks for the timeout/transport variants. The "other"
    fallback catches both unhandled httpx branches AND non-httpx
    exception types — the orchestrator wraps the whole upload call
    so any surprise lands here, never escaping as a 500.
    """
    assert failure_reason_from_klardaten_outcome(exc) == expected_category
