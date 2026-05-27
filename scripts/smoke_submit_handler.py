"""Smoke: submit-handler slice — exit-criterion #8 of
`.overseer/slice/submit-handler.md`.

WARNING — MUTATES LIVE DATEV. Creates request letters + response docs
+ attachment files in the target VGM via the production mint pipeline
(`run_create_request`) and the real `POST /r/<token>/submit` handler.
Per ADR-0007 klardaten has no DELETE proxy; ALL pollution is permanent
until DATEV-UO manual cleanup. Run minimally — once per UNIT 4 closure
attempt, not iteratively during development.

USE THE DEV INSTANCE. The smoke does not interlock against a wrong env
(no automated check); the owner is responsible for pointing `.env` at
the dev tenant before running.

What it proves
--------------
Three sub-scenarios exercise the slice's three commit branches against
the real klardaten gateway, real Starlette HTTP stack, and real FastAPI
handler. Sub-D (partial_success) and Sub-E (all-files-failed) are
deferred to S1 unit-test coverage only per slice contract Phase 4 —
deterministically inducing klardaten-side per-file rejection requires
gateway-version-specific malformed payloads.

  Sub-A (full_success with files):
    1. Mint request L1 in the dev VGM (1 question).
    2. POST /r/T1/submit with 2 synthetic PDF blobs + 1 answer + Anmerkungen.
    3. Assert HTTP 200 + "Vielen Dank" template-text marker.
    4. Find the response doc (_response_<letter_id_1>_*.txt) in the binder.
    5. Download the response doc bytes; assert both attachment UUIDs
       appear in the ==ATTACHMENTS== section.
    6. Assert 3 new structure-items in the binder (1 response doc + 2 attachments).

  Sub-B (replay_rejected):
    1. Re-POST /r/T1/submit with the same token + (regenerated) files + form.
    2. Assert HTTP 200 + "Bereits eingereicht" template-text marker.
    3. Assert binder structure-item count UNCHANGED from end of Sub-A.

  Sub-C (full_success answers-only):
    1. Mint request L2 (new letter_id, new token T2) in the same VGM.
    2. POST /r/T2/submit with 0 files + non-empty answer (D7 satisfied via answer).
    3. Assert HTTP 200 + "Vielen Dank".
    4. Find the response doc (_response_<letter_id_2>_*.txt).
    5. Download; assert ==ATTACHMENTS== section is EMPTY (zero filename lines
       between the markers).

HTTP layer: in-process via FastAPI's TestClient (real Starlette stack
against real klardaten), NOT a browser. Per slice contract the smoke is
automatable; browser eyeballs are not required.

Pollution per run
-----------------
- 2 request letters via `run_create_request` (matches the production
  pattern; same as token-instance-binding's smoke pollution).
- 1 response doc from Sub-A + 2 attachments → 3 structure-items.
- 1 response doc from Sub-C → 1 structure-item.
- Total: 7 new structure-items in the dev VGM per run.
- Sub-B does NOT add anything (replay rejection short-circuits before any upload).

The smoke records all created structure_item_ids in the JSON output for
precise future cleanup (DATEV-UO manual per ADR-0007 no-DELETE).
Distinctive Mandant filenames `_smoke_attachment_<smoke_id>_<i>.pdf` make
grep-cleanup trivial.

Output
------
``artifacts/spikes/submit-handler-smoke-<YYYY-MM-DD>.json`` — exit code
0 = ``overall_pass`` true; 1 = any sub-scenario's cross-assertion failed.

Usage
-----
    uv run python scripts/smoke_submit_handler.py [VGM_NUMBER]

VGM_NUMBER defaults to 395357 (dev binder).
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
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

# Wire-format section markers, kept local rather than imported from
# response_format so this smoke is fully self-contained for the
# cross-assertions. Drift detector for ATTACHMENTS section parsing.
_ATTACHMENTS_MARKER = "==ATTACHMENTS=="
_FAILED_ATTACHMENTS_MARKER = "==FAILED_ATTACHMENTS=="


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
    to grep for in cross-assertions. One question so the submit form
    has an answer field to populate."""
    args = CreateRequestArgs.model_validate(
        {
            "vgm_id": vgm_guid,
            "to": "smoke@example.com",
            "cc": "",
            "subject": marker,
            "body": (
                f"Smoke letter for slice submit-handler.\n"
                f"Distinctive marker (also in subject): {marker}\n"
            ),
            "questions": ["Welche Bank?"],
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


def _find_items_by_prefix(
    items: list[dict[str, object]], prefix: str
) -> list[dict[str, object]]:
    """Return structure-items whose `name` starts with `prefix`."""
    return [
        item
        for item in items
        if isinstance(item.get("name"), str) and str(item["name"]).startswith(prefix)
    ]


def _extract_attachments_section(wire_text: str) -> list[str]:
    """Pull the lines between ``==ATTACHMENTS==`` and
    ``==FAILED_ATTACHMENTS==`` markers in a response doc. Empty list
    if no lines between them (the answers-only branch's expected shape)."""
    lines = wire_text.split("\n")
    if _ATTACHMENTS_MARKER not in lines or _FAILED_ATTACHMENTS_MARKER not in lines:
        raise AssertionError(f"response doc missing expected markers; lines: {lines!r}")
    start = lines.index(_ATTACHMENTS_MARKER)
    end = lines.index(_FAILED_ATTACHMENTS_MARKER)
    if not start < end:
        raise AssertionError(
            f"markers out of order: ATTACHMENTS at {start}, FAILED_ATTACHMENTS at {end}"
        )
    return [line for line in lines[start + 1 : end] if line]


def _run_sub_a(
    *,
    vgm_guid: str,
    klardaten: KlardatenClient,
    secret: str,
    base_url: str,
    now: datetime,
    smoke_id: str,
) -> dict[str, object]:
    """Sub-A: full_success with two files. Mint → POST → verify."""
    print("[Sub-A] mint request L1 ...", file=sys.stderr)
    marker = f"SMOKE_SUBA_{smoke_id}"
    url = _mint(
        vgm_guid=vgm_guid,
        marker=marker,
        klardaten=klardaten,
        secret=secret,
        base_url=base_url,
        now=now,
    )
    token = url.rsplit("/r/", 1)[1]
    payload = verify_token(token=token, secret=secret, now=now)

    pre_count = len(klardaten.list_structure_items(vgm_guid))
    print(
        f"[Sub-A] pre-POST binder count = {pre_count} (incl. fresh request letter)",
        file=sys.stderr,
    )

    file_payloads = [
        (
            "files",
            (
                f"_smoke_attachment_{smoke_id}_1.pdf",
                secrets.token_bytes(1024),
                "application/pdf",
            ),
        ),
        (
            "files",
            (
                f"_smoke_attachment_{smoke_id}_2.pdf",
                secrets.token_bytes(1024),
                "application/pdf",
            ),
        ),
    ]
    form_data = {"response": "Anbei zwei Scans (Smoke).", "answer_0": "Sparkasse."}

    app.dependency_overrides[get_letter_source] = lambda: klardaten
    app.dependency_overrides[get_secret] = lambda: secret
    app.dependency_overrides[get_now] = lambda: now
    try:
        client = TestClient(app, raise_server_exceptions=True)
        print("[Sub-A] POST /r/<T1>/submit ...", file=sys.stderr)
        r = client.post(f"/r/{token}/submit", data=form_data, files=file_payloads)
    finally:
        app.dependency_overrides.clear()

    http_ok = r.status_code == 200
    template_ok = "Vielen Dank" in r.text

    # Post-flow binder inspection.
    post_items = klardaten.list_structure_items(vgm_guid)
    response_doc_prefix = f"_response_{payload.letter_id}_"
    attachment_prefix = f"_attachment_{payload.letter_id}_"

    response_docs = _find_items_by_prefix(post_items, response_doc_prefix)
    attachments = _find_items_by_prefix(post_items, attachment_prefix)

    response_doc_id = str(response_docs[0]["id"]) if len(response_docs) == 1 else None
    attachment_ids = [str(a["id"]) for a in attachments]

    # Verify response doc body embeds the two attachment UUIDs.
    uuids_in_response_doc = False
    response_doc_attachment_lines: list[str] = []
    if response_doc_id is not None and len(attachments) == 2:
        dfid_raw = response_docs[0].get("document_file_id")
        if isinstance(dfid_raw, int):
            body = klardaten.download_document_file(dfid_raw).decode("utf-8")
            response_doc_attachment_lines = _extract_attachments_section(body)
            # Both attachment stored names should appear in the
            # ==ATTACHMENTS== section.
            attachment_stored_names = {str(a["name"]) for a in attachments}
            uuids_in_response_doc = attachment_stored_names == set(
                response_doc_attachment_lines
            )

    binder_count_delta = len(post_items) - pre_count
    cross_assertion_pass = (
        http_ok
        and template_ok
        and response_doc_id is not None
        and len(attachments) == 2
        and uuids_in_response_doc
        and binder_count_delta == 3  # 1 response doc + 2 attachments
    )

    print(
        f"[Sub-A] http={r.status_code} template_ok={template_ok} "
        f"response_docs={len(response_docs)} attachments={len(attachments)} "
        f"binder_count_delta={binder_count_delta} "
        f"uuids_in_response_doc={uuids_in_response_doc} "
        f"PASS={cross_assertion_pass}",
        file=sys.stderr,
    )

    return {
        "token": token,
        "letter_id": payload.letter_id,
        "http_status": r.status_code,
        "template_marker_present": template_ok,
        "response_doc_structure_item_id": response_doc_id,
        "attachment_structure_item_ids": attachment_ids,
        "response_doc_attachment_lines": response_doc_attachment_lines,
        "binder_count_pre": pre_count,
        "binder_count_post": len(post_items),
        "binder_count_delta": binder_count_delta,
        "uuids_in_response_doc": uuids_in_response_doc,
        "cross_assertion_pass": cross_assertion_pass,
    }


def _run_sub_b(
    *,
    vgm_guid: str,
    klardaten: KlardatenClient,
    secret: str,
    now: datetime,
    sub_a_token: str,
    sub_a_post_count: int,
    smoke_id: str,
) -> dict[str, object]:
    """Sub-B: re-POST same token. Replay check should short-circuit."""
    print("[Sub-B] re-POST /r/<T1>/submit (same token) ...", file=sys.stderr)
    file_payloads = [
        (
            "files",
            (
                f"_smoke_attachment_{smoke_id}_REPLAY.pdf",
                secrets.token_bytes(1024),
                "application/pdf",
            ),
        ),
    ]
    form_data = {
        "response": "Replay attempt.",
        "answer_0": "Sparkasse.",
    }

    app.dependency_overrides[get_letter_source] = lambda: klardaten
    app.dependency_overrides[get_secret] = lambda: secret
    app.dependency_overrides[get_now] = lambda: now
    try:
        client = TestClient(app, raise_server_exceptions=True)
        r = client.post(f"/r/{sub_a_token}/submit", data=form_data, files=file_payloads)
    finally:
        app.dependency_overrides.clear()

    http_ok = r.status_code == 200
    template_ok = "Bereits eingereicht" in r.text

    # Replay must NOT have added structure-items.
    post_items = klardaten.list_structure_items(vgm_guid)
    binder_count_unchanged = len(post_items) == sub_a_post_count

    cross_assertion_pass = http_ok and template_ok and binder_count_unchanged

    print(
        f"[Sub-B] http={r.status_code} template_ok={template_ok} "
        f"binder_count_unchanged={binder_count_unchanged} "
        f"PASS={cross_assertion_pass}",
        file=sys.stderr,
    )

    return {
        "token": sub_a_token,
        "http_status": r.status_code,
        "template_marker_present": template_ok,
        "binder_count_after": len(post_items),
        "binder_count_unchanged_from_sub_a": binder_count_unchanged,
        "cross_assertion_pass": cross_assertion_pass,
    }


def _run_sub_c(
    *,
    vgm_guid: str,
    klardaten: KlardatenClient,
    secret: str,
    base_url: str,
    now: datetime,
    smoke_id: str,
) -> dict[str, object]:
    """Sub-C: answers-only submit (zero files). Mint fresh token T2."""
    print("[Sub-C] mint request L2 ...", file=sys.stderr)
    marker = f"SMOKE_SUBC_{smoke_id}"
    # +2s so the request-letter ISO filename differs from L1's (1s
    # precision; we already burned now/now+1s in L1's lifecycle).
    now2 = now + timedelta(seconds=2)
    url = _mint(
        vgm_guid=vgm_guid,
        marker=marker,
        klardaten=klardaten,
        secret=secret,
        base_url=base_url,
        now=now2,
    )
    token = url.rsplit("/r/", 1)[1]
    payload = verify_token(token=token, secret=secret, now=now2)

    pre_count = len(klardaten.list_structure_items(vgm_guid))
    print(
        f"[Sub-C] pre-POST binder count = {pre_count}",
        file=sys.stderr,
    )

    # Zero files; non-empty answer satisfies D7.
    form_data = {"answer_0": "Volksbank.", "response": ""}

    app.dependency_overrides[get_letter_source] = lambda: klardaten
    app.dependency_overrides[get_secret] = lambda: secret
    app.dependency_overrides[get_now] = lambda: now2
    try:
        client = TestClient(app, raise_server_exceptions=True)
        print("[Sub-C] POST /r/<T2>/submit (no files) ...", file=sys.stderr)
        r = client.post(f"/r/{token}/submit", data=form_data)
    finally:
        app.dependency_overrides.clear()

    http_ok = r.status_code == 200
    template_ok = "Vielen Dank" in r.text

    post_items = klardaten.list_structure_items(vgm_guid)
    response_doc_prefix = f"_response_{payload.letter_id}_"
    response_docs = _find_items_by_prefix(post_items, response_doc_prefix)
    response_doc_id = str(response_docs[0]["id"]) if len(response_docs) == 1 else None

    # Verify the response doc's ==ATTACHMENTS== section is empty.
    attachments_section_empty = False
    response_doc_attachment_lines: list[str] = []
    if response_doc_id is not None:
        dfid_raw = response_docs[0].get("document_file_id")
        if isinstance(dfid_raw, int):
            body = klardaten.download_document_file(dfid_raw).decode("utf-8")
            response_doc_attachment_lines = _extract_attachments_section(body)
            attachments_section_empty = len(response_doc_attachment_lines) == 0

    binder_count_delta = len(post_items) - pre_count
    cross_assertion_pass = (
        http_ok
        and template_ok
        and response_doc_id is not None
        and attachments_section_empty
        and binder_count_delta == 1  # only the response doc
    )

    print(
        f"[Sub-C] http={r.status_code} template_ok={template_ok} "
        f"response_docs={len(response_docs)} "
        f"attachments_section_empty={attachments_section_empty} "
        f"binder_count_delta={binder_count_delta} "
        f"PASS={cross_assertion_pass}",
        file=sys.stderr,
    )

    return {
        "token": token,
        "letter_id": payload.letter_id,
        "http_status": r.status_code,
        "template_marker_present": template_ok,
        "response_doc_structure_item_id": response_doc_id,
        "response_doc_attachment_lines": response_doc_attachment_lines,
        "attachments_section_empty": attachments_section_empty,
        "binder_count_pre": pre_count,
        "binder_count_post": len(post_items),
        "binder_count_delta": binder_count_delta,
        "cross_assertion_pass": cross_assertion_pass,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke for slice submit-handler: exercises the POST handler's "
            "three commit branches (Sub-A full_success with files, "
            "Sub-B replay_rejected, Sub-C full_success answers-only) "
            "against real klardaten via TestClient."
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

    vgm_guid = resolve_binder_guid_by_number(klardaten, parsed.vgm_number)
    if vgm_guid is None:
        print(
            f"VGM Dokumentnummer {parsed.vgm_number} not found (or not a "
            f"Vorgangsmappe) — pick another dev VGM.",
            file=sys.stderr,
        )
        return 1

    smoke_id = uuid4().hex[:8]
    started_at = datetime.now(timezone.utc)
    # Single `now` clock for Sub-A and Sub-B; Sub-C gets +2s inside its
    # helper so L2's filename ISO differs from L1's.
    now = started_at

    sub_a = _run_sub_a(
        vgm_guid=vgm_guid,
        klardaten=klardaten,
        secret=secret,
        base_url=base_url,
        now=now,
        smoke_id=smoke_id,
    )

    sub_a_token_value = sub_a["token"]
    sub_a_post_count_value = sub_a["binder_count_post"]
    assert isinstance(sub_a_token_value, str)
    assert isinstance(sub_a_post_count_value, int)
    sub_b = _run_sub_b(
        vgm_guid=vgm_guid,
        klardaten=klardaten,
        secret=secret,
        now=now,
        sub_a_token=sub_a_token_value,
        sub_a_post_count=sub_a_post_count_value,
        smoke_id=smoke_id,
    )

    sub_c = _run_sub_c(
        vgm_guid=vgm_guid,
        klardaten=klardaten,
        secret=secret,
        base_url=base_url,
        now=now,
        smoke_id=smoke_id,
    )

    overall_pass = bool(
        sub_a["cross_assertion_pass"]
        and sub_b["cross_assertion_pass"]
        and sub_c["cross_assertion_pass"]
    )

    output: dict[str, object] = {
        "slice": "submit-handler",
        "smoke_id": smoke_id,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "vgm_number": parsed.vgm_number,
        "vgm_binder_guid": vgm_guid,
        "sub_a_full_success": sub_a,
        "sub_b_replay_rejected": sub_b,
        "sub_c_answers_only": sub_c,
        "overall_pass": overall_pass,
    }

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACTS_DIR / f"submit-handler-smoke-{today}.json"
    out_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

    print(file=sys.stderr)
    print("=" * 72, file=sys.stderr)
    print(f"smoke output: {out_path}", file=sys.stderr)
    print(f"overall PASS: {overall_pass}", file=sys.stderr)
    print(
        f"  Sub-A (full_success with files):     {sub_a['cross_assertion_pass']}",
        file=sys.stderr,
    )
    print(
        f"  Sub-B (replay_rejected):             {sub_b['cross_assertion_pass']}",
        file=sys.stderr,
    )
    print(
        f"  Sub-C (full_success answers-only):   {sub_c['cross_assertion_pass']}",
        file=sys.stderr,
    )
    print(
        f"smoke_id={smoke_id} — cleanup grep: '_smoke_attachment_{smoke_id}'",
        file=sys.stderr,
    )
    print("=" * 72, file=sys.stderr)

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
