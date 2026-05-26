"""Regression guard for the shared `validation_error_items` extractor
and the CLI's `_format_validation_error` wrapper.

The extraction (inline loop in `__main__` -> shared
`validation_errors.validation_error_items`, also consumed by
`belegmeister.sb.app`) MUST be byte-identical at the CLI surface. This
is proven here, not assumed: a controlled multi-field `ValidationError`
is rendered and pinned.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from belegmeister.__main__ import _format_validation_error
from belegmeister.cli.create_request import CreateRequestArgs
from belegmeister.validation_errors import validation_error_items

_NOW = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)


def _multi_field_error() -> ValidationError:
    """A submission bad in a top-level field AND with a per-item type
    failure in the list, so BOTH the single-element loc (`("to",)`) and
    a genuine multi-element loc (`("questions", 0)`) are produced — the
    latter is what exercises the dotted-join the extraction carried over.

    Note: the 4a *domain* questions validator (`_clean_questions`)
    validates the whole list and raises `ValueError("question N ...")`,
    so a sentinel-collision / multi-line question yields loc
    `("questions",)` with the index only in the message (blank entries
    drop silently and never raise). A multi-element loc requires a
    per-ITEM failure — here a non-str item (`123`) tripping `list[str]`
    coercion.
    """
    with pytest.raises(ValidationError) as ei:
        CreateRequestArgs.model_validate(
            {
                "vgm_id": "v",
                "to": "",  # blank -> single-element loc ("to",)
                "cc": "",
                "subject": "S",
                "body": "real body",
                "questions": [123],  # non-str -> loc ("questions", 0)
                "expires_at": _NOW.replace(year=2026, month=5, day=26),
            },
            context={"now": _NOW},
        )
    return ei.value


def test_VE1_extractor_dots_nested_index() -> None:
    """The behavior that actually moved: a multi-element loc is dotted
    (`questions.0`); a single-element loc stays bare (`to`). This
    `'.'.join(...)` is the only logic the extraction carried over from
    the old inline loop."""
    items = dict(validation_error_items(_multi_field_error()))

    assert "to" in items
    assert "questions.0" in items
    assert "must not be blank" in items["to"]


def test_VE2_cli_format_is_extractor_wrapped_byte_identical() -> None:
    """`_format_validation_error` is exactly the header + one
    `"  - {loc}: {msg}"` line per extractor item, in order — proving the
    refactor did not alter the CLI's stderr bytes."""
    exc = _multi_field_error()

    expected = "invalid arguments:\n" + "\n".join(
        f"  - {loc}: {msg}" for loc, msg in validation_error_items(exc)
    )

    assert _format_validation_error(exc) == expected
