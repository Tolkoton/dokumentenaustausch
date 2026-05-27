"""Unit tests for `_find_letter_by_id` — pure filter + id-match, no token,
no DATEV, no HTTP. The filter+selection seam called from
`resolve_request_view` after the token is verified.

Migrated from `test_pick_newest_letter.py` (slice token-instance-binding,
UNIT 2): `_pick_newest_letter` is deleted; selection is now by
structure-item `id` match (D1 / D2) rather than newest-by-ISO-name. The
filter half of the contract is unchanged (`type == 1` AND name starts
with `_request_letter_` AND ends with `.txt`), so the filter-edge cases
inherited from the prior suite (mixed children, stray `.md` legacy
letters, completely empty binder) survive verbatim with their assertion
updated for the new failure shape.

`_find_letter_by_id` is private but it is the explicit unit under test
(filter type==1 & `_request_letter_*.txt`, id-match, empty →
RequestLinkInvalid letter_missing, no-id-match → letter_id_not_in_binder).
Testing it directly keeps these deterministic and decoupled from the
flow integration tests in `test_request_view.py`.
"""

from __future__ import annotations

from typing import Any

import pytest

from belegmeister.web.request_view import RequestLinkInvalid
from belegmeister.web.request_view import _find_letter_by_id as find

VGM = "vgm-guid-x"


def _item(
    name: str, *, type_: int = 1, file_id: int = 1, item_id: str | None = None
) -> dict[str, Any]:
    """`item_id` defaults to `str(file_id)` so existing fixtures (which
    pre-date id-match) generate distinct ids per file_id automatically.
    Tests that need a specific id pass it explicitly."""
    return {
        "name": name,
        "type": type_,
        "counter": file_id,
        "document_file_id": file_id,
        "id": item_id if item_id is not None else str(file_id),
    }


def test_FS1_id_match_picks_target_even_when_not_newest_by_name() -> None:
    """Replacement for the prior FS1 (newest-by-ISO-name). Under the new
    contract the selector picks by `id`, not by name — even a lex-earlier
    letter wins as long as its id matches. This is the unit-level
    counterpart to Seam-1 in `test_request_view.py`."""
    children = [
        _item("_request_letter_2026-05-15T080805Z.txt", file_id=1, item_id="ID_A"),
        # newest-by-name but NOT target
        _item("_request_letter_2026-05-15T143022Z.txt", file_id=2, item_id="ID_B"),
        # oldest-by-name, IS target
        _item("_request_letter_2026-05-14T090000Z.txt", file_id=3, item_id="TARGET_ID"),
    ]
    chosen = find(children, letter_id="TARGET_ID", vgm_id=VGM)
    assert chosen["name"] == "_request_letter_2026-05-14T090000Z.txt"
    assert chosen["document_file_id"] == 3


def test_FS2_mixed_children_only_request_letters_considered() -> None:
    """Filter half of the contract (unchanged from FS2 pre-migration):
    non-letter children (folders, stray PDFs) MUST be excluded before
    the id-match runs. A letter_id that happens to match a non-letter
    child's id MUST NOT resolve."""
    children = [
        _item("Neuer Ordner", type_=2, file_id=10, item_id="THE_ID"),
        _item("kunde_antwort_scan.pdf", file_id=11, item_id="THE_ID"),
        _item("_request_letter_2026-05-10T000000Z.txt", file_id=12, item_id="THE_ID"),
        _item("Honorar-Rechnung.PDF", file_id=13, item_id="THE_ID"),
    ]
    chosen = find(children, letter_id="THE_ID", vgm_id=VGM)
    assert chosen["name"] == "_request_letter_2026-05-10T000000Z.txt"
    assert chosen["document_file_id"] == 12


def test_FS3_empty_after_filter_raises_letter_missing() -> None:
    """Filter empties the candidate set → `letter_missing` (binder has
    no letters at all). The token's letter_id is irrelevant in this
    branch — we never reach the id-match."""
    children = [
        _item("Neuer Ordner", type_=2),
        _item("nur_eine_kundendatei.pdf"),
    ]
    with pytest.raises(RequestLinkInvalid) as exc:
        find(children, letter_id="any-id", vgm_id=VGM)
    assert exc.value.log_reason == "letter_missing"
    assert exc.value.log_context.get("vgm_id") == VGM


def test_FS3_completely_empty_list_raises_letter_missing() -> None:
    with pytest.raises(RequestLinkInvalid) as exc:
        find([], letter_id="any-id", vgm_id=VGM)
    assert exc.value.log_reason == "letter_missing"


def test_FS4_single_letter_with_matching_id_returns_it() -> None:
    children = [
        _item("_request_letter_2026-05-15T080805Z.txt", file_id=7, item_id="ONLY_ID")
    ]
    chosen = find(children, letter_id="ONLY_ID", vgm_id=VGM)
    assert chosen["document_file_id"] == 7


def test_FS5_non_txt_with_prefix_is_excluded() -> None:
    """The writer emits exactly `_request_letter_<ISO>.txt`. A stray file
    that shares the prefix but is not `.txt` (an OLD `.md` from a prior
    format, a manual upload, corruption) must NOT be mistaken for the
    letter — filter rejects them, so an otherwise-matching id resolves to
    `letter_missing` (no letters of right shape), NOT
    `letter_id_not_in_binder`.

    (Empirically reinforced: VGM 395357 in the dev environment contains
    3 such `.md` legacy letters from May 15/19, captured in
    `artifacts/spikes/submit-letter-discovery-2026-05-26.md`.)"""
    children = [
        _item("_request_letter_2026-05-15T080805Z.md", file_id=1, item_id="THE_ID"),
        _item("_request_letter_notes", file_id=2, item_id="THE_ID"),
    ]
    with pytest.raises(RequestLinkInvalid) as exc:
        find(children, letter_id="THE_ID", vgm_id=VGM)
    assert exc.value.log_reason == "letter_missing"


def test_FS5_txt_suffix_still_selected_among_non_txt_prefix_siblings() -> None:
    children = [
        _item("_request_letter_2026-05-15T080805Z.md", file_id=1, item_id="MD_ID"),
        _item("_request_letter_2026-05-15T090000Z.txt", file_id=2, item_id="TXT_ID"),
    ]
    chosen = find(children, letter_id="TXT_ID", vgm_id=VGM)
    assert chosen["document_file_id"] == 2


def test_FS6_id_not_in_letters_raises_letter_id_not_in_binder() -> None:
    """NEW failure mode introduced by slice token-instance-binding: the
    binder has letters of the right shape but NONE whose `id` matches
    the token's letter_id. Operationally distinct from `letter_missing`
    (Mandant stale link vs. empty VGM); the log_reason discriminator is
    the slice's D2 observability promise.

    Anti-pattern this catches: copy-paste from the empty-VGM branch
    yields `letter_missing` here too, collapsing the taxonomy. Without
    a dedicated assertion on the new log_reason value, that bug would
    pass any test asserting only `pytest.raises(RequestLinkInvalid)`."""
    children = [
        _item("_request_letter_2026-05-15T080805Z.txt", file_id=1, item_id="ID_X"),
        _item("_request_letter_2026-05-16T080805Z.txt", file_id=2, item_id="ID_Y"),
    ]
    with pytest.raises(RequestLinkInvalid) as exc:
        find(children, letter_id="NOT_PRESENT", vgm_id=VGM)
    assert exc.value.log_reason == "letter_id_not_in_binder"
    assert exc.value.log_context.get("vgm_id") == VGM
