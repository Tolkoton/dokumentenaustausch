"""Unit tests for `_pick_newest_letter` — pure filter+sort, no token,
no DATEV, no HTTP. The fixture cases the seam review asked for.

`_pick_newest_letter` is private but it is the explicit unit under test
(filter type==1 & `_request_letter_*.md`, newest by ISO-in-name; empty →
RequestLinkInvalid letter_missing). Testing it directly keeps these
deterministic and decoupled from the flow.
"""

from __future__ import annotations

from typing import Any

import pytest

from belegmeister.web.request_view import RequestLinkInvalid
from belegmeister.web.request_view import _pick_newest_letter as pick

VGM = "vgm-guid-x"


def _item(name: str, *, type_: int = 1, file_id: int = 1) -> dict[str, Any]:
    return {
        "name": name,
        "type": type_,
        "counter": file_id,
        "document_file_id": file_id,
        "id": str(file_id),
    }


def test_FS1_multiple_letters_picks_newest_by_iso_name() -> None:
    children = [
        _item("_request_letter_2026-05-15T080805Z.md", file_id=1),
        _item("_request_letter_2026-05-15T143022Z.md", file_id=2),
        _item("_request_letter_2026-05-14T090000Z.md", file_id=3),
    ]
    chosen = pick(children, vgm_id=VGM)
    assert chosen["name"] == "_request_letter_2026-05-15T143022Z.md"
    assert chosen["document_file_id"] == 2


def test_FS2_mixed_children_only_request_letters_considered() -> None:
    children = [
        _item("Neuer Ordner", type_=2, file_id=10),  # sub-folder
        _item("kunde_antwort_scan.pdf", file_id=11),  # client response
        _item("_request_letter_2026-05-10T000000Z.md", file_id=12),
        _item("Honorar-Rechnung.PDF", file_id=13),  # unrelated file
    ]
    chosen = pick(children, vgm_id=VGM)
    assert chosen["name"] == "_request_letter_2026-05-10T000000Z.md"


def test_FS3_empty_after_filter_raises_letter_missing() -> None:
    children = [
        _item("Neuer Ordner", type_=2),
        _item("nur_eine_kundendatei.pdf"),
    ]
    with pytest.raises(RequestLinkInvalid) as exc:
        pick(children, vgm_id=VGM)
    assert exc.value.log_reason == "letter_missing"
    assert exc.value.log_context.get("vgm_id") == VGM


def test_FS3_completely_empty_list_raises_letter_missing() -> None:
    with pytest.raises(RequestLinkInvalid) as exc:
        pick([], vgm_id=VGM)
    assert exc.value.log_reason == "letter_missing"


def test_FS4_single_letter_returns_it() -> None:
    children = [_item("_request_letter_2026-05-15T080805Z.md", file_id=7)]
    chosen = pick(children, vgm_id=VGM)
    assert chosen["document_file_id"] == 7


def test_FS5_non_md_with_prefix_is_excluded() -> None:
    """Slice-2 writes exactly `_request_letter_<ISO>.md`. A stray file
    that shares the prefix but is not `.md` (manual upload, corruption,
    a future different artifact) must NOT be mistaken for the letter."""
    children = [
        _item("_request_letter_2026-05-15T080805Z.txt", file_id=1),
        _item("_request_letter_notes", file_id=2),
    ]
    with pytest.raises(RequestLinkInvalid) as exc:
        pick(children, vgm_id=VGM)
    assert exc.value.log_reason == "letter_missing"


def test_FS5_md_suffix_still_selected_among_non_md_prefix_siblings() -> None:
    children = [
        _item("_request_letter_2026-05-15T080805Z.txt", file_id=1),
        _item("_request_letter_2026-05-15T090000Z.md", file_id=2),
    ]
    chosen = pick(children, vgm_id=VGM)
    assert chosen["document_file_id"] == 2
