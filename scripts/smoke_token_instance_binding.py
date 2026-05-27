"""Smoke: token-instance-binding — exit-criterion #5 of slice
`.overseer/slice/token-instance-binding.md`.

WARNING — MUTATES LIVE DATEV. Creates two real `_request_letter_*.txt`
artifacts inside the target VGM via `run_create_request` against the
real klardaten instance configured in `.env`. Each run leaves two new
structure-items in the binder; cleanup is OUT-of-scope this slice
(captured in the slice contract's "Deferred" section). The smoke's
output JSON records both `structure_item_id`s so future cleanup can
target them precisely.

USE THE DEV INSTANCE. The smoke does not interlock against a wrong env
(no automated check); the owner is responsible for pointing `.env` at
the dev tenant before running.

What it proves (the slice's primary regression guard against the
magic-link-ui smoke bug):

    1. Create request L1 in VGM V    → token T1 + letter_id_1
    2. Create request L2 in VGM V    → token T2 + letter_id_2  (distinct)
    3. GET /r/T1 → response carries L1's distinctive subject marker
                   AND does NOT carry L2's marker      ← bug-detector
    4. GET /r/T2 → response carries L2's marker
                   AND does NOT carry L1's marker      ← bug-detector

Cross-assertion #3/#4 are the load-bearing NOT-in checks — without them
a "200 OK + non-empty body" smoke passes even under the original bug
("newest letter wins") that this slice exists to fix.

HTTP layer: in-process via FastAPI's `TestClient` (real Starlette
stack), NOT a browser. Per slice contract Phase 1 the smoke is
automatable; browser eyeballs are not required.

Filename caveat: the smoke uses the production `_request_letter_<ISO>.txt`
naming via `run_create_request`, not the artifact-suggested
`_smoke_letter_<UUID>.txt` prefix — changing the filename would mean
touching production source for the smoke's convenience (out of scope).
A unique smoke-id and the recorded `structure_item_id`s in the output
JSON serve as the cleanup breadcrumb.

Output:
    artifacts/spikes/token-instance-binding-smoke-<YYYY-MM-DD>.json

Exit code 0 = all four cross-assertions PASS; 1 = any failed.

Usage:
    uv run python scripts/smoke_token_instance_binding.py [VGM_NUMBER]

VGM_NUMBER defaults to 395357 (dev binder used by
`artifacts/spikes/submit-letter-discovery-2026-05-26.md`).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi.testclient import TestClient

from belegmeister.cli.create_request import CreateRequestArgs, run_create_request
from belegmeister.datev.resolver import resolve_binder_guid_by_number
from belegmeister.klardaten.client import KlardatenClient
from belegmeister.magic_link.token import verify_token
from belegmeister.web.app import app, get_letter_source, get_now, get_secret

DEFAULT_VGM_NUMBER = 395357
ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "spikes"


def _build_client() -> KlardatenClient:
    return KlardatenClient(
        base_url=os.environ.get("KLARDATEN_BASE_URL", "https://api.klardaten.com"),
        api_key=os.environ["KLARDATEN_API_KEY"],
        instance_id=os.environ["KLARDATEN_INSTANCE_ID"],
        profile_id=os.environ.get("KLARDATEN_PROFILE_ID") or None,
    )


def _mint(
    *,
    vgm_guid: str,
    marker: str,
    klardaten: KlardatenClient,
    secret: str,
    base_url: str,
    now: datetime,
) -> str:
    """Create one request via the production mint pipeline and return
    the magic-link URL. Subject = marker so the rendered page is easy
    to grep for in cross-assertions."""
    args = CreateRequestArgs.model_validate(
        {
            "vgm_id": vgm_guid,
            "to": "smoke@example.com",
            "cc": "",
            "subject": marker,
            "body": (
                f"Smoke letter for slice token-instance-binding.\n"
                f"Distinctive marker (also in subject): {marker}\n"
            ),
            "questions": [],
            "expires_at": now + timedelta(days=1),
        },
        context={"now": now},
    )
    return run_create_request(
        args,
        klardaten_client=klardaten,
        magic_link_secret=secret,
        magic_link_base_url=base_url,
        now=now,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke for slice token-instance-binding: creates two real "
            "requests in the same VGM and asserts each /r/<token> "
            "renders only its own letter's content."
        )
    )
    parser.add_argument(
        "vgm_number",
        nargs="?",
        type=int,
        default=DEFAULT_VGM_NUMBER,
        help=f"VGM Dokumentnummer (default: {DEFAULT_VGM_NUMBER})",
    )
    parsed = parser.parse_args()

    load_dotenv()
    secret = os.environ["MAGIC_LINK_SECRET"]
    base_url = os.environ["MAGIC_LINK_BASE_URL"]
    klardaten = _build_client()

    # Single-call number → GUID lookup (post-ADR-0005, fast).
    vgm_guid = resolve_binder_guid_by_number(klardaten, parsed.vgm_number)
    if vgm_guid is None:
        print(
            f"VGM Dokumentnummer {parsed.vgm_number} not found (or not a "
            f"Vorgangsmappe) — pick another dev VGM.",
            file=sys.stderr,
        )
        return 1

    # Per-run UUID so concurrent / repeated smokes never collide on
    # marker substrings and the JSON output can be matched to a run.
    smoke_id = uuid4().hex[:8]
    l1_marker = f"SMOKE_L1_{smoke_id}"
    l2_marker = f"SMOKE_L2_{smoke_id}"

    now1 = datetime.now(timezone.utc)
    url1 = _mint(
        vgm_guid=vgm_guid,
        marker=l1_marker,
        klardaten=klardaten,
        secret=secret,
        base_url=base_url,
        now=now1,
    )

    # L2 uses a `now` 1s later so its filename ISO timestamp differs
    # from L1's (filename precision is seconds). `expires_at` is still
    # within MAX_TTL_DAYS of L2's now.
    now2 = now1 + timedelta(seconds=1)
    url2 = _mint(
        vgm_guid=vgm_guid,
        marker=l2_marker,
        klardaten=klardaten,
        secret=secret,
        base_url=base_url,
        now=now2,
    )

    t1 = url1.rsplit("/r/", 1)[1]
    t2 = url2.rsplit("/r/", 1)[1]
    # `now2` is the reference clock for the fetches below; both tokens'
    # `exp` are well in the future of it.
    payload1 = verify_token(token=t1, secret=secret, now=now2)
    payload2 = verify_token(token=t2, secret=secret, now=now2)

    # Real Starlette HTTP stack via TestClient, real klardaten upstream.
    app.dependency_overrides[get_letter_source] = lambda: klardaten
    app.dependency_overrides[get_secret] = lambda: secret
    app.dependency_overrides[get_now] = lambda: now2
    try:
        client = TestClient(app, raise_server_exceptions=True)
        r1 = client.get(f"/r/{t1}")
        r2 = client.get(f"/r/{t2}")
    finally:
        app.dependency_overrides.clear()

    # Cross-assertions — the IN checks confirm happy path; the NOT-IN
    # checks are the load-bearing bug-detectors.
    l1_marker_in_t1 = r1.status_code == 200 and l1_marker in r1.text
    l2_marker_in_t2 = r2.status_code == 200 and l2_marker in r2.text
    l2_marker_not_in_t1 = l2_marker not in r1.text
    l1_marker_not_in_t2 = l1_marker not in r2.text

    # Slice exit-criterion #7: CLI external-surface sanity — the printed
    # URL's token decodes to a 3-field payload {vgm_id, letter_id, exp}
    # with non-empty letter_id. We piggyback on the verify_token round-
    # trip we already did.
    sanity = {
        "T1_payload_fields": sorted(
            ["vgm_id", "letter_id", "exp"]
            if (payload1.vgm_id and payload1.letter_id and payload1.exp)
            else []
        ),
        "T2_payload_fields": sorted(
            ["vgm_id", "letter_id", "exp"]
            if (payload2.vgm_id and payload2.letter_id and payload2.exp)
            else []
        ),
        "letter_ids_distinct": payload1.letter_id != payload2.letter_id,
        "vgm_ids_both_match_target": (
            payload1.vgm_id == vgm_guid and payload2.vgm_id == vgm_guid
        ),
    }
    sanity_ok = (
        sanity["T1_payload_fields"] == ["exp", "letter_id", "vgm_id"]
        and sanity["T2_payload_fields"] == ["exp", "letter_id", "vgm_id"]
        and sanity["letter_ids_distinct"]
        and sanity["vgm_ids_both_match_target"]
    )

    cross = {
        "L1_marker_in_T1_body": l1_marker_in_t1,
        "L2_marker_in_T2_body": l2_marker_in_t2,
        "L2_marker_NOT_in_T1_body": l2_marker_not_in_t1,
        "L1_marker_NOT_in_T2_body": l1_marker_not_in_t2,
    }
    overall_pass = all(cross.values()) and sanity_ok

    output: dict[str, object] = {
        "slice": "token-instance-binding",
        "smoke_id": smoke_id,
        "started_at": now1.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "vgm_number": parsed.vgm_number,
        "vgm_guid": vgm_guid,
        "letters_created": [
            {
                "role": "L1",
                "marker": l1_marker,
                "url": url1,
                "letter_id": payload1.letter_id,
                "exp_unix": payload1.exp,
            },
            {
                "role": "L2",
                "marker": l2_marker,
                "url": url2,
                "letter_id": payload2.letter_id,
                "exp_unix": payload2.exp,
            },
        ],
        "http_responses": [
            {"token_role": "T1", "status": r1.status_code, "body_len": len(r1.text)},
            {"token_role": "T2", "status": r2.status_code, "body_len": len(r2.text)},
        ],
        "cross_assertions": cross,
        "cli_payload_sanity": sanity,
        "overall_pass": overall_pass,
    }

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACTS_DIR / f"token-instance-binding-smoke-{today}.json"
    out_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

    print(f"smoke output: {out_path}")
    print(f"overall PASS: {overall_pass}")
    if not overall_pass:
        print("cross_assertions:", json.dumps(cross, indent=2))
        print("sanity:", json.dumps(sanity, indent=2))

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
