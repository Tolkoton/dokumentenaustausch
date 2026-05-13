"""Probe DATEVconnect DMS v2 (via klardaten) to reverse-engineer the
create-document metadata schema.

Read-only. Issues GETs only — does NOT modify folder 395239 or any DMS state.

Usage
-----
    uv run python scripts/probe_dms.py
    uv run python scripts/probe_dms.py --top 5
    uv run python scripts/probe_dms.py --doc-id <known-document-id>

The output is pretty-printed JSON for each probed endpoint plus a status
summary. 200s tell us a path is real and reveal the response shape; 404s tell
us a path is wrong; 400s sometimes leak the expected schema (like the smoke
test did for POST /documents).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx
from dotenv import load_dotenv


def _build_session(
    api_key: str, instance_id: str, profile_id: str | None
) -> httpx.Client:
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "x-client-instance-id": instance_id,
        "Accept": "application/json",
    }
    if profile_id is not None:
        headers["x-profile-id"] = profile_id
    return httpx.Client(headers=headers, timeout=30.0)


def _print_section(title: str) -> None:
    bar = "=" * 72
    print(f"\n{bar}\n{title}\n{bar}")


def _truncate(value: Any, max_items: int = 5) -> Any:
    """Recursively cap list lengths so printouts stay readable."""
    if isinstance(value, list):
        truncated: list[Any] = [_truncate(v, max_items) for v in value[:max_items]]
        if len(value) > max_items:
            truncated.append(f"...(truncated {len(value) - max_items} more)")
        return truncated
    if isinstance(value, dict):
        return {k: _truncate(v, max_items) for k, v in value.items()}
    return value


def _probe(
    client: httpx.Client, base_url: str, path: str, label: str
) -> tuple[int, Any]:
    """GET one endpoint. Returns (status, parsed-body-or-text-or-None)."""
    url = f"{base_url.rstrip('/')}{path}"
    _print_section(f"{label}  →  GET {path}")
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        print(f"transport error: {exc!s}")
        return -1, None

    print(f"status: {response.status_code}")
    if not response.content:
        print("(empty body)")
        return response.status_code, None

    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body: Any = response.json()
        except json.JSONDecodeError:
            text = response.text
            print(text[:2000])
            return response.status_code, text
        print(json.dumps(_truncate(body), indent=2, ensure_ascii=False, default=str))
        return response.status_code, body

    text = response.text
    print(text[:2000])
    return response.status_code, text


def _find_first_doc_id(list_body: Any) -> str | None:
    items: Any = None
    if isinstance(list_body, dict):
        for key in ("value", "items", "documents", "Documents", "Value"):
            candidate = list_body.get(key)
            if isinstance(candidate, list) and candidate:
                items = candidate
                break
    elif isinstance(list_body, list):
        items = list_body

    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    if not isinstance(first, dict):
        return None
    for key in ("Id", "id", "DocumentId", "document_id", "guid", "Guid"):
        val = first.get(key)
        if isinstance(val, str) and val:
            return val
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--top", type=int, default=2, help="List response cap (default 2)."
    )
    parser.add_argument(
        "--doc-id",
        type=str,
        default=None,
        help="Fetch this specific document ID in full.",
    )
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("KLARDATEN_API_KEY")
    instance_id = os.environ.get("KLARDATEN_INSTANCE_ID")
    base_url = os.environ.get("KLARDATEN_BASE_URL", "https://api.klardaten.com")
    profile_id = os.environ.get("KLARDATEN_PROFILE_ID") or None

    missing = [
        name
        for name, val in (
            ("KLARDATEN_API_KEY", api_key),
            ("KLARDATEN_INSTANCE_ID", instance_id),
        )
        if not val
    ]
    if missing:
        print(f"FAIL: missing env vars: {', '.join(missing)}")
        return 2
    assert api_key and instance_id

    dvc = "/datevconnect/dms/v2"
    summary: list[tuple[str, int]] = []

    with _build_session(api_key, instance_id, profile_id) as client:
        for path, label in (
            (f"{dvc}/info", "INFO"),
            (f"{dvc}", "ROOT"),
        ):
            status, _ = _probe(client, base_url, path, label)
            summary.append((label, status))

        list_path = f"{dvc}/documents?$top={args.top}"
        status, list_body = _probe(client, base_url, list_path, "DOCUMENTS LIST")
        summary.append(("DOCUMENTS_LIST", status))

        target_doc_id = args.doc_id or _find_first_doc_id(list_body)
        if target_doc_id:
            status, _ = _probe(
                client,
                base_url,
                f"{dvc}/documents/{target_doc_id}",
                f"DOCUMENT DETAIL ({target_doc_id})",
            )
            summary.append(("DOCUMENT_DETAIL", status))
        else:
            print("\n(no document id discovered; skipping detail fetch)")

        for path, label in (
            (f"{dvc}/structureitems", "STRUCTUREITEMS"),
            (f"{dvc}/structure-items", "STRUCTURE-ITEMS"),
            (f"{dvc}/structureitemtypes", "STRUCTUREITEMTYPES"),
            (f"{dvc}/structure", "STRUCTURE"),
            (f"{dvc}/folders", "FOLDERS"),
            (f"{dvc}/folders/395239", "FOLDER_395239"),
        ):
            status, _ = _probe(client, base_url, path, label)
            summary.append((label, status))

        for path, label in (
            (f"{dvc}/classes", "CLASSES"),
            (f"{dvc}/domains", "DOMAINS"),
            (f"{dvc}/states", "STATES"),
            (f"{dvc}/correspondencepartners", "CORRESPONDENCEPARTNERS"),
            (f"{dvc}/users", "USERS"),
        ):
            status, _ = _probe(client, base_url, path, label)
            summary.append((label, status))

    _print_section("PROBE SUMMARY")
    for label, status in summary:
        print(f"  {label:<32} {status}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
