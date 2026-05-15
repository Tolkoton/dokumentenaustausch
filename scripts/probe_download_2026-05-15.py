"""SPIKE (read-only): how do we download a structure-item's file content?

NOT production code. NOT tests. Prints real DATEV responses so we can
lock the Slice-3 seam against the actual wire shape instead of guessing.

Closes these unknowns in one run against VGM #395239 (has
`_request_letter_*.md` from Slice-2 smokes):

  1. Shape of `structure_items` in GET /documents/{guid} — does each
     child carry a `document_file_id` (or equivalent)?
  2. Which GET path returns the raw file bytes? Tries several.
  3. Content-Type of the download — raw bytes vs JSON wrapper?
  4. Do the upload API key + x-client-instance-id also grant download?

Usage:
    uv run python scripts/probe_download_2026-05-15.py            # #395239
    uv run python scripts/probe_download_2026-05-15.py 395357
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx
from dotenv import load_dotenv

from belegmeister.datev.resolver import resolve_binder_guid_by_number
from belegmeister.klardaten.client import KlardatenClient


def _auth_headers(
    api_key: str, instance_id: str, profile_id: str | None
) -> dict[str, str]:
    h = {
        "Authorization": f"Bearer {api_key}",
        "x-client-instance-id": instance_id,
        "Accept": "application/json",
    }
    if profile_id:
        h["x-profile-id"] = profile_id
    return h


def _probe_get(url: str, headers: dict[str, str], label: str) -> None:
    print(f"\n--- {label}")
    print(f"GET {url}")
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.get(url, headers=headers)
    except httpx.HTTPError as exc:
        print(f"  transport error: {exc!r}")
        return
    print(f"  status        : {r.status_code}")
    print(f"  content-type  : {r.headers.get('content-type')}")
    print(
        f"  content-length: {r.headers.get('content-length')} (actual {len(r.content)})"
    )
    link = r.headers.get("link")
    if link:
        print(f"  link header   : {link}")
    body = r.content[:300]
    try:
        print(f"  body[:300]    : {body.decode('utf-8')!r}")
    except UnicodeDecodeError:
        print(f"  body[:300]    : <binary> {body!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("binder_number", nargs="?", type=int, default=395239)
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("KLARDATEN_API_KEY")
    instance_id = os.environ.get("KLARDATEN_INSTANCE_ID")
    base = os.environ.get("KLARDATEN_BASE_URL", "https://api.klardaten.com")
    profile_id = os.environ.get("KLARDATEN_PROFILE_ID") or None
    if not api_key or not instance_id:
        print(
            "FAIL: KLARDATEN_API_KEY / KLARDATEN_INSTANCE_ID required", file=sys.stderr
        )
        return 2

    headers = _auth_headers(api_key, instance_id, profile_id)
    client = KlardatenClient(
        base_url=base, api_key=api_key, instance_id=instance_id, profile_id=profile_id
    )

    print(f"Resolving #{args.binder_number} -> GUID ...")
    guid = resolve_binder_guid_by_number(client, args.binder_number)
    if guid is None:
        print(f"FAIL: #{args.binder_number} not found", file=sys.stderr)
        return 3
    print(f"  -> {guid}")

    b = base.rstrip("/")

    # === Unknown 1: where do the binder's children live? ===
    doc = client.get_document(guid)
    sitems = doc.get("structure_items")
    if not isinstance(sitems, list):
        print(
            "\n(GET /documents/{guid} has NO structure_items — "
            "probing sub-resource list endpoints)"
        )
        for path in (
            f"/datevconnect/dms/v2/documents/{guid}/structure-items",
            f"/datevconnect/dms/v2/documents/{guid}/structureitems",
            f"/datevconnect/dms/v2/documents/{guid}/document-files",
        ):
            _probe_get(b + path, headers, f"LIST probe: {path}")
        try:
            with httpx.Client(timeout=30.0) as c:
                lr = c.get(
                    f"{b}/datevconnect/dms/v2/documents/{guid}/structure-items",
                    headers=headers,
                )
            if lr.status_code == 200 and isinstance(lr.json(), list):
                sitems = lr.json()
                print(f"\n  -> structure-items LIST works: {len(sitems)} items")
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            print(f"  list-endpoint parse failed: {exc!r}")
    if not isinstance(sitems, list):
        print("  STILL no children list — dumping doc keys, stopping")
        print(f"  keys: {sorted(doc.keys())}")
        return 1

    letters = []
    for it in sitems:
        name = it.get("name", "")
        is_letter = isinstance(name, str) and name.startswith("_request_letter_")
        if is_letter:
            letters.append(it)
        # Dump full record for letters + first 2 others (shape reference)
        if is_letter or sitems.index(it) < 2:
            print(f"  {json.dumps(it, ensure_ascii=False, sort_keys=True)}")

    print(f"\n=== _request_letter_*.md found: {len(letters)} ===")
    if not letters:
        print("  none — run a Slice-2 create-request against this VGM first")
        return 1
    newest = max(letters, key=lambda it: it.get("name", ""))
    print(f"  newest: {newest.get('name')}")
    print(f"  fields: {sorted(newest.keys())}")

    file_id = newest.get("document_file_id")
    counter = newest.get("counter")
    print(f"  document_file_id = {file_id!r}   counter = {counter!r}")

    # === Unknown 2/3/4: which GET returns bytes? ===
    if file_id is not None:
        _probe_get(
            f"{b}/datevconnect/dms/v2/document-files/{file_id}",
            headers,
            "candidate A: /document-files/{file_id} (json accept)",
        )
        _probe_get(
            f"{b}/datevconnect/dms/v2/document-files/{file_id}",
            {**headers, "Accept": "*/*"},
            "candidate A': /document-files/{file_id} (accept */*)",
        )
    _probe_get(
        f"{b}/datevconnect/dms/v2/documents/{guid}/structure-items/{counter}",
        headers,
        "candidate B: /documents/{guid}/structure-items/{counter}",
    )
    _probe_get(
        f"{b}/datevconnect/dms/v2/documents/{guid}/structure-items/{counter}/document-file",
        {**headers, "Accept": "*/*"},
        "candidate C: .../structure-items/{counter}/document-file",
    )
    _probe_get(
        f"{b}/datevconnect/dms/v2/documents/{guid}/document-files/{file_id}",
        {**headers, "Accept": "*/*"},
        "candidate D: /documents/{guid}/document-files/{file_id}",
    )

    print("\n=== DONE — copy the working candidate + content-type into the seam ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
