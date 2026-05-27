"""Codec for the `_response_<letter_id>_<ISO>.txt` file: Mandant
answers + Anmerkungen + attachment inventory, in one human-readable,
machine-parseable file.

Symmetric counterpart of `belegmeister.request_format` (4a). This
slice (submit-handler) ships **serialize only**; parse / round-trip
is deferred (slice contract Phase 5 #13 — downstream consumers
needing parsing get their own slice).

Wire format (`response/v1`):

    ==BELEGMEISTER== response/v1
    Letter-Id: <letter_id>
    Submitted-At: <ISO 8601 UTC>

    ==ANTWORTEN==
    Q1: <question 1 text>
    A1: <answer 1, verbatim — may be empty>

    Q2: <question 2 text>
    A2: <answer 2, verbatim — may be empty>
    ==ANMERKUNGEN==
    <Mandant freeform Anmerkungen, multi-line allowed, verbatim>
    ==ATTACHMENTS==
    <stored_filename_1>
    <stored_filename_2>
    ==FAILED_ATTACHMENTS==
    <original_filename_X>: <failure_reason_X>
    ==BELEGMEISTER== end

All sections appear regardless of content (predictable parse surface
when round-trip is ever added). Empty sections are zero lines between
the surrounding markers.

Marker design (see slice contract D1 + ADR-0007):
- Version + end markers mirror 4a's ``==BELEGMEISTER==`` prefix shape.
- Section markers (``==ANTWORTEN==`` / ``==ANMERKUNGEN==`` /
  ``==ATTACHMENTS==`` / ``==FAILED_ATTACHMENTS==``) are BARE per the
  slice contract S4 fixture wording. The sentinel-collision predicate
  ``has_sentinel_collision`` is imported from
  ``belegmeister.request_format`` and called with the full marker
  tuple (`_RESPONSE_SENTINELS`) — one source of truth, both layers
  call it. NO copy-paste. Per CLAUDE.md "Single source of truth for
  cross-layer logic" and MEMORY[feedback_cross_layer_validation_extract].

Collision-proof by construction: any user-supplied surface (answer,
Anmerkungen, attachment filename) is checked against the full marker
tuple before serialization. The codec rejects rather than escapes —
the wire is unambiguous without the parser ever having to disambiguate.

This module does NOT:
- read/write files or talk to klardaten (caller does the I/O);
- categorize klardaten errors into `failure_reason` strings (that
  function — `failure_reason_from_klardaten_outcome` — is UNIT 3
  scope, lives here after that unit);
- render anything HTML (submit_confirmation.html is the renderer).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import httpx

from belegmeister.request_format import SENTINEL_PREFIX, has_sentinel_collision

_VERSION_MARKER = f"{SENTINEL_PREFIX} response/v1"
_END_MARKER = f"{SENTINEL_PREFIX} end"
_ANTWORTEN_MARKER = "==ANTWORTEN=="
_ANMERKUNGEN_MARKER = "==ANMERKUNGEN=="
_ATTACHMENTS_MARKER = "==ATTACHMENTS=="
_FAILED_ATTACHMENTS_MARKER = "==FAILED_ATTACHMENTS=="

# Every user-supplied surface (answer / Anmerkungen / filename) is
# checked against this tuple. Includes the shared ``==BELEGMEISTER==``
# prefix so a Mandant pasting ``==BELEGMEISTER== fragen`` (a 4a
# request-side marker) into an answer cell is also rejected — defense
# spans both codecs' marker vocabularies.
_RESPONSE_SENTINELS: tuple[str, ...] = (
    SENTINEL_PREFIX,
    _ANTWORTEN_MARKER,
    _ANMERKUNGEN_MARKER,
    _ATTACHMENTS_MARKER,
    _FAILED_ATTACHMENTS_MARKER,
)


@dataclass(frozen=True)
class AttachmentOutcome:
    """Per-file outcome record. Populated by the UNIT 3 file-upload
    loop and consumed by this codec's serializer.

    Invariant (caller's responsibility — codec trusts but does not
    enforce): if ``status == "succeeded"`` then ``stored_filename``,
    ``structure_item_id``, and ``document_file_id`` are all non-None
    and ``failure_reason`` is None; if ``status == "failed"`` the
    inverse. UNIT 3's construction site enforces this; this dataclass
    accepts both shapes so test fixtures can build either side easily.

    See ADR-0007 for the full schema rationale and the
    ``failure_reason`` category vocabulary (``"klardaten_4xx"`` /
    ``"klardaten_5xx"`` / ``"network_timeout"`` / ``"other"``).
    """

    original_filename: str
    stored_filename: str | None
    structure_item_id: str | None
    document_file_id: int | None
    status: Literal["succeeded", "failed"]
    failure_reason: str | None
    elapsed_s: float


@dataclass(frozen=True)
class ResponseDocument:
    """The full input to the response-letter serializer.

    Fields:
        letter_id: The structure-item id of the original
            ``_request_letter_*.txt`` the Mandant was responding to.
            Comes from the token payload's ``letter_id`` (per
            token-instance-binding slice). Server-generated; not
            user-controlled; no sentinel check applied.
        submitted_at: Wall-clock UTC at which the handler started
            processing the POST. Server-generated; serialized via
            ``isoformat()`` for portability.
        qa_pairs: Ordered tuple of ``(question_text, answer_text)``.
            Position is meaningful (Q1 / A1 / Q2 / A2 / …). Empty
            answers are valid (Mandant skipped a question, per slice
            4 design point 3 "all questions optional"). Question text
            comes from the parsed request letter and is also sentinel-
            checked here as defense-in-depth.
        anmerkungen: Mandant's freeform Anmerkungen field. May be the
            empty string. Multi-line allowed; embedded newlines
            preserved verbatim.
        attachments: Ordered tuple of per-file outcomes. May be empty
            (answers-only / Anmerkungen-only submit, per D6's
            ``files_attempted == 0`` branch). Mixed succeeded /
            failed allowed (D6 partial-success branch).
    """

    letter_id: str
    submitted_at: datetime
    qa_pairs: tuple[tuple[str, str], ...]
    anmerkungen: str
    attachments: tuple[AttachmentOutcome, ...]


class ResponseLetterMalformed(Exception):
    """A ``ResponseDocument`` cannot be safely serialized (sentinel
    collision on some user-supplied surface). Message embeds the
    field name so a single log line is self-describing — same pattern
    as ``RequestLetterMalformed`` and ``InvalidUploadTarget``.

    POST-side error taxonomy (per ADR-0007 + slice contract D4):
    this exception is raised at the codec layer. The handler in
    ``web/app.py`` catches it and maps to
    ``RequestSubmitFailed(log_reason="upload_failed_response_doc")``
    on the unlikely path where Mandant input passed every prior guard
    yet still trips a sentinel here (typically: an
    SB-typed question containing a marker that wasn't checked in
    request-creation).
    """

    def __init__(self, *, reason: str) -> None:
        self.reason = reason
        super().__init__(f"malformed response letter: {reason}")


def _reject_sentinel(field: str, value: str) -> None:
    """Codec guard wrapping the shared ``has_sentinel_collision``
    predicate with the response-codec's full marker tuple."""
    if has_sentinel_collision(value, sentinel_prefixes=_RESPONSE_SENTINELS):
        raise ResponseLetterMalformed(
            reason=f"{field} contains a line starting with a forbidden marker"
        )


