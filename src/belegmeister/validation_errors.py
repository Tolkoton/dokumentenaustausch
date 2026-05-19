"""Shared presentation of a Pydantic `ValidationError` for
`CreateRequestArgs`.

Single source of truth (CLAUDE.md "Single source of truth for cross-layer
logic"): the CLI surface (`belegmeister.__main__`) renders these as a flat
stderr block; the SB web surface (`belegmeister.sb.app`) groups them per
form field. Both consume `validation_error_items`, so the
`loc -> message` traversal lives in exactly one place and cannot drift
between the two layers.

No I/O, no env reads — a pure transformation, unit-testable in isolation.
"""

from __future__ import annotations

from pydantic import ValidationError


def validation_error_items(exc: ValidationError) -> list[tuple[str, str]]:
    """Flatten a `ValidationError` into ``(dotted_loc, message)`` pairs.

    ``loc`` is dotted (e.g. ``"questions.2"``) so a caller can route a
    message to a specific field/index; an empty ``loc`` becomes
    ``"<root>"``.
    """
    items: list[tuple[str, str]] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        items.append((loc, err["msg"]))
    return items
