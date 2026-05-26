"""Probe: re-list `_request_letter_*` structure-items inside VGM 395357 and
emit JSON. Cross-check against the values captured ~30 minutes ago in
`artifacts/spikes/submit-letter-discovery-2026-05-26.md` to verify P2 —
structure-item identifiers are stable across re-reads.

Read-only. No mutations.

Usage:
    uv run python scripts/probe_letter_id_stability_2026-05-26.py
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

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
    r.raise_for_status()
    items = r.json()
    if not isinstance(items, list):
        raise RuntimeError(f"Unexpected response type: {type(items).__name__}")

    letters: list[dict[str, object]] = []
    for item in items:
        name = (
            item.get("name") or item.get("file_name") or item.get("description") or ""
        )
        if "_request_letter_" in name:
            letters.append(
                {
                    "name": name,
                    "id": item.get("id"),
                    "document_file_id": item.get("document_file_id"),
                    "counter": item.get("counter"),
                    "creation_date": item.get("creation_date"),
                }
            )

    output = {
        "probe": "letter-id-stability-re-read",
        "binder_guid": binder_guid,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total_items": len(items),
        "letters_count": len(letters),
        "letters": letters,
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
