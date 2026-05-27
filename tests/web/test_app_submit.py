"""Regular-difficulty tests for the POST /r/{token}/submit handler —
slice submit-handler UNIT 2. Covers slice exit criterion items #5
(replay check), #6 (banner-state derivation), and #7 (D7 empty-submit
predicate). The Hardest-Seam S1 four-branch matrix lives in the
sibling file `test_app_submit_branching.py`.

Tests target the pure functions (`dispatch_submit_outcome`,
`is_empty_submit`) and the replay-check helper directly — they do NOT
go through the HTTP layer. The HTTP-layer integration assertions are
the S1 matrix's job.
"""

from __future__ import annotations

import pytest

from belegmeister.web.app import (
    BannerState,
    SubmitDispatch,
    _is_already_submitted,
    dispatch_submit_outcome,
    is_empty_submit,
)
from belegmeister.web.response_format import AttachmentOutcome

# --- D7 server-side predicate (tightened 2026-05-27) ---
#
# Revised semantic (pre-existing UX defect fix, NOT a slice contract
# revision): ALL request-letter question answers must be non-empty
# (after .strip()); files and Anmerkungen are OPTIONAL supplements
# that do NOT affect the predicate.
#
# Was: "≥1 of {files, answers, anmerkungen} non-empty" — allowed
# "answer with Anmerkungen only, no answers to actual questions"
# which is product-wrong for Beleganforderung.


def test_empty_submit_predicate_rejects_all_empty() -> None:
    """Zero questions answered → True (any missing answer = empty).

    Whitespace-only counts as empty so the new HTML5 ``required``
    attribute is structurally indistinguishable on the server side
    (a Mandant pasting ``"   "`` into an input must be rejected the
    same way an empty input is).
    """
    # Multi-question fixture, all empty.
    assert is_empty_submit(answers=["", ""], anmerkungen="", file_count=0) is True
    # Whitespace-only variants of empty.
    assert (
        is_empty_submit(answers=["   ", "\t\n"], anmerkungen="", file_count=0) is True
    )


def test_predicate_accepts_when_all_answers_filled_no_files_no_anmerkungen() -> None:
    """All answers filled, no files, no anmerkungen → accept.

    Was: ``test_empty_submit_predicate_accepts_answers_only`` —
    semantic shift: now requires ALL answers, not just AT LEAST ONE.
    Fixture has two questions both answered.
    """
    assert (
        is_empty_submit(
            answers=["Sparkasse.", "Ja, vollständig."],
            anmerkungen="",
            file_count=0,
        )
        is False
    )


def test_predicate_rejects_files_only_when_answers_empty() -> None:
    """Files attached but answers empty → REJECT under the new
    semantic. Files are an optional supplement, not a substitute for
    answering the SB's questions.

    Was: ``test_empty_submit_predicate_accepts_files_only`` — used to
    PASS (files-only ⇒ accept). Now REJECTS to enforce the new
    "answer the questions first" product rule.
    """
    assert is_empty_submit(answers=["", ""], anmerkungen="", file_count=2) is True


def test_predicate_rejects_anmerkungen_only_when_answers_empty() -> None:
    """Anmerkungen filled but answers empty → REJECT under the new
    semantic. Same rationale as files-only: comment is an optional
    supplement.

    Was: ``test_empty_submit_predicate_accepts_anmerkungen_only`` —
    used to PASS. Now REJECTS — this is the realistic edge-case the
    pre-existing defect allowed ("Mandant only typed a comment").
    """
    assert (
        is_empty_submit(
            answers=["", ""],
            anmerkungen="Sorry, ich finde die Belege nicht.",
            file_count=0,
        )
        is True
    )


def test_predicate_rejects_when_any_single_answer_empty() -> None:
    """Multi-question fixture where N-1 answers are filled and 1 is
    empty → REJECT. Catches the "almost done but one question
    skipped" case the new strict-all-required semantic exists for.
    """
    assert (
        is_empty_submit(
            answers=["Sparkasse.", "", "2026-03-15"],
            anmerkungen="",
            file_count=0,
        )
        is True
    )
    # Whitespace-only in the skipped slot also rejects (strip semantic).
    assert (
        is_empty_submit(
            answers=["Sparkasse.", "   ", "2026-03-15"],
            anmerkungen="",
            file_count=0,
        )
        is True
    )


def test_predicate_accepts_all_answers_with_optional_files() -> None:
    """All answers filled + files attached → accept. Files are an
    allowed supplement; their presence does NOT alter the accept."""
    assert (
        is_empty_submit(
            answers=["Sparkasse.", "Ja."],
            anmerkungen="",
            file_count=3,
        )
        is False
    )


def test_predicate_accepts_all_answers_with_optional_anmerkungen() -> None:
    """All answers filled + Anmerkungen → accept. Anmerkungen is an
    allowed supplement; its presence does NOT alter the accept."""
    assert (
        is_empty_submit(
            answers=["Sparkasse.", "Ja."],
            anmerkungen="Bitte um schnelle Bearbeitung.",
            file_count=0,
        )
        is False
    )


def test_predicate_accepts_all_answers_alone() -> None:
    """All answers filled, no files, no anmerkungen → accept. The
    minimal valid submission for a request letter with questions."""
    assert (
        is_empty_submit(answers=["Sparkasse."], anmerkungen="", file_count=0) is False
    )


