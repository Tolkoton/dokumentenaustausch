"""Tests for the VGM file-naming conventions module — pure, no I/O.

`request_letter_filename` is a pure composition; the round of tests
pins the wire-contract (writer and reader must agree on this exact
shape). Test-code prefix: VF<N>.
"""

from __future__ import annotations

from belegmeister.vgm_files import (
    REQUEST_LETTER_PREFIX,
    REQUEST_LETTER_SUFFIX,
    request_letter_filename,
)


def test_VF1_request_letter_filename_composes_prefix_iso_suffix() -> None:
    assert (
        request_letter_filename("2026-05-19T120000Z")
        == "_request_letter_2026-05-19T120000Z.txt"
    )


def test_VF2_request_letter_filename_is_exactly_prefix_iso_suffix() -> None:
    # Contract: a constant change flows through the helper (no hardcoded
    # duplicate of the affixes inside it).
    iso = "ANYSTAMP"
    assert (
        request_letter_filename(iso)
        == f"{REQUEST_LETTER_PREFIX}{iso}{REQUEST_LETTER_SUFFIX}"
    )


def test_VF3_suffix_is_txt_not_md() -> None:
    # Notepad-openable on stock Windows; the externally-visible contract.
    assert REQUEST_LETTER_SUFFIX == ".txt"
    assert REQUEST_LETTER_PREFIX == "_request_letter_"
