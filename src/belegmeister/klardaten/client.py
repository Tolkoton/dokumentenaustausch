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
        """GET /datevconnect/dms/v2/documents/{guid}."""
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

    def list_documents(self, *, top: int = 1000, skip: int = 0) -> list[dict[str, Any]]:
        """GET /datevconnect/dms/v2/documents with simple paging."""
        url = f"{self.base_url.rstrip('/')}/datevconnect/dms/v2/documents"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(
                url,
                headers=self._auth_headers(),
                params={"$top": top, "$skip": skip},
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
        """Flow: POST bytes → POST structure-item under the binder."""
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
