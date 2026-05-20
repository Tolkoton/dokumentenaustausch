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
    """Flatten a Pydantic ``ValidationError`` into ``(dotted_loc, message)`` pairs.

    Both the CLI and the SB web surface consume this — the CLI emits one
    line per item to stderr; the SB form groups items by the leading
    ``loc`` segment to put each message next to its field. Keeping the
    traversal in one place means a future Pydantic upgrade (which may
    change ``ValidationError.errors()`` shape) needs to land in exactly
    one file, not two, and the two layers cannot drift on which message
    a given input produces.

    Args:
        exc: A ``pydantic.ValidationError`` raised by validating a model
            in this project (in practice
            ``belegmeister.cli.create_request.CreateRequestArgs``).

    Returns:
        A list of ``(loc, msg)`` tuples preserving the original error
        order. ``loc`` is a dot-joined path through the model (e.g.
        ``"questions.2"`` for the third entry of the ``questions`` list);
        the root-level error (empty ``loc`` tuple) is rendered as
        ``"<root>"`` so consumers never produce an empty field label.
        ``msg`` is the human Pydantic message, unmodified.
    """
    items: list[tuple[str, str]] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        items.append((loc, err["msg"]))
    return items
