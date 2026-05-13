"""Import / contract sanity. Real validation lives in
`scripts/smoke_test_datev_upload.py` against a real DATEV instance.

Mock-based behavioral tests will be added once the slice grows logic worth
mocking (retries, error-mapping branches, response normalization).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from belegmeister.datev.resolver import resolve_binder_guid_by_number
from belegmeister.datev.upload import (
    InvalidUploadTarget,
    UploadResult,
    upload_to_binder,
)
from belegmeister.klardaten.client import KlardatenClient


def test_module_imports_and_types_are_exported() -> None:
    assert callable(upload_to_binder)
    assert callable(resolve_binder_guid_by_number)
    assert issubclass(InvalidUploadTarget, Exception)
    assert UploadResult.__dataclass_fields__.keys() >= {
        "success",
        "document_id",
        "error",
    }
    assert KlardatenClient.__dataclass_fields__.keys() >= {
        "base_url",
        "api_key",
        "instance_id",
    }


def test_validate_inputs_rejects_missing_file() -> None:
    class _NeverCalled:
        def get_document(self, _guid: str) -> dict[str, Any]:
            raise AssertionError("client must not be invoked on validation failure")

        def attach_file_to_binder(self, **_: object) -> dict[str, Any]:
            raise AssertionError("client must not be invoked on validation failure")

    result = upload_to_binder(
        Path("/nonexistent/does/not/exist.pdf"),
        "11111111-1111-1111-1111-111111111111",
        _NeverCalled(),
    )
    assert result.success is False
    assert result.document_id is None
    assert result.error is not None
    assert "not found" in result.error.lower()


def test_invalid_upload_target_message_carries_id_and_reason() -> None:
    err = InvalidUploadTarget(
        "abc-123", "not a Vorgangsmappe (is_binder=False, extension='PDF')"
    )
    assert err.binder_guid == "abc-123"
    assert "abc-123" in str(err)
    assert "Vorgangsmappe" in str(err)
    assert err.reason.startswith("not a Vorgangsmappe")
