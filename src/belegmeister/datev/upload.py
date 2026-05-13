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
    success: bool
    document_id: str | None
    error: str | None


class _BinderClient(Protocol):
    """Structural type for the injected client."""

    def get_document(self, guid: str) -> dict[str, Any]: ...

    def attach_file_to_binder(
        self, *, binder_guid: str, file_name: str, file_bytes: bytes
    ) -> dict[str, Any]: ...


def upload_to_binder(
    file_path: Path,
    binder_guid: str,
    klardaten_client: _BinderClient,
) -> UploadResult:
    """Validate the binder, then attach the file as a sub-document.

    Flow: validate file → fetch binder → ensure Vorgangsmappe → read bytes
    → attach. Programmer/operator errors raise; HTTP/transport business
    failures return an `UploadResult(success=False, …)`.
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
