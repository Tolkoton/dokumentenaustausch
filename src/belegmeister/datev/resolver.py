"""Resolve a DATEV Dokumentnummer (UI-visible integer) to a GUID.

Kept deliberately separate from upload: "find the target" and "act on the
target" are two concerns and should not be braided together.

The klardaten gateway's `$filter`/`?number=` syntax is undocumented and was
empirically observed to be ignored (the server returns the unfiltered page).
Until the right filter shape is found, the resolver paginates and scans
in-memory. The `max_pages` bound keeps the worst case finite.
"""

from __future__ import annotations

from typing import Any, Protocol


class _DocLister(Protocol):
    """Structural type for the document-listing capability."""

    def list_documents(self, *, top: int, skip: int) -> list[dict[str, Any]]: ...


def resolve_binder_guid_by_number(
    klardaten_client: _DocLister,
    number: int,
    *,
    page_size: int = 1000,
    max_pages: int = 50,
) -> str | None:
    """Return the GUID of the doc with `number`, or None if not found within
    `page_size * max_pages` records."""
    skip = 0
    for _ in range(max_pages):
        page = klardaten_client.list_documents(top=page_size, skip=skip)
        if not page:
            return None
        for entry in page:
            if entry.get("number") == number:
                guid = entry.get("id")
                if isinstance(guid, str) and guid:
                    return guid
        if len(page) < page_size:
            return None
        skip += page_size
    return None
