"""Smoke test: upload a fresh .txt INTO a DATEV DMS Vorgangsmappe (binder).

Flow
----
1. Resolve binder Dokumentnummer (UI-visible int) to its DATEV GUID.
2. Validate the GUID points to a real Vorgangsmappe (is_binder + extension=VGM).
   InvalidUploadTarget is the failure mode here, surfaced before any bytes.
3. POST the file bytes + attach as a sub-document of the binder.
4. Print result and what to verify by clicking on that binder in the DATEV UI.

Usage
-----
    uv run python scripts/smoke_test_datev_upload.py            # binder #395239
    uv run python scripts/smoke_test_datev_upload.py 395295
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from belegmeister.datev.resolver import resolve_binder_guid_by_number
from belegmeister.datev.upload import InvalidUploadTarget, upload_to_binder
from belegmeister.klardaten.client import KlardatenClient


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "binder_number",
        nargs="?",
        type=int,
        default=395239,
        help="Binder Dokumentnummer (UI-visible int). Default 395239.",
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

    client = KlardatenClient(
        base_url=base_url,
        api_key=api_key,
        instance_id=instance_id,
        profile_id=profile_id,
    )

    print(f"Resolving binder Dokumentnummer #{args.binder_number} -> GUID ...")
    binder_guid = resolve_binder_guid_by_number(client, args.binder_number)
    if binder_guid is None:
        print(f"FAIL: binder #{args.binder_number} not found within scan window")
        return 3
    print(f"  -> {binder_guid}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"belegmeister_smoke_{stamp}.txt"
    body = (
        f"Belegmeister smoke test into binder #{args.binder_number}\n"
        f"timestamp: {stamp}\n"
    ).encode("utf-8")

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / filename
        file_path.write_bytes(body)
        print(f"Uploading {filename} ({len(body)} bytes) -> binder {binder_guid}")
        try:
            result = upload_to_binder(file_path, binder_guid, client)
        except InvalidUploadTarget as exc:
            print(f"FAIL: {exc}")
            return 4

    print()
    print(f"  success:           {result.success}")
    print(f"  structure_item_id: {result.document_id}")
    print(f"  error:             {result.error}")
    print()

    if result.success:
        print("=" * 72)
        print(
            f"VERIFY: open DATEV DMS, click on Vorgangsmappe "
            f"#{args.binder_number} ({binder_guid}),"
        )
        print(f"        look INSIDE the binder for: {filename}")
        print("        Reply DONE if you see it, FAIL otherwise.")
        print("=" * 72)
        return 0

    print("=" * 72)
    print("UPLOAD FAILED — the HTTP body in `error` is the truth source.")
    print("=" * 72)
    return 1


if __name__ == "__main__":
    sys.exit(main())
