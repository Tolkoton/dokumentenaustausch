"""Smoke test: create a document-request against a real DATEV Vorgangsmappe.

Flow
----
1. Resolve binder Dokumentnummer (UI-visible int) to GUID via klardaten.
2. Write a fixed letter body to a temp file.
3. Invoke `python -m belegmeister create-request` as a subprocess so the
   real env-loading + argparse + exception-handling path is exercised
   (not just the in-process flow).
4. Print stdout (the magic-link URL) and what to verify in the DATEV UI.

Usage
-----
    uv run python scripts/smoke_test_create_request.py            # VGM #395239
    uv run python scripts/smoke_test_create_request.py 395295

Required env (in `.env` or shell):
    KLARDATEN_API_KEY, KLARDATEN_INSTANCE_ID
    MAGIC_LINK_SECRET (>=32 bytes), MAGIC_LINK_BASE_URL (https:// or http://localhost)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from belegmeister.datev.resolver import resolve_binder_guid_by_number
from belegmeister.klardaten.client import KlardatenClient

LETTER_BODY = """\
Sehr geehrte Damen und Herren,

bitte übermitteln Sie uns die folgenden Belege für den
Veranlagungszeitraum 2026 binnen 7 Tagen:

  - Rechnungen über 1.000 EUR (Eingang/Ausgang)
  - Bankauszüge sämtlicher Geschäftskonten
  - Kassenbuch (falls Bargeschäft)

Den Upload-Link erhalten Sie unter der unten generierten URL.

Mit freundlichen Grüßen,
Belegmeister (Test-Smoke {stamp})
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "binder_number",
        nargs="?",
        type=int,
        default=395239,
        help="VGM Dokumentnummer (UI-visible int). Default 395239.",
    )
    parser.add_argument(
        "--ttl-days",
        type=int,
        default=7,
        help="Magic-link lifetime in days (default 7).",
    )
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("KLARDATEN_API_KEY")
    instance_id = os.environ.get("KLARDATEN_INSTANCE_ID")
    base_url = os.environ.get("KLARDATEN_BASE_URL", "https://api.klardaten.com")
    profile_id = os.environ.get("KLARDATEN_PROFILE_ID") or None
    magic_secret = os.environ.get("MAGIC_LINK_SECRET")
    magic_base = os.environ.get("MAGIC_LINK_BASE_URL")

    missing = [
        name
        for name, val in (
            ("KLARDATEN_API_KEY", api_key),
            ("KLARDATEN_INSTANCE_ID", instance_id),
            ("MAGIC_LINK_SECRET", magic_secret),
            ("MAGIC_LINK_BASE_URL", magic_base),
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

    print(f"Resolving binder Dokumentnummer #{args.binder_number} -> GUID ...")
    binder_guid = resolve_binder_guid_by_number(client, args.binder_number)
    if binder_guid is None:
        print(
            f"FAIL: binder #{args.binder_number} not found within scan window",
            file=sys.stderr,
        )
        return 3
    print(f"  -> {binder_guid}")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    with tempfile.TemporaryDirectory() as tmpdir:
        letter_path = Path(tmpdir) / f"letter_{stamp}.txt"
        letter_path.write_text(LETTER_BODY.format(stamp=stamp), encoding="utf-8")

        print(
            f"Running: python -m belegmeister create-request "
            f"--vgm-id {binder_guid} --letter-file {letter_path.name} "
            f"--ttl-days {args.ttl_days}"
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "belegmeister",
                "create-request",
                "--vgm-id",
                binder_guid,
                "--letter-file",
                str(letter_path),
                "--ttl-days",
                str(args.ttl_days),
            ],
            capture_output=True,
            text=True,
        )

    print()
    if result.returncode != 0:
        print("FAIL: subprocess exited non-zero", file=sys.stderr)
        print(f"  stderr: {result.stderr}", file=sys.stderr)
        print(f"  stdout: {result.stdout}", file=sys.stderr)
        return 4

    url = result.stdout.strip()
    print("=" * 72)
    print("VERIFY in DATEV UI:")
    print(f"  Open VGM #{args.binder_number} ({binder_guid})")
    print(f"  Look INSIDE the binder for: _request_letter_{stamp}.md")
    print("  File should contain the German tax-doc request body.")
    print("=" * 72)
    print()
    print("Magic-link URL (copy & inspect — DO NOT email yet, no handler exists):")
    print(f"  {url}")
    print()
    print("Reply DONE if file is visible in the binder, FAIL otherwise.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
