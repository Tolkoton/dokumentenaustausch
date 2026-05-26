"""Unit tests for ``resolve_binder_guid_by_number``.

The resolver delegates filtering to klardaten's server-side ``filter``
query param (non-``$``-prefixed; see ADR-0003 for the wire-format
finding). These tests mock the document-lister and assert both the
return value and the ``list_documents`` call shape the resolver makes,
so a future regression to client-side scanning would surface as a
calls-list mismatch rather than a coincidence-pass.
"""

from __future__ import annotations

from typing import Any

import pytest

from belegmeister.datev.resolver import resolve_binder_guid_by_number


class _FakeLister:
    """Records every ``list_documents`` call and routes responses by
    ``filter`` value so a test can assert both 'what was asked' and
    'what came back'."""

    def __init__(
        self,
        *,
        on_filter: dict[str, list[dict[str, Any]]] | None = None,
        raise_on_call: Exception | None = None,
    ) -> None:
        self._on_filter = on_filter or {}
        self._raise = raise_on_call
        self.calls: list[dict[str, Any]] = []

    def list_documents(
        self,
        *,
        filter: str | None = None,  # noqa: A002 — wire-level param name
        top: int | None = None,
        skip: int | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append({"filter": filter, "top": top, "skip": skip})
        if self._raise is not None:
            raise self._raise
        if filter is None:
            return []
        return self._on_filter.get(filter, [])


def test_resolves_existing_vgm_via_server_side_filter() -> None:
    fake = _FakeLister(
        on_filter={
            "number eq 395357": [
                {
                    "number": 395357,
                    "id": "guid-395357",
                    "extension": "VGM",
                    "is_binder": True,
                }
            ],
        }
    )

    result = resolve_binder_guid_by_number(fake, 395357)

    assert result == "guid-395357"
    # call shape proves we did NOT page-walk
    assert fake.calls == [{"filter": "number eq 395357", "top": None, "skip": None}]


def test_resolves_second_known_vgm_395223() -> None:
    fake = _FakeLister(
        on_filter={
            "number eq 395223": [
                {
                    "number": 395223,
                    "id": "guid-395223",
                    "extension": "VGM",
                    "is_binder": True,
                }
            ],
        }
    )

    assert resolve_binder_guid_by_number(fake, 395223) == "guid-395223"


def test_absent_number_returns_none_with_a_single_call() -> None:
    fake = _FakeLister(on_filter={"number eq 999999999": []})

    result = resolve_binder_guid_by_number(fake, 999999999)

    assert result is None
    # exactly one wire call — no page-walk fallback hiding behind an empty page
    assert len(fake.calls) == 1


def test_filter_returns_non_vgm_doc_returns_none() -> None:
    """Same number could in principle be a non-VGM doc; the resolver
    refuses to silently return a non-binder GUID even when the server
    filter matched."""
    fake = _FakeLister(
        on_filter={
            "number eq 395357": [
                {
                    "number": 395357,
                    "id": "guid-other",
                    "extension": "PDF",
                    "is_binder": False,
                }
            ],
        }
    )

    assert resolve_binder_guid_by_number(fake, 395357) is None


def test_filter_returning_multiple_matches_raises_value_error() -> None:
    """klardaten enforces number uniqueness, so >1 result is a server
    contract violation — surfaced loudly, not silently picked."""
    fake = _FakeLister(
        on_filter={
            "number eq 395357": [
                {
                    "number": 395357,
                    "id": "guid-a",
                    "extension": "VGM",
                    "is_binder": True,
                },
                {
                    "number": 395357,
                    "id": "guid-b",
                    "extension": "VGM",
                    "is_binder": True,
                },
            ],
        }
    )

    with pytest.raises(ValueError, match="resolved to 2 items"):
        resolve_binder_guid_by_number(fake, 395357)


def test_match_without_string_id_returns_none() -> None:
    """Defensive: even if the server returns an id of an unexpected
    type, the resolver never returns a non-str — callers downstream
    embed it in a URL path."""
    fake = _FakeLister(
        on_filter={
            "number eq 395357": [
                {
                    "number": 395357,
                    "id": 12345,
                    "extension": "VGM",
                    "is_binder": True,
                }
            ],
        }
    )

    assert resolve_binder_guid_by_number(fake, 395357) is None
