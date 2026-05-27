"""Spike: klardaten DELETE semantics (Phase-0 premise A9 for submit-handler).

Premise under test
------------------
**A9** — *"Klardaten supports DELETE on `/document-files/{id}` and
`/documents/{vgm}/structure-items/{id}` cleanly enough to use as a
rollback primitive for all-or-nothing multi-file uploads."*

If A9 is VERIFIED, submit-handler D6 locks as **all-or-nothing**: when
upload N of M fails, the handler issues DELETE on the N-1 succeeded
structure-items + their document-files. Mandant sees one "submission
failed, please retry" page; binder is left in a clean state with no
orphans.

If A9 is FALSIFIED (DELETE 404s / 405s / silently no-ops / returns
errors), D6 falls back to **best-effort with partial-success UX**:
handler accepts partial commits, surfaces "K of N uploaded, retry"
to Mandant, and the response doc records the partial state. The fallback
is a fundamentally different slice — different error taxonomy, different
response-doc semantics, different ordering in D8.

Procedure
---------
1. Upload a single synthetic 1 MB blob to the dev VGM (production
   `KlardatenClient.attach_file_to_binder` seam). Capture
   `document_file_id` (int) and `structure_item_id` (str).
2. `DELETE /datevconnect/dms/v2/documents/{binder_guid}/structure-items/
   {structure_item_id}` — record status, response body excerpt,
   elapsed seconds.
3. `DELETE /datevconnect/dms/v2/document-files/{document_file_id}` —
   record status, response body excerpt, elapsed seconds.
4. `KlardatenClient.list_structure_items(binder_guid)` and confirm the
   deleted structure-item is absent.
5. Edge case A: repeat both DELETEs on the now-already-deleted ids.
   Record status (404 expected; 200 idempotent acceptable; 500 is a
   yellow flag that complicates rollback retries).
6. Edge case B: DELETE both endpoints with definitely-nonexistent ids
   (`structure_item_id="0"`, `document_file_id=0`). Record status.
   Tells us whether "delete a never-existed id" looks the same as
   "delete an already-deleted id" — affects rollback idempotency design.
7. Write `artifacts/spikes/klardaten-delete-semantics-2026-05-26.json`.

Output schema
-------------
::

    {
      "vgm_binder_guid": "...",
      "uploaded": {"document_file_id": <int>, "structure_item_id": "...",
                   "elapsed_s": <float>},
      "structure_item_delete":  {"status": <int|null>, "response_body_excerpt": "...",
                                 "elapsed_s": <float>, "error_class": <str|null>},
      "document_file_delete":   {"status": <int|null>, "response_body_excerpt": "...",
                                 "elapsed_s": <float>, "error_class": <str|null>},
      "verified_absent_from_list": <bool>,
      "double_delete_structure_item": {"status": ..., ...},
      "double_delete_document_file":  {"status": ..., ...},
      "nonexistent_delete_structure_item": {"status": ..., ...},
      "nonexistent_delete_document_file":  {"status": ..., ...},
      "supports_all_or_nothing_rollback": <bool>,
      "notes": "<one-line summary for ADR-0007>"
    }

The ``supports_all_or_nothing_rollback`` boolean is the load-bearing
A9 verdict:

  - True iff steps 2 + 3 returned 2xx AND step 4 confirmed absence
    (DELETE actually removed the data, not just acknowledged it).
  - All other outcomes (any 4xx/5xx on the real-delete path, any
    failure to verify absence) → False, D6 falls back to best-effort.

Edge-case outcomes are recorded but DO NOT determine the boolean — they
inform Phase 3's rollback-idempotency design.

Spike-only liberty
------------------
This script calls httpx directly for DELETE because ``KlardatenClient``
does not (yet) expose ``delete_*`` methods — we are discovering whether
to ADD them. The upload step DOES go through the production seam
(``attach_file_to_binder``) so the uploaded artifact is real and
indistinguishable from production traffic. Production code MUST NOT
issue ad-hoc httpx calls — that pattern lives only in spikes.

WARNING — MUTATES LIVE DATEV. Use the dev instance. Script uploads
exactly one synthetic blob to the target VGM, then attempts to delete
it. On success the binder is left in the same state as before the run.
On any DELETE failure, the synthetic blob is left in the binder
(filename ``_a9_probe_<UUID>.pdf`` for trivial cleanup).

Usage
-----
::

    uv run python scripts/probe_klardaten_delete_semantics_2026-05-26.py

Required env (loaded from .env via python-dotenv):
    KLARDATEN_API_KEY
    KLARDATEN_INSTANCE_ID

Optional env:
    KLARDATEN_BASE_URL          (default https://api.klardaten.com)
    KLARDATEN_PROFILE_ID
    SPIKE_VGM_BINDER_GUID       (default 4c83e94e-24e7-4866-809c-5e983ad7f485 — dev VGM 395357)
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from belegmeister.klardaten.client import KlardatenClient

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = REPO_ROOT / "artifacts" / "spikes"
OUTPUT_PATH = ARTIFACTS_DIR / "klardaten-delete-semantics-2026-05-26.json"

DEFAULT_BINDER_GUID = "4c83e94e-24e7-4866-809c-5e983ad7f485"  # VGM 395357, dev
ONE_MB = 1024 * 1024
PROBE_TIMEOUT_S = 60.0
NONEXISTENT_STRUCTURE_ITEM_ID = "0"
NONEXISTENT_DOCUMENT_FILE_ID = 0


def _auth_headers(client: KlardatenClient) -> dict[str, str]:
    """Re-create the wire-level header set used by KlardatenClient.

    Public API does not expose this; we replicate the structure because
    raw DELETE calls below cannot go through the typed seam.
    """
    headers = {
        "Authorization": f"Bearer {client.api_key}",
        "X-Client-Instance-Id": client.instance_id,
    }
    if client.profile_id:
        headers["X-Profile-Id"] = client.profile_id
    return headers


def _delete(url: str, headers: dict[str, str]) -> dict[str, Any]:
    """Issue a DELETE and record the wire outcome.

    Returns a dict with status / response_body_excerpt / elapsed_s /
    error_class. Never raises; the whole point is to observe the
    server's reaction.
    """
    started = time.monotonic()
    try:
        with httpx.Client(timeout=PROBE_TIMEOUT_S) as http:
            response = http.delete(url, headers=headers)
    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - started
        return {
            "status": None,
            "response_body_excerpt": "",
            "elapsed_s": round(elapsed, 2),
            "error_class": type(exc).__name__,
            "error_message": str(exc)[:500],
        }
    elapsed = time.monotonic() - started
    return {
        "status": response.status_code,
        "response_body_excerpt": response.text[:2000],
        "elapsed_s": round(elapsed, 2),
        "error_class": None,
    }


def _structure_item_url(base_url: str, binder_guid: str, structure_item_id: str) -> str:
    return (
        f"{base_url.rstrip('/')}/datevconnect/dms/v2/documents/"
        f"{binder_guid}/structure-items/{structure_item_id}"
    )


def _document_file_url(base_url: str, document_file_id: int) -> str:
    return (
        f"{base_url.rstrip('/')}/datevconnect/dms/v2/document-files/{document_file_id}"
    )


def main() -> int:
    load_dotenv()
    api_key = os.environ.get("KLARDATEN_API_KEY")
    instance_id = os.environ.get("KLARDATEN_INSTANCE_ID")
    base_url = os.environ.get("KLARDATEN_BASE_URL", "https://api.klardaten.com")
    profile_id = os.environ.get("KLARDATEN_PROFILE_ID") or None
    binder_guid = os.environ.get("SPIKE_VGM_BINDER_GUID", DEFAULT_BINDER_GUID)

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

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    client = KlardatenClient(
        base_url=base_url,
        api_key=api_key,
        instance_id=instance_id,
        profile_id=profile_id,
        timeout=PROBE_TIMEOUT_S,
    )

    # Guardrail: confirm target is actually a VGM.
    print(
        f"Validating target binder {binder_guid} is a Vorgangsmappe ...",
        file=sys.stderr,
    )
    binder = client.get_document(binder_guid)
    is_binder = binder.get("is_binder")
    extension = binder.get("extension")
    if is_binder is not True or extension != "VGM":
        print(
            f"FAIL: target {binder_guid} is not a Vorgangsmappe "
            f"(is_binder={is_binder!r}, extension={extension!r})",
            file=sys.stderr,
        )
        return 3
    print(
        f"  OK is_binder=True extension=VGM number={binder.get('number')!r}",
        file=sys.stderr,
    )

    # STEP 1: upload synthetic 1 MB blob via production seam.
    file_name = f"_a9_probe_{uuid.uuid4().hex[:8]}.pdf"
    payload = secrets.token_bytes(ONE_MB)
    print(
        f"[1/7] Uploading {file_name} (1 MB) via attach_file_to_binder ...",
        file=sys.stderr,
    )
    started_upload = time.monotonic()
    structure_item = client.attach_file_to_binder(
        binder_guid=binder_guid, file_name=file_name, file_bytes=payload
    )
    elapsed_upload = time.monotonic() - started_upload
    structure_item_id = structure_item.get("id")
    document_file_id_raw = structure_item.get("document_file_id")
    if not isinstance(structure_item_id, str) or not structure_item_id:
        print(
            f"FAIL: structure-items response missing usable id: {structure_item!r}",
            file=sys.stderr,
        )
        return 4
    if not isinstance(document_file_id_raw, int):
        print(
            f"FAIL: structure-items response missing usable document_file_id: "
            f"{structure_item!r}",
            file=sys.stderr,
        )
        return 4
    document_file_id: int = document_file_id_raw
    print(
        f"  -> document_file_id={document_file_id} "
        f"structure_item_id={structure_item_id} "
        f"elapsed={elapsed_upload:.2f}s",
        file=sys.stderr,
    )

    headers = _auth_headers(client)

    # STEP 2: DELETE the structure-item.
    si_url = _structure_item_url(base_url, binder_guid, structure_item_id)
    print(f"[2/7] DELETE {si_url} ...", file=sys.stderr)
    si_delete = _delete(si_url, headers)
    print(
        f"  -> status={si_delete['status']!r} "
        f"elapsed={si_delete['elapsed_s']}s "
        f"error_class={si_delete['error_class']!r}",
        file=sys.stderr,
    )

    # STEP 3: DELETE the underlying document-file.
    df_url = _document_file_url(base_url, document_file_id)
    print(f"[3/7] DELETE {df_url} ...", file=sys.stderr)
    df_delete = _delete(df_url, headers)
    print(
        f"  -> status={df_delete['status']!r} "
        f"elapsed={df_delete['elapsed_s']}s "
        f"error_class={df_delete['error_class']!r}",
        file=sys.stderr,
    )

    # STEP 4: verify absence via list_structure_items.
    print(
        "[4/7] list_structure_items -> confirm uploaded id absent ...",
        file=sys.stderr,
    )
    try:
        items = client.list_structure_items(binder_guid)
    except Exception as exc:  # noqa: BLE001
        print(
            f"  list failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        items = []
    present_ids = {item.get("id") for item in items if isinstance(item, dict)}
    verified_absent = structure_item_id not in present_ids
    print(
        f"  -> verified_absent={verified_absent} "
        f"(binder has {len(items)} items post-delete)",
        file=sys.stderr,
    )

    # STEP 5a: double-delete the structure-item.
    print(f"[5/7] DELETE (idempotent) {si_url} ...", file=sys.stderr)
    si_double_delete = _delete(si_url, headers)
    print(
        f"  -> status={si_double_delete['status']!r}",
        file=sys.stderr,
    )

    # STEP 5b: double-delete the document-file.
    print(f"[6/7] DELETE (idempotent) {df_url} ...", file=sys.stderr)
    df_double_delete = _delete(df_url, headers)
    print(
        f"  -> status={df_double_delete['status']!r}",
        file=sys.stderr,
    )

    # STEP 6: DELETE definitely-nonexistent ids.
    nonexistent_si_url = _structure_item_url(
        base_url, binder_guid, NONEXISTENT_STRUCTURE_ITEM_ID
    )
    nonexistent_df_url = _document_file_url(base_url, NONEXISTENT_DOCUMENT_FILE_ID)
    print(
        f"[7/7] DELETE nonexistent ids "
        f"(si={NONEXISTENT_STRUCTURE_ITEM_ID}, df={NONEXISTENT_DOCUMENT_FILE_ID}) ...",
        file=sys.stderr,
    )
    nonexistent_si_delete = _delete(nonexistent_si_url, headers)
    nonexistent_df_delete = _delete(nonexistent_df_url, headers)
    print(
        f"  -> si_status={nonexistent_si_delete['status']!r} "
        f"df_status={nonexistent_df_delete['status']!r}",
        file=sys.stderr,
    )

    # Compose the load-bearing verdict.
    def _is_2xx(status: int | None) -> bool:
        return status is not None and 200 <= status < 300

    si_status_raw = si_delete["status"]
    df_status_raw = df_delete["status"]
    si_status = si_status_raw if isinstance(si_status_raw, int) else None
    df_status = df_status_raw if isinstance(df_status_raw, int) else None
    supports_rollback = _is_2xx(si_status) and _is_2xx(df_status) and verified_absent

    notes_parts: list[str] = []
    if supports_rollback:
        notes_parts.append("DELETE works on both endpoints; absence verified.")
    else:
        notes_parts.append("DELETE path NOT clean; D6 must fall back to best-effort.")
    if si_double_delete["status"] != si_delete["status"]:
        notes_parts.append(
            f"structure-item double-delete differs "
            f"({si_delete['status']!r} → {si_double_delete['status']!r})."
        )
    if nonexistent_si_delete["status"] != si_double_delete["status"]:
        notes_parts.append(
            f"never-existed vs already-deleted structure-item differ "
            f"({nonexistent_si_delete['status']!r} vs {si_double_delete['status']!r})."
        )

    completed_at = datetime.now(timezone.utc)
    payload_out: dict[str, object] = {
        "vgm_binder_guid": binder_guid,
        "vgm_number": binder.get("number"),
        "completed_at": completed_at.isoformat(),
        "uploaded": {
            "file_name": file_name,
            "document_file_id": document_file_id,
            "structure_item_id": structure_item_id,
            "elapsed_s": round(elapsed_upload, 2),
        },
        "structure_item_delete": si_delete,
        "document_file_delete": df_delete,
        "verified_absent_from_list": verified_absent,
        "double_delete_structure_item": si_double_delete,
        "double_delete_document_file": df_double_delete,
        "nonexistent_delete_structure_item": nonexistent_si_delete,
        "nonexistent_delete_document_file": nonexistent_df_delete,
        "supports_all_or_nothing_rollback": supports_rollback,
        "notes": " ".join(notes_parts),
    }
    OUTPUT_PATH.write_text(json.dumps(payload_out, indent=2) + "\n", encoding="utf-8")

    print(file=sys.stderr)
    print("=" * 72, file=sys.stderr)
    print(f"Evidence written to: {OUTPUT_PATH}", file=sys.stderr)
    print(f"  supports_all_or_nothing_rollback = {supports_rollback}", file=sys.stderr)
    print(f"  notes: {payload_out['notes']}", file=sys.stderr)
    if not supports_rollback:
        print(
            f"NOTE: uploaded blob {file_name} may remain in the binder "
            f"(structure_item_id={structure_item_id}). Cleanup manual.",
            file=sys.stderr,
        )
    print("=" * 72, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
