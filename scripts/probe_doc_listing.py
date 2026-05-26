"""Probe: empirical check of OData query-param handling on /documents.

Goal
----
Determine which of ``$top``, ``$skip``, ``$orderby``, ``$filter`` the
klardaten gateway honors so that the submit-slice (or its prerequisite
token-instance-binding slice) can decide whether a "subtract from
latest" direct-lookup is viable, or whether direct filter-by-number
might work after all.

Read-only. GETs only. Stdout only. No JSON output, no side effects.

Already-settled cross-reference (not re-asked by this script)
-------------------------------------------------------------
- ``scripts/spike_direct_lookup_2026-05-19.py`` settled that
  ``$filter=number eq X`` (lowercase, uppercase, and quoted forms) is
  IGNORED, and that ``/documents/by-number/{n}`` /
  ``/documents/number/{n}`` path routes are ABSENT. Variant E here is
  retained as a fresh cross-check; expected outcome IGNORED.
- ``src/belegmeister/klardaten/client.py:80-86`` documents that the
  server ignores ``$top`` — but the existing spike never verified the
  returned count against the requested cap. Variants A and B target
  exactly that.
- ``$orderby`` has NEVER been probed in this codebase. Variant C is
  the only genuinely novel question; it gates the "subtract from
  latest" strategy.

Usage
-----
    uv run python scripts/probe_doc_listing.py
"""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx
from dotenv import load_dotenv

from belegmeister.klardaten.client import KlardatenClient

DOCS_PATH = "/datevconnect/dms/v2/documents"


def _probe(
    client: KlardatenClient,
    label: str,
    params: dict[str, Any] | None,
) -> None:
    """Send one GET with the given params, print the diagnostic shape.

    Drops below ``KlardatenClient.list_documents`` (which only exposes
    ``top`` / ``skip``) to send arbitrary OData params. The client's
    auth headers and base URL are reused so credential handling matches
    the project pattern.
    """
    print(f"--- Variant {label} ---")
    url = f"{client.base_url.rstrip('/')}{DOCS_PATH}"
    try:
        response = httpx.get(
            url,
            headers=client._auth_headers(),  # noqa: SLF001
            params=params,
            timeout=client.timeout,
        )
    except httpx.HTTPError as exc:
        print(f"  TRANSPORT ERROR: {type(exc).__name__}: {exc!s}")
        print()
        return

    print(f"  sent URL: {response.request.url}")
    print(f"  status:   {response.status_code}")

    if response.status_code >= 400:
        body = response.text[:1000]
        print(f"  error body: {body}")
        print()
        return

    try:
        data = response.json()
    except ValueError:
        print(f"  body not JSON: {response.text[:500]}")
        print()
        return

    items: list[dict[str, Any]] = []
    if isinstance(data, list):
        items = [x for x in data if isinstance(x, dict)]
    elif isinstance(data, dict):
        for key in ("value", "items", "documents", "Documents", "Value"):
            container = data.get(key)
            if isinstance(container, list):
                items = [x for x in container if isinstance(x, dict)]
                break

    print(f"  count:    {len(items)}")
    for item in items[:10]:
        print(
            f"    ({item.get('number')!r}, "
            f"{item.get('id')!r}, "
            f"{item.get('extension')!r})"
        )
    print()


def main() -> int:
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
        print(f"FAIL: missing env vars: {', '.join(missing)}", file=sys.stderr)
        return 2
    assert api_key and instance_id

    client = KlardatenClient(
        base_url=base_url,
        api_key=api_key,
        instance_id=instance_id,
        profile_id=profile_id,
    )

    variants: list[tuple[str, dict[str, Any] | None]] = [
        ("A (no params — baseline)", None),
        ("B ($top=10)", {"$top": 10}),
        (
            "C ($top=10, $orderby=number desc)",
            {"$top": 10, "$orderby": "number desc"},
        ),
        ("D ($top=5, $skip=100)", {"$top": 5, "$skip": 100}),
        ("E ($filter=number eq 395223)", {"$filter": "number eq 395223"}),
    ]

    for label, params in variants:
        try:
            _probe(client, label, params)
        except Exception as exc:  # noqa: BLE001 — broad catch per spec
            print(f"--- Variant {label} ---")
            print(f"  UNEXPECTED ERROR: {type(exc).__name__}: {exc!s}")
            print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
