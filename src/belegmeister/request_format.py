"""Codec for the `_request_letter_<ISO>.txt` file: email metadata + letter
body + client questions, in one human-readable, machine-parseable file.

A codec is serialize + parse as ONE logical unit. The serializer is
untestable in isolation (a string-match in a vacuum); only the
round-trip property `parse(serialize(x)) == x` proves the format is
whole — it catches data loss, serializer/parser drift, and sentinel
collisions.

Wire format (`request/v1`):

    ==BELEGMEISTER== request/v1
    To: client@example.com
    Cc:
    Subject: Unterlagen für Steuererklärung 2025

    <letter body — free text, multi-line, markdown OK, verbatim>
    ==BELEGMEISTER== fragen
    Erste Frage an den Mandanten
    Zweite Frage
    ==BELEGMEISTER== end

Collision-proof by construction: the form is the ONLY serializer, and
it (plus this module, defensively) rejects any input line whose stripped
form starts with the sentinel prefix `==BELEGMEISTER==`. The SB therefore
cannot inject a marker even by typing `## Fragen` or the marker itself.

Parse rules:
- line 1 must equal the exact version marker. A structurally-valid
  sentinel with a DIFFERENT version (e.g. `request/v2`) is rejected
  with an explicit "unknown version" reason — versioning is verified,
  not decorative (a v2 file must never silently misparse as v1).
- `To:` / `Cc:` / `Subject:` headers until the first blank line;
  value = everything after the FIRST colon, stripped. A duplicate
  header line is rejected (header-injection via duplicates is the same
  threat class as embedded-newline injection).
- `==BELEGMEISTER== fragen` and `==BELEGMEISTER== end` must each
  appear EXACTLY ONCE (`count != 1` -> reject). This is symmetric to
  serialize (which emits exactly one of each) and is a single
  structural invariant covering both "marker absent" (count 0) and
  "marker injected inside body" (count 2). `parse` is a separate,
  hostile input path (corrupted file / manual DATEV edit / attack) —
  the serialize-side sentinel guard does NOT protect it; this does.
- body = text between the blank line and the (sole) `... fragen`
  line; its first `""` line is the header/body separator, blank
  lines AFTER it are verbatim body content
- questions = non-empty lines between `... fragen` and `... end`,
  one per line; zero lines = no questions (valid)

Codec-local decision (independent of any caller): an empty or
whitespace-only `body` is rejected by `serialize_request_letter`
(`RequestLetterMalformed`). `CreateRequestArgs` also enforces
`min_length=1`, but the codec owns its own integrity.

This module does NOT:
- read/write files or talk to DATEV (caller does the I/O)
- validate email syntax (the form / `CreateRequestArgs` owns input
  validation; this module only guards format integrity)
- render anything for the client (`/r/{token}` render is a later slice
  and will consume `parse_request_letter`)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SENTINEL_PREFIX = "==BELEGMEISTER=="
_VERSION_MARKER = f"{SENTINEL_PREFIX} request/v1"
_FRAGEN_MARKER = f"{SENTINEL_PREFIX} fragen"
_END_MARKER = f"{SENTINEL_PREFIX} end"

# A "sane" version token: short, alnum + slash only. Used to decide
# whether line 1 is a *recognizable* version marker whose token may be
# safely echoed into an error (B13) vs. hostile garbage that must NOT
# be quoted into logs (B9).
_VERSION_LINE_RE = re.compile(rf"^{re.escape(SENTINEL_PREFIX)} ([A-Za-z0-9/]{{1,20}})$")


@dataclass(frozen=True)
class RequestLetter:
    """A fully-validated request letter. Values are clean by contract:
    no leading/trailing whitespace, no embedded newline in headers, no
    line colliding with the sentinel prefix. `CreateRequestArgs` is the
    user-facing gate that produces these; this codec defensively
    re-checks so it is sound when used independently."""

    to: str
    cc: str  # "" allowed
    subject: str
    body: str
    questions: tuple[str, ...]  # () allowed


class RequestLetterMalformed(Exception):
    """The bytes are not a well-formed `request/v1` file, or a
    `RequestLetter` cannot be safely serialized (sentinel collision /
    header newline). Message embeds the reason so a single log line is
    self-describing (same pattern as `InvalidUploadTarget`)."""

    def __init__(self, *, reason: str) -> None:
        self.reason = reason
        super().__init__(f"malformed request letter: {reason}")


# --- Shared predicates: ONE source of truth for cross-layer rules. ---
# Both the codec guards below AND `CreateRequestArgs` validators call
# these; each layer wraps a failure in its own exception type. See
# CLAUDE.md "Single source of truth for cross-layer logic". Do not
# re-implement these checks anywhere else.


def is_single_line(value: str) -> bool:
    """True iff `value` is one physical line. Catches \\n, \\r\\n AND
    bare \\r (Windows SB box + copy-paste from old Mac / mangled
    sources) — `\\n`/`\\r` membership covers all three."""
    return "\n" not in value and "\r" not in value


def has_sentinel_collision(value: str) -> bool:
    """True iff any line of `value` (stripped) starts with the sentinel
    prefix — such a line would let a crafted file misparse on the way
    back through `parse_request_letter`."""
    return any(line.strip().startswith(SENTINEL_PREFIX) for line in value.split("\n"))


def is_blank(value: str) -> bool:
    """True iff `value` is empty or whitespace-only."""
    return value.strip() == ""


def _reject_sentinel_collision(field: str, value: str) -> None:
    """Codec guard wrapping `has_sentinel_collision`.

    Applied to `body` ONLY by design. Headers (to/cc/subject) need no
    sentinel check: `_reject_header_newline` makes it structurally
    impossible for a header value to become its own line, so it cannot
    become an injected marker. The newline guard IS the header sentinel
    guard, for free — do not add a redundant sentinel check on headers.
    """
    if has_sentinel_collision(value):
        raise RequestLetterMalformed(
            reason=f"{field} contains a line starting with {SENTINEL_PREFIX!r}"
        )


def _reject_header_newline(field: str, value: str) -> None:
    """Codec guard wrapping `is_single_line`. See
    `_reject_sentinel_collision`: a single-line header also
    transitively closes header sentinel injection."""
    if not is_single_line(value):
        raise RequestLetterMalformed(
            reason=f"{field} must be a single line (contains a newline/CR)"
        )


def _reject_empty_body(value: str) -> None:
    """Codec guard wrapping `is_blank` — codec-local decision that an
    empty/whitespace-only body is not a valid request letter,
    independent of any caller."""
    if is_blank(value):
        raise RequestLetterMalformed(reason="body is empty or whitespace-only")


def serialize_request_letter(letter: RequestLetter) -> str:
    """RequestLetter -> wire text. Raises RequestLetterMalformed if the
    value object carries a sentinel-colliding line, a header newline, or
    an empty body (defense in depth; the form should have rejected it
    first). Flow: validate -> assemble."""
    _reject_header_newline("to", letter.to)
    _reject_header_newline("cc", letter.cc)
    _reject_header_newline("subject", letter.subject)
    _reject_empty_body(letter.body)
    _reject_sentinel_collision("body", letter.body)
    lines = [
        _VERSION_MARKER,
        f"To: {letter.to}",
        f"Cc: {letter.cc}",
        f"Subject: {letter.subject}",
        "",
        letter.body,
        _FRAGEN_MARKER,
        *letter.questions,
        _END_MARKER,
    ]
    return "\n".join(lines) + "\n"


def _verify_version(line1: str) -> None:
    """Three-state version gate. Exact `request/v1` -> OK. Structurally
    valid sentinel + sane token but other version -> quote the token
    ('unknown version: X'). Anything else (garbage, empty, oversized,
    other text) -> generic reason WITHOUT echoing hostile raw input."""
    if line1 == _VERSION_MARKER:
        return
    match = _VERSION_LINE_RE.match(line1)
    if match is not None:
        raise RequestLetterMalformed(reason=f"unknown version: {match.group(1)}")
    raise RequestLetterMalformed(reason="missing or unrecognizable version marker")


def _verify_marker_counts(lines: list[str]) -> None:
    """Guard: `fragen` and `end` markers must each appear EXACTLY ONCE.
    Runs BEFORE any `.index()` so a missing marker (count 0) or an
    injected one (count 2, e.g. inside body) is a clean domain error,
    never a bare ValueError."""
    for marker, name in ((_FRAGEN_MARKER, "fragen"), (_END_MARKER, "end")):
        count = lines.count(marker)
        if count != 1:
            raise RequestLetterMalformed(
                reason=f"{name} marker must appear exactly once (found {count})"
            )


def _verify_separator(lines: list[str]) -> None:
    """Guard: a header/body separator (blank line) must exist. Runs
    BEFORE `lines.index("")` so a separator-less file is a clean domain
    error, not a bare ValueError."""
    if "" not in lines:
        raise RequestLetterMalformed(
            reason="missing header/body separator (blank line)"
        )


def _verify_marker_order(lines: list[str]) -> tuple[int, int, int]:
    """Guard + locate: structural sections must be in order
    `0 < sep < fragen < end`. Runs AFTER counts+separator (all three
    indices proven to exist exactly once), so this is pure index
    comparison. Closes the silent-misparse class: out-of-order markers
    return a wrong RequestLetter with no exception otherwise.

    Returns the validated `(sep_idx, fragen_idx, end_idx)` so `parse`
    does not re-scan — a guard that returns its proven value, not one
    that only raises-or-stays-silent."""
    sep_idx = lines.index("")
    fragen_idx = lines.index(_FRAGEN_MARKER)
    end_idx = lines.index(_END_MARKER)
    if not sep_idx < fragen_idx:
        raise RequestLetterMalformed(
            reason="header/body separator must precede the fragen marker"
        )
    if not fragen_idx < end_idx:
        raise RequestLetterMalformed(
            reason="end marker must come after the fragen marker (end before fragen)"
        )
    return sep_idx, fragen_idx, end_idx


def parse_request_letter(text: str) -> RequestLetter:
    """Wire text -> RequestLetter. Inverse of serialize_request_letter.
    Raises RequestLetterMalformed on any structural defect."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]  # drop the trailing-newline artifact
    if not lines:
        raise RequestLetterMalformed(reason="missing or unrecognizable version marker")

    _verify_version(lines[0])
    _verify_marker_counts(lines)
    _verify_separator(lines)
    sep_idx, fragen_idx, end_idx = _verify_marker_order(lines)

    headers: dict[str, str] = {}
    for line in lines[1:sep_idx]:
        key, _, value = line.partition(":")
        key = key.strip()
        if key in headers:
            raise RequestLetterMalformed(reason=f"duplicate header: {key}")
        headers[key] = value.strip()

    body = "\n".join(lines[sep_idx + 1 : fragen_idx])
    questions = tuple(q for q in lines[fragen_idx + 1 : end_idx] if q != "")

    return RequestLetter(
        to=headers.get("To", ""),
        cc=headers.get("Cc", ""),
        subject=headers.get("Subject", ""),
        body=body,
        questions=questions,
    )
