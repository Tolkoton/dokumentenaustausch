"""Spike: klardaten upload-size envelope (Phase-0 premise A5 for submit-handler).

Premise under test
------------------
**A5** — *"Klardaten accepts realistic-size Mandant uploads (e.g. 50-100 MB
PDFs / phone-camera scans)."* The submit-multi-file-upload spike (2026-05-26)
confirmed 7.2 MB PDF + 5.8 MB JPG; nothing above that has been exercised. If
the endpoint silently rejects (or HTTP-errors) at, e.g., 50 MB, the submit
handler would ship with a silent regression (Mandant submits a scan, sees
an error or stalls, gives up — operationally invisible to the SB).

Procedure
---------
For each candidate size in 25 / 50 / 100 / 200 MB:

  1. Generate `random.randbytes(N)` (NOT a real PDF — klardaten does not
     validate PDF structure; we are exercising its size/transport handling,
     not its content sniffing).
  2. Upload via ``KlardatenClient.attach_file_to_binder`` (the production
     two-step seam). Filename ``_size_probe_<N>MB_<UUID>.pdf`` for trivial
     cleanup-by-grep later.
  3. Record HTTP outcome (status, elapsed seconds, document_file_id on
     success, response body on error).
  4. STOP on the first hard failure (any non-2xx, any httpx transport
     error, any client-side exception). All prior sizes are still recorded;
     ``first_failure_size_mb`` is set to the size that failed.

Output
------
``artifacts/spikes/klardaten-size-envelope-2026-05-26.json``::

    {
      "vgm_binder_guid": "...",
      "started_at": "...",
      "completed_at": "...",
      "runs": [
        {"size_mb": 25,  "status": 200, "elapsed_s": 4.2, "document_file_id": ...,
         "structure_item_id": "...", "file_name": "_size_probe_25MB_<UUID>.pdf"},
        ...
      ],
      "first_failure_size_mb": <int or null>,
      "max_confirmed_mb": <int>
    }

Exit code 0 = ran to completion (whether every size passed or stopped on a
real failure with the JSON recorded). Non-zero = setup error (missing env,
wrong target type, etc.) — distinct from "klardaten rejected size N", which
is empirical data and exits 0 with the JSON.

Cleanup
-------
NONE in this script. Filename prefix ``_size_probe_<N>MB_*`` is the
breadcrumb; structure_item_ids are also captured in the JSON for precise
targeting once klardaten DELETE semantics are known.

WARNING — MUTATES LIVE DATEV. Use the dev instance. The script does not
interlock against pointing at a wrong env.

Usage
-----
::

    uv run python scripts/probe_klardaten_size_envelope_2026-05-26.py
    SPIKE_VGM_BINDER_GUID=<guid> uv run python scripts/probe_klardaten_size_envelope_2026-05-26.py
    SPIKE_SIZES_MB=25,50 uv run python scripts/probe_klardaten_size_envelope_2026-05-26.py

Required env (loaded from .env via python-dotenv):
    KLARDATEN_API_KEY
    KLARDATEN_INSTANCE_ID

Optional env:
    KLARDATEN_BASE_URL         (default https://api.klardaten.com)
    KLARDATEN_PROFILE_ID
    SPIKE_VGM_BINDER_GUID      (default 4c83e94e-24e7-4866-809c-5e983ad7f485 — dev VGM 395357)
    SPIKE_SIZES_MB             (default "25,50,100,200" — comma-separated MB ints)
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

import httpx
from dotenv import load_dotenv

from belegmeister.klardaten.client import KlardatenClient

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = REPO_ROOT / "artifacts" / "spikes"
OUTPUT_PATH = ARTIFACTS_DIR / "klardaten-size-envelope-2026-05-26.json"

DEFAULT_BINDER_GUID = "4c83e94e-24e7-4866-809c-5e983ad7f485"  # VGM 395357, dev
DEFAULT_SIZES_MB = (25, 50, 100, 200)
# 200 MB upload over a slow link can easily exceed 60s. 15 min budget per call.
SPIKE_TIMEOUT_S = 900.0
ONE_MB = 1024 * 1024


def _parse_sizes(raw: str | None) -> tuple[int, ...]:
    if not raw:
        return DEFAULT_SIZES_MB
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    sizes: list[int] = []
    for part in parts:
        try:
            n = int(part)
        except ValueError as exc:
            raise SystemExit(
                f"FAIL: SPIKE_SIZES_MB entries must be integer MB, got {part!r}"
            ) from exc
        if n <= 0:
            raise SystemExit(f"FAIL: SPIKE_SIZES_MB entries must be > 0, got {n}")
        sizes.append(n)
    return tuple(sizes)


def _one_run(
    client: KlardatenClient, binder_guid: str, size_mb: int
) -> tuple[dict[str, object], bool]:
    """Upload one synthetic blob of ``size_mb`` MB. Return (record, success).

    On success: record carries status=200, document_file_id, structure_item_id.
    On HTTPStatusError: record carries the non-2xx status + response body
    (truncated). On any other exception: record carries an "error" field
    with the exception class name + message. ``success`` is False for any
    non-2xx / exception.
    """
    file_name = f"_size_probe_{size_mb}MB_{uuid.uuid4().hex[:8]}.pdf"
    print(
        f"  [{size_mb} MB] generating {size_mb} MB of random bytes ...",
        file=sys.stderr,
    )
    payload = secrets.token_bytes(size_mb * ONE_MB)

    print(
        f"  [{size_mb} MB] POST /document-files + /structure-items "
        f"(file_name={file_name}) ...",
        file=sys.stderr,
    )
    started = time.monotonic()
    try:
        structure_item = client.attach_file_to_binder(
            binder_guid=binder_guid, file_name=file_name, file_bytes=payload
        )
    except httpx.HTTPStatusError as exc:
        elapsed = time.monotonic() - started
        body_text = exc.response.text[:2000] if exc.response is not None else ""
        record: dict[str, object] = {
            "size_mb": size_mb,
            "file_name": file_name,
            "status": exc.response.status_code if exc.response is not None else None,
            "elapsed_s": round(elapsed, 2),
            "response_body_excerpt": body_text,
            "error_class": type(exc).__name__,
        }
        print(
            f"  [{size_mb} MB] HTTPStatusError "
            f"status={record['status']} elapsed={record['elapsed_s']}s",
            file=sys.stderr,
        )
        return record, False
    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - started
        record = {
            "size_mb": size_mb,
            "file_name": file_name,
            "status": None,
            "elapsed_s": round(elapsed, 2),
            "error_class": type(exc).__name__,
            "error_message": str(exc)[:2000],
        }
        print(
            f"  [{size_mb} MB] {type(exc).__name__}: {exc} "
            f"(elapsed={record['elapsed_s']}s)",
            file=sys.stderr,
        )
        return record, False

    elapsed = time.monotonic() - started
    structure_item_id = structure_item.get("id")
    document_file_id = structure_item.get("document_file_id")
    record = {
        "size_mb": size_mb,
        "file_name": file_name,
        "status": 200,
        "elapsed_s": round(elapsed, 2),
        "document_file_id": document_file_id,
        "structure_item_id": structure_item_id,
    }
    print(
        f"  [{size_mb} MB] OK elapsed={record['elapsed_s']}s "
        f"structure_item_id={structure_item_id}",
        file=sys.stderr,
    )
    return record, True


def main() -> int:
    load_dotenv()
    api_key = os.environ.get("KLARDATEN_API_KEY")
    instance_id = os.environ.get("KLARDATEN_INSTANCE_ID")
    base_url = os.environ.get("KLARDATEN_BASE_URL", "https://api.klardaten.com")
    profile_id = os.environ.get("KLARDATEN_PROFILE_ID") or None
    binder_guid = os.environ.get("SPIKE_VGM_BINDER_GUID", DEFAULT_BINDER_GUID)
    sizes_mb = _parse_sizes(os.environ.get("SPIKE_SIZES_MB"))

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
        timeout=SPIKE_TIMEOUT_S,
    )

    # Guardrail: confirm target is actually a VGM. Otherwise we are
    # uploading 25-200 MB of random bytes into a wrong document.
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

    started_at = datetime.now(timezone.utc)
    runs: list[dict[str, object]] = []
    first_failure: int | None = None
    max_confirmed: int = 0

    print(f"Running size envelope across {sizes_mb} MB ...", file=sys.stderr)
    for size_mb in sizes_mb:
        record, ok = _one_run(client, binder_guid, size_mb)
        runs.append(record)
        if ok:
            max_confirmed = size_mb
            continue
        first_failure = size_mb
        print(
            f"Stopping on first failure at {size_mb} MB; "
            f"max-confirmed = {max_confirmed} MB.",
            file=sys.stderr,
        )
        break

    completed_at = datetime.now(timezone.utc)

    payload_out: dict[str, object] = {
        "vgm_binder_guid": binder_guid,
        "vgm_number": binder.get("number"),
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "runs": runs,
        "first_failure_size_mb": first_failure,
        "max_confirmed_mb": max_confirmed,
    }
    OUTPUT_PATH.write_text(json.dumps(payload_out, indent=2) + "\n", encoding="utf-8")

    print(file=sys.stderr)
    print("=" * 72, file=sys.stderr)
    print(f"Evidence written to: {OUTPUT_PATH}", file=sys.stderr)
    print(f"  max_confirmed_mb     = {max_confirmed}", file=sys.stderr)
    print(f"  first_failure_size_mb = {first_failure!r}", file=sys.stderr)
    print(
        f"Uploaded {len([r for r in runs if r.get('status') == 200])} probe(s) "
        f"into VGM #{binder.get('number')} — cleanup by filename grep "
        f"'_size_probe_*MB_*.pdf' or by structure_item_id in the JSON.",
        file=sys.stderr,
    )
    print("=" * 72, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
