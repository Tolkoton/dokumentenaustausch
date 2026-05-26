"""Spike: multi-file upload to a single DATEV VGM (Vorgangsmappe).

Premise probe for submit-slice (Phase 0, A2 + A3):
  - A2: ``upload_to_binder`` accepts real binary file types (PDF, JPEG)
    at mobile-photo dimensions.
  - A3: Two independent uploads to the SAME binder both succeed and
    produce visible attachments.

Owner runs this script; the script captures wire-level evidence into
``artifacts/spikes/submit-multi-file-upload-2026-05-26.json``. Owner
then logs into DATEV-UO and writes
``artifacts/spikes/submit-sb-discovery-2026-05-26.md`` (spike #2 —
manual, owner-driven, no script).

Spike-only liberty
------------------
This script deliberately calls the KlardatenClient's two-step private
methods (``_upload_file_bytes`` + ``_post_structure_item``) so the
output JSON can record BOTH wire-level ids: the intermediate
``document_file_id`` (consumed once on the structure-items POST) and
the surfaced ``structure_item_id``. Production code MUST go through
``upload_to_binder``; this drop-below-the-seam pattern exists ONLY to
strengthen the evidence record. Do not copy it elsewhere.

Usage
-----
    uv run python scripts/spike_multi_file_upload.py
    SPIKE_VGM_DOKNUM=395357 uv run python scripts/spike_multi_file_upload.py

Required env (loaded from .env via python-dotenv):
    KLARDATEN_API_KEY
    KLARDATEN_INSTANCE_ID

Optional env:
    KLARDATEN_BASE_URL    (default https://api.klardaten.com)
    KLARDATEN_PROFILE_ID
    SPIKE_VGM_DOKNUM      (default 395357)

Fixtures
--------
Fixtures live at ``tests/fixtures/spike_sample.{pdf,jpg}``. If both
already exist they are reused (no regeneration). If either is missing,
the script generates it via Pillow + reportlab. If those deps are not
installed, the script fails fast with an install instruction; owner
may alternatively drop their own files into ``tests/fixtures/`` and
re-run.

Cleanup
-------
NONE. Uploaded docs are left in place so the owner can inspect them in
DATEV-UO for spike #2.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from belegmeister.datev.resolver import resolve_binder_guid_by_number
from belegmeister.klardaten.client import KlardatenClient

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
ARTIFACTS_DIR = REPO_ROOT / "artifacts" / "spikes"
PDF_FIXTURE = FIXTURES_DIR / "spike_sample.pdf"
JPG_FIXTURE = FIXTURES_DIR / "spike_sample.jpg"
OUTPUT_PATH = ARTIFACTS_DIR / "submit-multi-file-upload-2026-05-26.json"

DEFAULT_VGM_DOKNUM = 395357
JPG_DIMENSIONS = (4032, 3024)  # mobile-photo
JPG_QUALITY = 60  # noise compresses poorly; q60 keeps the file roughly mobile-size


def _ensure_fixtures() -> None:
    """Generate fixtures lazily; fail fast with a clear message if deps missing.

    Existing fixtures are NOT regenerated — owner-supplied files take
    precedence over the synthetic ones.
    """
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    need_jpg = not JPG_FIXTURE.exists()
    need_pdf = not PDF_FIXTURE.exists()
    if not need_jpg and not need_pdf:
        return

    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError as exc:
        print(
            "FAIL: missing fixture dependency 'Pillow'.\n"
            "Either install the dev deps:\n"
            "    uv add --dev reportlab Pillow\n"
            "Or drop your own files at:\n"
            f"    {JPG_FIXTURE}\n"
            f"    {PDF_FIXTURE}\n"
            "and re-run.",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc

    if need_jpg:
        # High-entropy RGB noise at mobile-photo dimensions. Random pixel
        # data is intentional: JPEG bytes are what we want, not a pretty
        # picture. q60 yields a file roughly in the mobile-photo size band.
        pixel_count = JPG_DIMENSIONS[0] * JPG_DIMENSIONS[1] * 3
        img = Image.frombytes("RGB", JPG_DIMENSIONS, os.urandom(pixel_count))
        img.save(JPG_FIXTURE, "JPEG", quality=JPG_QUALITY)

    if need_pdf:
        try:
            from reportlab.lib.pagesizes import A4  # noqa: PLC0415
            from reportlab.lib.utils import ImageReader  # noqa: PLC0415
            from reportlab.pdfgen import canvas  # noqa: PLC0415
        except ImportError as exc:
            print(
                "FAIL: missing fixture dependency 'reportlab'.\n"
                "Either install the dev deps:\n"
                "    uv add --dev reportlab Pillow\n"
                "Or drop your own PDF at:\n"
                f"    {PDF_FIXTURE}\n"
                "and re-run.",
                file=sys.stderr,
            )
            raise SystemExit(2) from exc

        # Embed the JPEG as a single A4-sized page. The resulting PDF
        # inherits the JPEG bytes (via DCTDecode), so PDF size ≈ JPEG
        # size + small overhead. Independent file, independent upload.
        c = canvas.Canvas(str(PDF_FIXTURE), pagesize=A4)
        c.drawImage(ImageReader(str(JPG_FIXTURE)), 0, 0, width=A4[0], height=A4[1])
        c.showPage()
        c.save()


def _upload_one(
    client: KlardatenClient,
    binder_guid: str,
    fixture_path: Path,
    iso_stamp: str,
    kind: str,
) -> dict[str, object]:
    """Upload one fixture and record both wire-level ids.

    Calls ``_upload_file_bytes`` then ``_post_structure_item`` directly
    so ``document_file_id`` is observable. Production code uses
    ``upload_to_binder`` — see the module docstring.
    """
    suffix = fixture_path.suffix  # ".pdf" or ".jpg"
    file_name = f"_spike_{kind}_{iso_stamp}{suffix}"
    file_bytes = fixture_path.read_bytes()

    document_file_id = client._upload_file_bytes(file_bytes)  # noqa: SLF001
    structure_item = client._post_structure_item(  # noqa: SLF001
        binder_guid=binder_guid,
        file_name=file_name,
        document_file_id=document_file_id,
    )
    structure_item_id = structure_item.get("id")
    if not isinstance(structure_item_id, str) or not structure_item_id:
        raise SystemExit(
            f"unexpected structure-items response (no usable id): {structure_item!r}"
        )

    return {
        "name": file_name,
        "size_bytes": len(file_bytes),
        "document_file_id": document_file_id,
        "structure_item_id": structure_item_id,
    }


def main() -> int:
    load_dotenv()
    api_key = os.environ.get("KLARDATEN_API_KEY")
    instance_id = os.environ.get("KLARDATEN_INSTANCE_ID")
    base_url = os.environ.get("KLARDATEN_BASE_URL", "https://api.klardaten.com")
    profile_id = os.environ.get("KLARDATEN_PROFILE_ID") or None
    vgm_doknum_raw = os.environ.get("SPIKE_VGM_DOKNUM", str(DEFAULT_VGM_DOKNUM))
    try:
        vgm_doknum = int(vgm_doknum_raw)
    except ValueError:
        print(
            f"FAIL: SPIKE_VGM_DOKNUM must be an integer, got {vgm_doknum_raw!r}",
            file=sys.stderr,
        )
        return 2

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

    _ensure_fixtures()
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    client = KlardatenClient(
        base_url=base_url,
        api_key=api_key,
        instance_id=instance_id,
        profile_id=profile_id,
    )

    print(f"Resolving VGM Dokumentnummer #{vgm_doknum} -> GUID ...")
    binder_guid = resolve_binder_guid_by_number(client, vgm_doknum)
    if binder_guid is None:
        print(
            f"FAIL: VGM #{vgm_doknum} not found within scan window",
            file=sys.stderr,
        )
        return 3
    print(f"  -> {binder_guid}")

    # Mirror upload_to_binder's VGM invariant so this spike cannot
    # pollute a non-VGM document if the doknum points at the wrong thing.
    binder = client.get_document(binder_guid)
    is_binder = binder.get("is_binder")
    extension = binder.get("extension")
    if is_binder is not True or extension != "VGM":
        print(
            f"FAIL: target {binder_guid} is not a Vorgangsmappe "
            f"(is_binder={is_binder!r}, extension={extension!r})",
            file=sys.stderr,
        )
        return 4

    started_at = datetime.now(timezone.utc)
    iso_stamp = started_at.strftime("%Y%m%dT%H%M%SZ")

    print(f"Uploading {PDF_FIXTURE.name} ({PDF_FIXTURE.stat().st_size} bytes) ...")
    pdf_record = _upload_one(client, binder_guid, PDF_FIXTURE, iso_stamp, "pdf")
    print(
        f"  document_file_id={pdf_record['document_file_id']} "
        f"structure_item_id={pdf_record['structure_item_id']}"
    )

    print(f"Uploading {JPG_FIXTURE.name} ({JPG_FIXTURE.stat().st_size} bytes) ...")
    jpg_record = _upload_one(client, binder_guid, JPG_FIXTURE, iso_stamp, "jpg")
    print(
        f"  document_file_id={jpg_record['document_file_id']} "
        f"structure_item_id={jpg_record['structure_item_id']}"
    )

    completed_at = datetime.now(timezone.utc)

    payload: dict[str, object] = {
        "vgm_doknum": vgm_doknum,
        "binder_guid": binder_guid,
        "files": [pdf_record, jpg_record],
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print()
    print("=" * 72)
    print(f"SUCCESS. Evidence written to: {OUTPUT_PATH}")
    print(f"Both files uploaded to VGM #{vgm_doknum} ({binder_guid}).")
    print("Uploaded docs are LEFT IN PLACE for spike #2.")
    print()
    print("Next (owner-driven, no script):")
    print(f"  1. Log into DATEV-UO, navigate to VGM #{vgm_doknum}.")
    print("  2. Confirm both _spike_pdf_*.pdf and _spike_jpg_*.jpg attachments")
    print("     are visible inside the binder.")
    print("  3. Write artifacts/spikes/submit-sb-discovery-2026-05-26.md with:")
    print("       - Both spike-uploaded docs visible in VGM contents: yes/no")
    print("       - Notification received: yes/no")
    print("       - Documents appeared without any push: yes/no")
    print("       - Notes on UX")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
