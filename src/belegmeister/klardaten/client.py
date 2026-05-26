"""HTTP wrapper for the klardaten gateway (reverse proxy for DATEVconnect).

Each public method is one HTTP call's worth of responsibility. Orchestration
(validate → fetch → act) lives one layer up in `belegmeister.datev.upload`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast

import httpx


@dataclass(frozen=True)
class KlardatenClient:
    """Authenticated client for the klardaten DATEVconnect gateway.

    Uses a long-lived API key (`uk-...`) that does not expire.
    """

    base_url: str
    api_key: str
    instance_id: str
    profile_id: str | None = None
    timeout: float = 30.0

    def get_document(self, guid: str) -> dict[str, Any]:
        """Fetch a single document record from DATEV DMS by GUID.

        Wire call: ``GET /datevconnect/dms/v2/documents/{guid}`` against
        the klardaten gateway. Used by ``belegmeister.datev.upload`` to
        confirm a target is a Vorgangsmappe (``is_binder`` /
        ``extension`` fields) before sending any bytes.

        Args:
            guid: The document's klardaten GUID. Embedded directly in
                the URL path; the caller is responsible for providing a
                trusted value (typically from a prior
                ``list_documents`` call or
                ``resolve_binder_guid_by_number``).

        Returns:
            The decoded JSON object as a ``dict``. Fields of interest
            for the DMS v2 schema include ``is_binder`` (bool),
            ``extension`` (``"VGM"`` for a Vorgangsmappe), ``number``
            (the UI Dokumentnummer), and the various ``folder`` /
            ``register`` references.

        Raises:
            httpx.HTTPStatusError: Non-2xx response (404 commonly means
                "GUID unknown", 401/403 means auth/profile problem).
            httpx.DecodingError: Body parsed as JSON but was not a JSON
                object — should not happen against the real endpoint;
                guards against a misrouted proxy.
            httpx.HTTPError: Other transport-level errors (timeout,
                connection refused).
        """
        url = f"{self.base_url.rstrip('/')}/datevconnect/dms/v2/documents/{guid}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, headers=self._auth_headers())
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise httpx.DecodingError(
                f"Expected JSON object from /documents/{{guid}}, "
                f"got {type(data).__name__}"
            )
        return cast(dict[str, Any], data)

    def list_documents(
        self,
        *,
        filter: str | None = None,  # noqa: A002 — wire-level param name
        top: int | None = None,
        skip: int | None = None,
    ) -> list[dict[str, Any]]:
        """List documents from DATEV DMS, optionally filtered server-side.

        Wire call: ``GET /datevconnect/dms/v2/documents`` with **plain
        (non-``$``-prefixed)** OData params — ``filter``, ``top``, and
        ``skip``. Only the params the caller supplies are sent; passing
        no kwargs hits the endpoint bare.

        klardaten wire-format finding (ADR-0003 — supersedes ADR-0001
        on this point): the gateway honors OData ``filter``, ``top``,
        and ``skip`` **without** the leading ``$``. The ``$``-prefixed
        forms (``$filter``, ``$top``, ``$skip``) are silently ignored —
        a 1000-row default page is returned regardless. The original
        Slice-1 reading "no server-side filter exists" was the symptom
        of sending the ignored ``$``-prefixed variant.

        Args:
            filter: OData filter expression sent as the ``filter`` query
                param. Typical shape: ``"number eq <int>"``.
            top: Max rows to return. Omit for the server default (1000).
            skip: Number of rows to skip (offset pagination).

        Returns:
            The result as a ``list`` of document records (each a
            ``dict``, schema per ``get_document``). Empty list means
            no matches under the filter, or pagination exhausted.

        Raises:
            httpx.HTTPStatusError: Non-2xx response.
            httpx.DecodingError: Body was not a JSON array — points to
                a proxy / gateway misroute.
            httpx.HTTPError: Other transport-level errors.
        """
        url = f"{self.base_url.rstrip('/')}/datevconnect/dms/v2/documents"
        params: dict[str, Any] = {}
        if filter is not None:
            params["filter"] = filter
        if top is not None:
            params["top"] = top
        if skip is not None:
            params["skip"] = skip
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                url,
                headers=self._auth_headers(),
                params=params,
            )
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, list):
            raise httpx.DecodingError(
                f"Expected JSON array from /documents, got {type(data).__name__}"
            )
        return cast(list[dict[str, Any]], data)

    def attach_file_to_binder(
        self, *, binder_guid: str, file_name: str, file_bytes: bytes
    ) -> dict[str, Any]:
        """Attach raw bytes as a child file (structure-item) of a Vorgangsmappe.

        Two-call DATEV DMS v2 flow, hidden behind one public method
        because the seam is one logical operation:

        1. ``POST /datevconnect/dms/v2/document-files`` with
           ``Content-Type: application/octet-stream`` — uploads the raw
           bytes and returns ``{"id": <int>}``. The returned id is
           **single-shot**: reusing it on a second ``structure-items``
           POST yields ``"document_file_id N is not available"``.
        2. ``POST /datevconnect/dms/v2/documents/{binder_guid}/structure-items``
           with the type=1 JSON body built by ``_build_structure_item``
           (carrying ``document_file_id`` from step 1).

        The caller (``belegmeister.datev.upload.upload_to_binder``) is
        responsible for verifying the target is actually a Vorgangsmappe
        before invoking this; the client does not re-check.

        Args:
            binder_guid: The Vorgangsmappe's GUID. Inserted into the
                URL path of step 2; not validated here.
            file_name: Display name for the attached file inside the
                binder — what the SB / Mandant sees in DATEV's UI. The
                request-letter slice uses
                ``vgm_files.request_letter_filename`` to keep this
                consistent with the reader.
            file_bytes: The full file content. Sent in one POST body
                (no chunking); large files become a single in-memory
                buffer at the caller.

        Returns:
            The freshly-created structure-item record as returned by
            step 2 (a ``dict``). Its ``id`` field (``str``) is the
            handle the SB / DMS UI use to identify the attachment.

        Raises:
            httpx.HTTPStatusError: Any non-2xx from either POST.
            httpx.DecodingError: Step 1's response did not match
                ``{"id": ...}``, or step 2's response was not a JSON
                object.
            httpx.HTTPError: Transport errors during either call.

        Side effects:
            Two HTTP calls per invocation; both are non-idempotent at
            the DATEV side. Re-running creates additional document-file
            ids and structure-items.
        """
        document_file_id = self._upload_file_bytes(file_bytes)
        return self._post_structure_item(
            binder_guid=binder_guid,
            file_name=file_name,
            document_file_id=document_file_id,
        )

    def _upload_file_bytes(self, file_bytes: bytes) -> int:
        url = f"{self.base_url.rstrip('/')}/datevconnect/dms/v2/document-files"
        headers = self._auth_headers()
        headers["Content-Type"] = "application/octet-stream"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, content=file_bytes)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict) or "id" not in data:
            raise httpx.DecodingError(
                f"Expected {{'id': ...}} from /document-files, got {data!r}"
            )
        return int(data["id"])

    def _post_structure_item(
        self, *, binder_guid: str, file_name: str, document_file_id: int
    ) -> dict[str, Any]:
        url = (
            f"{self.base_url.rstrip('/')}"
            f"/datevconnect/dms/v2/documents/{binder_guid}/structure-items"
        )
        headers = self._auth_headers()
        headers["Content-Type"] = "application/json"
        payload = _build_structure_item(
            file_name=file_name, document_file_id=document_file_id
        )
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise httpx.DecodingError(
                f"Expected JSON object from /structure-items, got {type(data).__name__}"
            )
        return cast(dict[str, Any], data)

    def list_structure_items(self, binder_guid: str) -> list[dict[str, Any]]:
        """List the children (files and sub-folders) of a Vorgangsmappe.

        Wire call: ``GET /datevconnect/dms/v2/documents/{binder_guid}/structure-items``.
        Children are a separate sub-resource — ``get_document`` on the
        binder itself does NOT include them. The Mandant-facing magic-
        link page uses this to find the newest
        ``_request_letter_*.txt`` deposited in the binder.

        Args:
            binder_guid: The Vorgangsmappe's GUID. Inserted into the
                URL path; not validated here.

        Returns:
            A ``list`` of structure-item ``dict``s. Each item carries:

            * ``"type"`` — ``1`` for a file (``document_file_id`` +
              ``size`` populated), ``2`` for a sub-folder.
            * ``"name"`` — display name.
            * ``"document_file_id"`` — the int handle to fetch bytes
              via ``download_document_file`` (files only).
            * Other DMS-v2 schema fields (``counter``, ``creation_date``,
              etc.).

        Raises:
            httpx.HTTPStatusError: Non-2xx response (404 indicates the
                binder GUID is unknown).
            httpx.DecodingError: Body was not a JSON array.
            httpx.HTTPError: Other transport-level errors.
        """
        url = (
            f"{self.base_url.rstrip('/')}"
            f"/datevconnect/dms/v2/documents/{binder_guid}/structure-items"
        )
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, headers=self._auth_headers())
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, list):
            raise httpx.DecodingError(
                f"Expected JSON array from /structure-items, got {type(data).__name__}"
            )
        return cast(list[dict[str, Any]], data)

    def download_document_file(self, document_file_id: int) -> bytes:
        """Download the raw bytes of a DMS document-file by id.

        Wire call: ``GET /datevconnect/dms/v2/document-files/{id}``.
        Used by ``belegmeister.web.request_view`` to fetch the body of
        the request-letter the Mandant must read on the magic-link page.

        DATEV-specific quirk: the endpoint **requires**
        ``Accept: application/octet-stream``; sending the client's
        default ``application/json`` yields a 400. The response body
        is the raw file content with no JSON wrapper (and DATEV does
        not always set ``Content-Length`` — the body is read in full).

        Args:
            document_file_id: The integer id obtained from a
                structure-item's ``document_file_id`` field
                (``list_structure_items``).

        Returns:
            The complete file content as ``bytes``. Decoding (typically
            UTF-8 for request letters) is the caller's concern.

        Raises:
            httpx.HTTPStatusError: Non-2xx — 400 typically means the
                ``Accept`` header was modified upstream; 404 means the
                id is unknown.
            httpx.HTTPError: Other transport-level errors.
        """
        url = (
            f"{self.base_url.rstrip('/')}"
            f"/datevconnect/dms/v2/document-files/{document_file_id}"
        )
        headers = self._auth_headers()
        headers["Accept"] = "application/octet-stream"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
        return response.content

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "x-client-instance-id": self.instance_id,
            "Accept": "application/json",
        }
        if self.profile_id is not None:
            headers["x-profile-id"] = self.profile_id
        return headers


def _build_structure_item(*, file_name: str, document_file_id: int) -> dict[str, Any]:
    """Build the type=1 (file) structure-item body.

    `counter` is sent as 1 but DATEV overwrites it server-side with the next
    free value for that binder (observed empirically). `creation_date` and
    `last_modification_date` use ISO-8601 with millisecond precision and no
    timezone — matches what GET returns on existing structure-items.
    """
    now = (
        datetime.now(timezone.utc)
        .replace(tzinfo=None)
        .isoformat(timespec="milliseconds")
    )
    return {
        "name": file_name,
        "counter": 1,
        "type": 1,
        "parent_counter": 0,
        "document_file_id": document_file_id,
        "creation_date": now,
        "last_modification_date": now,
    }
