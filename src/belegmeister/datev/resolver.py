"""Resolve a DATEV Dokumentnummer (UI-visible integer) to a GUID.

Single-call server-side filter. The klardaten gateway accepts OData
semantics **without** the ``$`` prefix — ``filter=number eq <N>`` is
honored; ``$filter=number eq <N>`` is silently ignored. The earlier
page-walking implementation was built on the misread that direct
lookup did not exist (ADR-0001, since superseded); the new ground
truth is recorded in ADR-0003.

Kept deliberately separate from upload: "find the target" and "act on
the target" are two concerns and should not be braided together.
"""

from __future__ import annotations

from typing import Any, Protocol


class _DocLister(Protocol):
    """Structural type for the server-side filter capability."""

    def list_documents(
        self,
        *,
        filter: str | None = ...,  # noqa: A002 — wire-level param name
    ) -> list[dict[str, Any]]: ...


def resolve_binder_guid_by_number(
    klardaten_client: _DocLister,
    doknum: int,
) -> str | None:
    """Resolve a DATEV Dokumentnummer (UI integer) to a klardaten GUID.

    One wire call: ``GET /datevconnect/dms/v2/documents?filter=number eq <doknum>``.
    The server returns 0 or 1 matching record (numbers are unique).
    A non-VGM hit yields ``None`` — the function refuses to surface a
    GUID that ``upload_to_binder`` would then reject for not being a
    Vorgangsmappe.

    Args:
        klardaten_client: Any object implementing
            ``list_documents(*, filter: str | None = ...) -> list[dict[str, Any]]``
            (the ``_DocLister`` Protocol). In production a
            ``KlardatenClient``; in tests a fake.
        doknum: The Dokumentnummer the SB typed into the form (a
            positive integer in DATEV's UI). Embedded into the OData
            ``number eq <doknum>`` filter expression verbatim.

    Returns:
        The matching Vorgangsmappe's ``id`` as a ``str`` (the GUID
        expected by ``upload_to_binder`` and the resolver-using web
        surfaces). ``None`` when no document matches, or when the match
        is not a Vorgangsmappe, or when the server response lacks a
        usable string id. ``None`` is the "not found" signal the caller
        renders as "VGM-Nummer ... wurde in DATEV nicht gefunden".

    Raises:
        ValueError: When the server returns more than one matching
            document. Numbers are unique in DATEV, so >1 is a server
            contract violation worth surfacing rather than silently
            picking the first.

    Side effects:
        Makes one synchronous ``GET`` request to klardaten, bounded by
        the client's per-request timeout (default 30 s). No mutation,
        no local I/O.
    """
    docs = klardaten_client.list_documents(filter=f"number eq {doknum}")
    if not docs:
        return None
    if len(docs) > 1:
        raise ValueError(f"Dokumentnummer {doknum} resolved to {len(docs)} items")
    doc = docs[0]
    if doc.get("extension") != "VGM" or not doc.get("is_binder"):
        return None
    guid = doc.get("id")
    if not isinstance(guid, str) or not guid:
        return None
    return guid