def serialize_response_letter(doc: ResponseDocument) -> str:
    """Serialize a ``ResponseDocument`` into the on-wire ``response/v1``
    text.

    Defensive-by-construction: every user-supplied surface (each
    question text, each answer, Anmerkungen, each attachment's
    original AND stored filename, each attachment's failure_reason)
    is checked against the response-codec's sentinel tuple before any
    bytes are assembled. The flow is validate-all → assemble — if any
    field collides, no partial output is produced. Sentinel-checking
    on server-generated fields (``letter_id``, ``submitted_at``,
    ``failure_reason``) is omitted by design (server vocabulary is
    controlled).

    Args:
        doc: The fully-populated response document.

    Returns:
        The complete file content as a single ``str`` ending in ``"\\n"``
        (canonical LF line-ending, regardless of the producer's
        platform).

    Raises:
        ResponseLetterMalformed: With ``reason`` naming the first
            offending field. Specifically:

            * ``"question N contains a line starting with a forbidden marker"``
            * ``"answer N contains a line starting with a forbidden marker"``
            * ``"anmerkungen contains a line starting with a forbidden marker"``
            * ``"attachment original_filename contains …"``
            * ``"attachment stored_filename contains …"``
    """
    # Validate all user-supplied surfaces before assembling. Field
    # names in the rejection reason use 1-based indexing for human
    # ergonomics (matches the on-wire Q1/A1/Q2/A2 numbering).
    for i, (question, answer) in enumerate(doc.qa_pairs, start=1):
        _reject_sentinel(f"question {i}", question)
        _reject_sentinel(f"answer {i}", answer)
    _reject_sentinel("anmerkungen", doc.anmerkungen)
    for att in doc.attachments:
        _reject_sentinel("attachment original_filename", att.original_filename)
        if att.stored_filename is not None:
            _reject_sentinel("attachment stored_filename", att.stored_filename)

    # Assemble. Build each section's lines, then join with "\n" and
    # append the canonical trailing newline.
    lines: list[str] = [
        _VERSION_MARKER,
        f"Letter-Id: {doc.letter_id}",
        f"Submitted-At: {doc.submitted_at.isoformat()}",
        "",
        _ANTWORTEN_MARKER,
    ]
    for i, (question, answer) in enumerate(doc.qa_pairs, start=1):
        lines.append(f"Q{i}: {question}")
        lines.append(f"A{i}: {answer}")
        # Blank-line separator between Q/A pairs (but not after the
        # last pair — that flows directly into the ==ANMERKUNGEN==
        # marker for compact wire shape per the anchor test).
        if i < len(doc.qa_pairs):
            lines.append("")
    lines.append(_ANMERKUNGEN_MARKER)
    if doc.anmerkungen:
        lines.append(doc.anmerkungen)
    lines.append(_ATTACHMENTS_MARKER)
    succeeded = [a for a in doc.attachments if a.status == "succeeded"]
    for att in succeeded:
        # Invariant: succeeded → stored_filename is non-None. Codec
        # treats violation as a developer bug rather than a runtime
        # exception (assertion in case of future shape drift).
        assert att.stored_filename is not None
        lines.append(att.stored_filename)
    lines.append(_FAILED_ATTACHMENTS_MARKER)
    failed = [a for a in doc.attachments if a.status == "failed"]
    for att in failed:
        # `failure_reason` may be None in malformed inputs; surface
        # it as the literal string "None" rather than crashing — the
        # codec's job is to produce output, the categorization
        # function's job is to ensure the value is meaningful.
        reason = att.failure_reason if att.failure_reason is not None else "unknown"
        lines.append(f"{att.original_filename}: {reason}")
    lines.append(_END_MARKER)

    return "\n".join(lines) + "\n"