def test_predicate_vacuously_accepts_zero_questions() -> None:
    """Zero questions in the request letter (``answers == []``) →
    accept (vacuous: ``all(non-empty for _ in [])`` is True). The SB
    intentionally created a letter without questions; the predicate
    imposes no answer requirement in that case.

    Pre-existing test_app_submit_inventory.py S6 fixture relies on
    this — it uses ``questions=()`` and submits 2 files without any
    answer fields; the predicate must accept that shape so the
    upload flow runs.
    """
    assert is_empty_submit(answers=[], anmerkungen="", file_count=0) is False
    assert is_empty_submit(answers=[], anmerkungen="", file_count=2) is False


# --- D2 in-binder replay check ---


class _FakeBinder:
    """Minimal LetterSource fake that returns a fixed structure-items
    list. Only `list_structure_items` is exercised by the replay
    check; `download_document_file` raises if called (catches stray
    invocations)."""

    def __init__(self, *, items: list[dict[str, object]]) -> None:
        self._items = items

    def list_structure_items(self, binder_guid: str) -> list[dict[str, object]]:
        return self._items

    def download_document_file(self, document_file_id: int) -> bytes:
        raise AssertionError(
            "download_document_file should not be called from replay check"
        )

    def attach_file_to_binder(
        self, *, binder_guid: str, file_name: str, file_bytes: bytes
    ) -> dict[str, object]:
        raise AssertionError(
            "attach_file_to_binder should not be called from replay check"
        )


def test_replay_check_fires_when_response_doc_present() -> None:
    """A structure-item whose name starts with ``_response_<letter_id>_``
    means the Mandant already submitted — replay check returns True."""
    items = [
        {"id": "1170198", "name": "_request_letter_2026-05-15T080805Z.txt", "type": 1},
        {"id": "1186600", "name": "_response_1170198_20260527T103000Z.txt", "type": 1},
    ]
    src = _FakeBinder(items=items)
    assert _is_already_submitted(src, vgm_id="vgm-x", letter_id="1170198") is True


def test_replay_check_passes_when_response_doc_absent() -> None:
    """Binder with only the request letter (no response doc with this
    letter_id) → False (Mandant may submit)."""
    items = [
        {"id": "1170198", "name": "_request_letter_2026-05-15T080805Z.txt", "type": 1},
    ]
    src = _FakeBinder(items=items)
    assert _is_already_submitted(src, vgm_id="vgm-x", letter_id="1170198") is False


def test_replay_check_distinguishes_letter_id() -> None:
    """A response doc for a DIFFERENT letter_id in the same VGM must
    NOT trip the check — the burn marker is per-letter, not per-VGM
    (per ADR-0006). Two requests in the same VGM remain
    independently burnable."""
    items = [
        {
            "id": "9999999",
            "name": "_response_OTHER_LETTER_20260527T100000Z.txt",
            "type": 1,
        },
    ]
    src = _FakeBinder(items=items)
    assert _is_already_submitted(src, vgm_id="vgm-x", letter_id="1170198") is False


# --- Banner-state derivation (D5 + D6 dispatcher output) ---


def _succeeded(name: str) -> AttachmentOutcome:
    return AttachmentOutcome(
        original_filename=name,
        stored_filename=f"_attachment_X_aaaaaaaa_{name}",
        structure_item_id="1186600",
        document_file_id=1166000,
        status="succeeded",
        failure_reason=None,
        elapsed_s=1.0,
    )


def _failed(name: str) -> AttachmentOutcome:
    return AttachmentOutcome(
        original_filename=name,
        stored_filename=None,
        structure_item_id=None,
        document_file_id=None,
        status="failed",
        failure_reason="klardaten_5xx",
        elapsed_s=0.4,
    )


@pytest.mark.parametrize(
    ("inventory", "expected_commit", "expected_banner", "expected_bailout"),
    [
        # Branch 1: answers-only (empty inventory) → commit + full_success.
        ((), True, "full_success", None),
        # Branch 2: all-files-failed bailout.
        ((_failed("a.pdf"),), False, None, "upload_failed_all_files"),
        ((_failed("a.pdf"), _failed("b.pdf")), False, None, "upload_failed_all_files"),
        # Branch 3: partial success.
        ((_succeeded("ok.pdf"), _failed("bad.pdf")), True, "partial_success", None),
        # Branch 4: full success.
        ((_succeeded("a.pdf"),), True, "full_success", None),
        ((_succeeded("a.pdf"), _succeeded("b.pdf")), True, "full_success", None),
    ],
)
def test_banner_state_from_outcome(
    inventory: tuple[AttachmentOutcome, ...],
    expected_commit: bool,
    expected_banner: BannerState | None,
    expected_bailout: str | None,
) -> None:
    """Pure dispatcher: maps inventory shape to commit/banner/bailout.
    Parametrized over all four D6 branches; covers the answers-only
    case where files_attempted == 0 = files_succeeded (which must
    route to branch 1, not branch 2 — branch ordering matters)."""
    result = dispatch_submit_outcome(inventory)
    assert isinstance(result, SubmitDispatch)
    assert result.commit_response_doc is expected_commit
    assert result.banner_state == expected_banner
    assert result.bailout_log_reason == expected_bailout
