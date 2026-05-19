"""Smoke test: the LOCAL SB request-creation web form (Slice 4b).

This is a GUIDED manual smoke — 4b is a browser form, so a human drives
the UI. The script does the preflight (env present, the test VGM number
actually resolves to a binder GUID) and then prints explicit, ordered,
human-verifiable steps + what to check in the DATEV UI.

It does NOT start uvicorn (long-running; the SB runs it in a console
window that stays visible — packaging/launcher is Slice 4c). It does NOT
touch the form itself.

Usage
-----
    uv run python scripts/smoke_test_sb_form.py            # VGM #395357
    uv run python scripts/smoke_test_sb_form.py 395239

Required env (in `.env` or shell):
    KLARDATEN_API_KEY, KLARDATEN_INSTANCE_ID
    MAGIC_LINK_SECRET (>=32 bytes)
    MAGIC_LINK_BASE_URL (https:// or http://localhost) — the PUBLIC
        client handler the magic link points at, NOT this SB app
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from belegmeister.datev.resolver import resolve_binder_guid_by_number
from belegmeister.klardaten.client import KlardatenClient

_SB_URL = "http://localhost:8731/sb"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "binder_number",
        nargs="?",
        type=int,
        default=395357,
        help="VGM Dokumentnummer (UI-visible int). Default 395357.",
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

    print(f"Preflight: resolving test VGM #{args.binder_number} -> GUID ...")
    guid = resolve_binder_guid_by_number(client, args.binder_number)
    if guid is None:
        print(
            f"FAIL: test binder #{args.binder_number} not found — pick a "
            f"binder that exists on this instance",
            file=sys.stderr,
        )
        return 3
    print(f"  -> {guid}  (the form will resolve the SAME way internally)")

    bar = "=" * 72
    print()
    print(bar)
    print("MANUAL SMOKE — drive the form in a browser:")
    print(bar)
    print("1. In a console window, start the LOCAL SB app:")
    print("     uv run uvicorn belegmeister.sb.app:app --port 8731")
    print(f"2. Open:  {_SB_URL}")
    print("   NOTE: open the /sb path explicitly. http://localhost:8731/")
    print("   intentionally 404s (no root route in 4b — the 4c launcher")
    print("   will open /sb directly). A favicon 404 in logs is normal.")
    print(f"3. Fill the form: VGM-Nummer = {args.binder_number},")
    print("   An/To, Betreff, Anschreiben (a few paragraphs), then click")
    print("   '+ Frage hinzufügen' 2-3 times and type questions.")
    print("4. Submit. EXPECT: a result page with the magic link as")
    print("   copyable text (https://.../r/<token>). NO email is sent.")
    print("   The submit button disables on click (no double-create).")
    print("5. VERIFY in the DATEV UI:")
    print(f"     Open VGM #{args.binder_number} ({guid})")
    print("     Inside the binder: a new _request_letter_<ISO>.txt with")
    print("     the request/v1 wire format:")
    print("       line 1 : ==BELEGMEISTER== request/v1")
    print("       To: / Cc: / Subject: headers, blank line, verbatim body")
    print("       ==BELEGMEISTER== fragen / the questions / == end")
    print("6. KEYBOARD test (browser-only — unit tests can't emulate):")
    print("   Click into each field; in a QUESTION input press Enter.")
    print("   EXPECT: Enter adds a new question row + focuses it; it")
    print("   does NOT submit the form. (Enter in other fields = normal")
    print("   submit, that is expected.)")
    print("7. SALVAGE test: fill several fields, then trigger an")
    print("   incomplete submit (e.g. POST with a tool, or clear a")
    print("   required field via devtools). EXPECT: the form re-renders")
    print("   at HTTP 200 with the 'unvollständig' banner AND every")
    print("   value you typed still present (NOT a wiped/empty form).")
    print("8. ERROR-UX spot checks (re-render, NOT a 500/traceback):")
    print("   a. VGM-Nummer = 'abc'      -> 'muss eine Zahl sein',")
    print("      every other field still filled in")
    print("   b. VGM-Nummer = a numeric NON-existent number (e.g.")
    print("      646546244) -> 'nicht gefunden'. MEASURE wall time:")
    print("      this forces a full DATEV document scan (resolver has")
    print("      no server-side filter — Slice-1 limitation). While it")
    print("      runs the form MUST show the moving spinner + 'wird in")
    print("      DATEV gesucht …' (slow must look ALIVE, not dead). A")
    print("      single hung page degrades to B12 'nicht erreichbar'")
    print("      within ~30s (per-request timeout). Record the elapsed")
    print("      seconds in the PROGRESS open-item (unit fakes hide it).")
    print("   c. leave Betreff empty     -> field message, body kept")
    print("   d. add a blank question    -> error AT that row, all rows")
    print("      and their text preserved")
    print("   e. GET http://localhost:8731/sb/create -> redirects to")
    print("      the form (NOT 405/JSON)")
    print(bar)
    print()
    print("Reply DONE only if: step 5 shows the request/v1 letter in")
    print("the binder, step 6 Enter adds a row (no submit), step 7")
    print("preserves values, and step 8 checks re-render cleanly.")
    print("FAIL otherwise (say which step).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
