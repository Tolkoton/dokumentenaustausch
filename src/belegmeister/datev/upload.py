"""Upload a file *into* a DATEV DMS binder (Vorgangsmappe) via klardaten.

Seam: `upload_to_binder(file_path, binder_guid, klardaten_client) -> UploadResult`.

The function validates that `binder_guid` actually refers to a Vorgangsmappe
(empirically: `is_binder == True` AND `extension == "VGM"`) before touching
any bytes. If the target is invalid, `InvalidUploadTarget` is raised with
the target id and reason in the message — operational logs see the failure
without needing to read the traceback.

This slice does NOT:
- resolve binder Dokumentnummer (UI-visible integer) to a GUID — see
  `belegmeister.datev.resolver`.
- enforce binder state rules. DATEV's API accepts attaches to
  `offen`/`erledigt`/`in Bearbeitung` binders alike. Refusing closed
  binders would be a business rule layered on top; deferred to a future
  slice as an explicit opt-in.
- verify presence after upload, retry, generate filenames, read .env,
  or emit structured logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx


class InvalidUploadTarget(Exception):
    """The given binder_guid is not usable as an upload target.

    The message embeds both the target id and the rejection reason so a single
    log line is self-describing.
    """

    def __init__(self, binder_guid: str, reason: str) -> None:
        self.binder_guid = binder_guid
        self.reason = reason
        super().__init__(f"Upload target {binder_guid} rejected: {reason}")


@dataclass(frozen=True)
class UploadResult:
    """Outcome of an ``upload_to_binder`` call.

    A non-exception failure carrier for transient / business problems
    where the caller still wants a structured value (HTTP 5xx, transport
    error, unexpected response shape). Exception-worthy programmer or
    operator errors — file missing, target is not a Vorgangsmappe — are
    raised via ``InvalidUploadTarget`` and do NOT come back here.

    Attributes:
        success: ``True`` only when the file landed and DATEV returned
            a usable structure-item id; ``False`` otherwise.
        document_id: The freshly-created structure-item id (the handle
            inside DATEV's DMS) on success; ``None`` on any failure.
        error: A short human-readable failure description on
            ``success=False``; ``None`` on success. Includes an HTTP
            status (when one is available) and a truncated response
            excerpt so operational logs are self-describing.
    """

    success: bool
    document_id: str | None
    error: str | None


class BinderClient(Protocol):
    """Structural type for the injected client.

    Public so other modules (e.g. `belegmeister.cli.create_request`) can
    type their own DI seams against the same shape without duplicating
    the protocol or depending on the concrete `KlardatenClient`.
    """

    def get_document(self, guid: str) -> dict[str, Any]: ...

    def attach_file_to_binder(
        self, *, binder_guid: str, file_name: str, file_bytes: bytes
    ) -> dict[str, Any]: ...


def upload_to_binder(
    file_path: Path,
    binder_guid: str,
    klardaten_client: BinderClient,
) -> UploadResult:
    """Attach a local file as a child structure-item of a DATEV Vorgangsmappe.

    Performs, in order: existence/regular-file checks on ``file_path``;
    a ``GET /datevconnect/dms/v2/documents/{guid}`` to fetch the
    candidate target; the Vorgangsmappe predicate
    (``is_binder is True`` AND ``extension == "VGM"``); then the
    two-call attach (``POST /document-files`` for the bytes, then
    ``POST /documents/{guid}/structure-items`` for the type=1
    structure-item — both inside ``klardaten_client``). The full flow
    is hidden behind one public method; the seam stays one method even
    though the wire is two HTTP calls.

    The boundary between "raises" and "returns ``UploadResult(success=
    False)``" is deliberate: programmer/operator errors that cannot
    succeed on retry (missing file, target is not a Vorgangsmappe,
    binder 404) become exceptions; transient business/transport
    failures stay structured so the SB / CLI can render a friendly
    re-try banner without traceback dives.

    Args:
        file_path: Path to the file on the local filesystem. Must exist
            and be a regular file. Read at most once (the binder fetch
            happens BEFORE the read, so a non-Vorgangsmappe target
            never touches the disk).
        binder_guid: The target binder's GUID (NOT the UI-visible
            Dokumentnummer — use
            ``belegmeister.datev.resolver.resolve_binder_guid_by_number``
            to translate first). Echoed verbatim into the URL path.
        klardaten_client: Any value matching the ``BinderClient``
            Protocol; in production a ``KlardatenClient`` instance, in
            tests a fake with the same shape.

    Returns:
        ``UploadResult(success=True, document_id=<str>, error=None)``
        on success, where ``document_id`` is the new structure-item's
        ``id`` (string). On non-exception failure,
        ``UploadResult(success=False, document_id=None, error=<str>)``
        — see the ``UploadResult`` docstring for the message shape.

    Raises:
        InvalidUploadTarget: When the binder GET returns HTTP 404
            (``reason="binder not found (HTTP 404)"``), or when the
            fetched document is not a Vorgangsmappe
            (``reason="not a Vorgangsmappe (is_binder=…, extension=…)"``).
            The exception message carries both target id and reason so
            a single operational log line is self-describing.

    Side effects:
        Makes one ``GET`` and (on a valid target) two ``POST`` HTTP
        calls to the klardaten gateway via ``klardaten_client``. Reads
        ``file_path``'s bytes into memory once. Does not retry on
        transient failures (a 5xx becomes an ``UploadResult.error``).
        Idempotency: re-running creates an additional structure-item
        with a new id — by design, so re-sends are auditable.
    """
    if (err := _validate_inputs(file_path)) is not None:
        return UploadResult(success=False, document_id=None, error=err)

    try:
        binder = klardaten_client.get_document(binder_guid)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise InvalidUploadTarget(
                binder_guid, "binder not found (HTTP 404)"
            ) from exc
        return UploadResult(
            success=False,
            document_id=None,
            error=(
                f"HTTP {exc.response.status_code} fetching binder: "
                f"{exc.response.text[:500]}"
            ),
        )
    except httpx.HTTPError as exc:
        return UploadResult(
            success=False,
            document_id=None,
            error=f"Transport error fetching binder: {exc!s}",
        )

    _ensure_vorgangsmappe(binder_guid, binder)

    file_bytes = file_path.read_bytes()

    try:
        raw = klardaten_client.attach_file_to_binder(
            binder_guid=binder_guid,
            file_name=file_path.name,
            file_bytes=file_bytes,
        )
    except httpx.HTTPStatusError as exc:
        return UploadResult(
            success=False,
            document_id=None,
            error=f"HTTP {exc.response.status_code}: {exc.response.text[:500]}",
        )
    except httpx.HTTPError as exc:
        return UploadResult(
            success=False, document_id=None, error=f"Transport error: {exc!s}"
        )

    return _map_response(raw)


def _validate_inputs(file_path: Path) -> str | None:
    if not file_path.exists():
        return f"File not found: {file_path}"
    if not file_path.is_file():
        return f"Not a regular file: {file_path}"
    return None


def _ensure_vorgangsmappe(binder_guid: str, binder: dict[str, Any]) -> None:
    is_binder = binder.get("is_binder")
    extension = binder.get("extension")
    if is_binder is not True or extension != "VGM":
        raise InvalidUploadTarget(
            binder_guid,
            f"not a Vorgangsmappe (is_binder={is_binder!r}, extension={extension!r})",
        )


def _map_response(raw: dict[str, Any]) -> UploadResult:
    # `POST /documents/{binder}/structure-items` returns the freshly-created
    # structure-item record; its `id` (string) is the handle inside DATEV.
    doc_id_raw = raw.get("id")
    if not isinstance(doc_id_raw, str) or not doc_id_raw:
        excerpt = repr(raw)[:500]
        return UploadResult(
            success=False,
            document_id=None,
            error=f"Unexpected response shape (no id): {excerpt}",
        )
    return UploadResult(success=True, document_id=doc_id_raw, error=None)
