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
    """Resolve a DATEV Dokumentnummer (UI integer) to a klardaten document GUID.

    Pages through ``GET /datevconnect/dms/v2/documents`` via the injected
    client's ``list_documents(top=, skip=)`` until a document with the
    matching ``number`` field is found, the listing runs out, or the page
    cap is reached. There is no server-side filter to lean on — see
    ADR-0001 (``docs/adr/0001-resolver-perf-persisted-index.md``):
    ``$filter=number eq X``, ``?number=X``, and by-number path routes are
    all silently ignored by klardaten's documents endpoint, and ``$top``
    is ignored too (the page is fixed at 1000). Settled empirically by
    ``scripts/spike_direct_lookup_2026-05-19.py``; do not re-probe.

    Worst-case behavior follows directly: a not-found result requires
    walking ``page_size * max_pages`` records sequentially (~45 s and
    growing on production data, per ADR-0001). The slice-4b form
    surfaces this via the "VGM-Nummer nicht gefunden" message; a
    persisted SQLite index will replace this function entirely, but
    until then the synchronous scan IS the resolve path.

    Args:
        klardaten_client: Any object implementing
            ``list_documents(*, top: int, skip: int) -> list[dict[str, Any]]``
            (the ``_DocLister`` Protocol). In production a
            ``KlardatenClient``; in tests a fake.
        number: The Dokumentnummer the SB typed into the form (a
            positive integer in DATEV's UI). Compared to each entry's
            ``"number"`` field using ``==``.
        page_size: ``$top`` value sent to klardaten; effectively
            ignored by the server (response is always 1000 entries), but
            kept as a parameter so a future server with real pagination
            can be exercised without a signature change.
        max_pages: Cap on how many pages to walk before giving up. With
            the defaults the scan looks at up to 50 000 records — large
            enough for current DATEV instances but bounded so a
            mis-configured run cannot loop indefinitely.

    Returns:
        The matching document's ``id`` as a ``str`` (the GUID expected
        by ``upload_to_binder`` and the resolver-using web surfaces),
        or ``None`` when no document with the given number was seen
        within the scan window. ``None`` is the "not found" signal the
        caller renders as "VGM-Nummer ... wurde in DATEV nicht
        gefunden".

    Side effects:
        Makes up to ``max_pages`` synchronous ``GET`` requests to
        klardaten. Each call is bounded by the client's own per-request
        timeout (the default ``KlardatenClient.timeout`` of 30 s); the
        total wall-clock is unbounded by this function. No mutation, no
        local I/O.
    """
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