# Failure-reason category vocabulary per ADR-0007. The UNIT 3 upload
# orchestrator catches every exception the klardaten attach call can
# raise and pipes it through this function to produce the inventory
# entry's `failure_reason` string. Stable strings (consumed by SB
# diagnostic eyeballs in the response doc's ==FAILED_ATTACHMENTS==
# section); changing the spelling is a contract break.
FailureReason = Literal[
    "klardaten_4xx",
    "klardaten_5xx",
    "network_timeout",
    "other",
]


def failure_reason_from_klardaten_outcome(exc: BaseException) -> FailureReason:
    """Categorize an exception raised by a klardaten upload call.

    Maps the exception's type/status into one of the four ADR-0007
    categories. Pure function: no I/O, no side effects, no logging.

    Categorization rules (in order):

    1. ``httpx.HTTPStatusError`` with 4xx response → ``"klardaten_4xx"``.
       Request-side problem — the SB / Mandant input is the likely
       cause (oversized file, malformed payload, auth header issue).
       Retry won't help.
    2. ``httpx.HTTPStatusError`` with 5xx response → ``"klardaten_5xx"``.
       Server-side problem at the gateway. Retry MAY help.
    3. ``httpx.TimeoutException`` (covers Read/Connect/Write/Pool)
       → ``"network_timeout"``. Transport-level slowness; usually
       retry-able if Mandant has bandwidth.
    4. Any other exception → ``"other"``. Catches both unhandled
       httpx branches (ConnectError, RemoteProtocolError, etc.) AND
       non-httpx surprises. The orchestrator wraps the whole upload
       call so nothing escapes uncategorized.

    Args:
        exc: The exception instance the orchestrator caught.

    Returns:
        One of the four `FailureReason` strings. The codec embeds
        this verbatim into the response doc's `==FAILED_ATTACHMENTS==`
        section after the ``: `` separator.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if 400 <= status < 500:
            return "klardaten_4xx"
        if 500 <= status < 600:
            return "klardaten_5xx"
        return "other"
    if isinstance(exc, httpx.TimeoutException):
        return "network_timeout"
    return "other"
