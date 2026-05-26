"""Probe: list structure-items inside a VGM binder, locate `_request_letter_*`
records, and inspect what stable per-request identifier they expose.

Read-only (GET only). Mutates nothing. Informs the token-instance-binding
slice (Path A prerequisite to submit-handler): what field of the
structure-item record is durable enough to bind a magic-link token to?

Target: VGM 395357 (binder GUID 4c83e94e-24e7-4866-809c-5e983ad7f485),
which is known to contain a request letter from the magic-link-ui smoke
earlier today.

Usage:
    uv run python scripts/probe_request_letter_structure_items_2026-05-26.py
"""

from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()

    base = os.environ.get("KLARDATEN_BASE_URL", "https://api.klardaten.com")
    api_key = os.environ["KLARDATEN_API_KEY"]
    instance_id = os.environ["KLARDATEN_INSTANCE_ID"]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "x-client-instance-id": instance_id,
    }
    binder_guid = "4c83e94e-24e7-4866-809c-5e983ad7f485"

    r = httpx.get(
        f"{base}/datevconnect/dms/v2/documents/{binder_guid}/structure-items",
        headers=headers,
        timeout=30,
    )
    print(f"URL:    {r.request.url}")
    print(f"Status: {r.status_code}")
    if r.status_code != 200:
        print(f"Body:   {r.text[:1000]}")
        return

    payload = r.json()
    items = payload if isinstance(payload, list) else []
    print(f"Items in binder: {len(items)}")
    print()

    letters: list[dict[str, object]] = []
    for item in items:
        name = (
            item.get("name") or item.get("file_name") or item.get("description") or ""
        )
        if "_request_letter_" in name or name.startswith("_request_letter"):
            letters.append(item)

    print(f"_request_letter_* found: {len(letters)}")
    print()
    for i, letter in enumerate(letters, 1):
        print(f"--- letter {i} ---")
        for k, v in letter.items():
            print(f"  {k!s:>28}: {v!r}")
        print()


if __name__ == "__main__":
    main()
