"""Flow tests for `resolve_request_view` with an in-memory fake
LetterSource (the KlardatenClient subset this needs).

The fake serves a structure-items list and file bytes; tests assert the
resolved RequestView or the generic RequestLinkInvalid + its log_reason
(never leaked to the client, but checked here for the logging contract).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from belegmeister.magic_link.token import generate_token
from belegmeister.request_format import RequestLetter, serialize_request_letter
from belegmeister.web.request_view import (
    RequestLinkInvalid,
    RequestView,
    resolve_request_view,
)

SECRET = "w" * 48
NOW = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)
VGM = "3bf17a53-42ca-4a03-9275-213bd1c6b263"
# Default fixture letter's structure-item `id`; mirrored in `_token`'s default
# so RV1 happy-path remains green under id-match selection. Slice
# token-instance-binding D1: the token's `letter_id` IS the structure-item id.
LETTER_ID = "1170198"

# Wire-format `request/v1` payload. After the Step 0 refactor,
# `resolve_request_view` parses what `download_document_file` returns,
# so the fixture must be a serializable letter rather than plain text.
_LETTER_BODY = "Sehr geehrte Damen und Herren, bitte Belege 2026."
_LETTER_OBJ = RequestLetter(
    to="client@example.com",
    cc="",
    subject="Belege 2026",
    body=_LETTER_BODY,
    questions=(),
)
_LETTER_BYTES = serialize_request_letter(_LETTER_OBJ).encode("utf-8")


class _FakeLetterSource:
    def __init__(
        self,
        *,
        children: list[dict[str, Any]] | None = None,
        files: dict[int, bytes] | None = None,
        list_error: Exception | None = None,
        download_error: Exception | None = None,
    ) -> None:
        self._children = (
            children
            if children is not None
            else [
                {
                    "name": "_request_letter_2026-05-15T080805Z.txt",
                    "counter": 2,
                    "type": 1,
                    "parent_counter": 0,
                    "document_file_id": 1152156,
                    "size": len(_LETTER_BYTES),
                    "id": LETTER_ID,
                }
            ]
        )
        self._files = files if files is not None else {1152156: _LETTER_BYTES}
        self._list_error = list_error
        self._download_error = download_error
        self.list_calls: list[str] = []
        self.download_calls: list[int] = []

    def list_structure_items(self, binder_guid: str) -> list[dict[str, Any]]:
        self.list_calls.append(binder_guid)
        if self._list_error is not None:
            raise self._list_error
        return self._children

    def download_document_file(self, document_file_id: int) -> bytes:
        self.download_calls.append(document_file_id)
        if self._download_error is not None:
            raise self._download_error
        return self._files[document_file_id]

    def attach_file_to_binder(
        self, *, binder_guid: str, file_name: str, file_bytes: bytes
    ) -> dict[str, Any]:
        # GET-side tests never write. Raise so a refactor that
        # accidentally invokes the write path from a GET test surfaces
        # loudly.
        raise AssertionError(
            "attach_file_to_binder unexpected on GET-side LetterSource fake"
        )


def _token(
    *,
    vgm: str = VGM,
    letter_id: str = LETTER_ID,
    exp_delta: timedelta = timedelta(days=3),
) -> str:
    return generate_token(
        vgm_id=vgm,
        letter_id=letter_id,
        expires_at=NOW + exp_delta,
        secret=SECRET,
    )


def test_RV1_valid_token_single_letter_returns_request_view() -> None:
    src = _FakeLetterSource()

    view = resolve_request_view(_token(), letter_source=src, secret=SECRET, now=NOW)

    assert isinstance(view, RequestView)
    assert view.vgm_id == VGM
    assert view.letter_filename == "_request_letter_2026-05-15T080805Z.txt"
    assert view.letter == _LETTER_OBJ
    assert view.letter.body == _LETTER_BODY
    assert src.list_calls == [VGM]
    assert src.download_calls == [1152156]


def test_RV2_bad_signature_raises_token_bad_signature() -> None:
    """Forged signature → distinct log_reason. A spike of these in the
    server log is a tamper signal (someone forging tokens). Client still
    sees a generic 404 — no disclosure."""
    src = _FakeLetterSource()
    forged = generate_token(
        vgm_id=VGM,
        letter_id="any-test-letter-id",
        expires_at=NOW + timedelta(days=3),
        secret="DIFFERENT" * 6,
    )

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(forged, letter_source=src, secret=SECRET, now=NOW)

    assert exc.value.log_reason == "token_bad_signature"
    assert src.list_calls == [], "must not touch DATEV on a bad token"


def test_RV2_malformed_token_raises_token_malformed() -> None:
    """Structurally broken token → distinct log_reason. A spike of these
    is a benign signal (email truncation / copy-paste), not an attack."""
    src = _FakeLetterSource()

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(
            "not-a-valid-token", letter_source=src, secret=SECRET, now=NOW
        )

    assert exc.value.log_reason == "token_malformed"
    assert src.list_calls == []


def test_RV3_expired_token_raises_token_expired() -> None:
    """Real token, real verify_token, expiry in the past. Pins the
    cross-module contract that an expired token maps to token_expired.
    Coupling is now typed (InvalidTokenReason.EXPIRED identity), not a
    string-match — a wording change can no longer silently degrade it."""
    src = _FakeLetterSource()
    expired = generate_token(
        vgm_id=VGM,
        letter_id="any-test-letter-id",
        expires_at=NOW - timedelta(seconds=1),
        secret=SECRET,
    )

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(expired, letter_source=src, secret=SECRET, now=NOW)

    assert exc.value.log_reason == "token_expired"
    assert src.list_calls == []


def _http_status_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://api.klardaten.com/x")
    resp = httpx.Response(code, request=req)
    return httpx.HTTPStatusError(f"HTTP {code}", request=req, response=resp)


def test_RV4_listing_404_raises_vgm_not_found() -> None:
    src = _FakeLetterSource(list_error=_http_status_error(404))

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(_token(), letter_source=src, secret=SECRET, now=NOW)

    assert exc.value.log_reason == "vgm_not_found"
    assert exc.value.log_context.get("vgm_id") == VGM
    assert src.list_calls == [VGM]  # dispatched with the token's vgm_id


def test_RV4_listing_503_raises_datev_error_not_vgm_not_found() -> None:
    """A DATEV outage must NOT be logged as 'SB typed a bad id'. Different
    operational response (page on-call vs. tell the SB)."""
    src = _FakeLetterSource(list_error=_http_status_error(503))

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(_token(), letter_source=src, secret=SECRET, now=NOW)

    assert exc.value.log_reason == "datev_error"
    assert exc.value.log_context.get("status") == 503


def test_RV4_listing_timeout_raises_datev_error() -> None:
    src = _FakeLetterSource(list_error=httpx.ConnectTimeout("timed out"))

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(_token(), letter_source=src, secret=SECRET, now=NOW)

    assert exc.value.log_reason == "datev_error"


def test_RV5a_download_http_error_raises_download_failed() -> None:
    src = _FakeLetterSource(download_error=_http_status_error(503))

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(_token(), letter_source=src, secret=SECRET, now=NOW)

    assert exc.value.log_reason == "download_failed"
    assert exc.value.log_context.get("vgm_id") == VGM


def test_RV5a_download_timeout_raises_download_failed() -> None:
    src = _FakeLetterSource(download_error=httpx.ReadTimeout("slow"))

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(_token(), letter_source=src, secret=SECRET, now=NOW)

    assert exc.value.log_reason == "download_failed"


def test_RV5a_non_httpx_download_error_propagates_as_bug() -> None:
    """A non-httpx exception from the client is a bug, not a download
    failure — it must propagate with its traceback, not be laundered
    into a generic RequestLinkInvalid."""
    src = _FakeLetterSource(download_error=RuntimeError("client bug"))

    with pytest.raises(RuntimeError, match="client bug"):
        resolve_request_view(_token(), letter_source=src, secret=SECRET, now=NOW)


def test_RV5b_non_utf8_letter_raises_letter_not_utf8() -> None:
    """Letter bytes manually replaced / corrupted to invalid UTF-8 in
    DATEV → content signal, distinct from a transport failure."""
    bad = b"\xff\xfe\x00\x01 not utf-8"
    src = _FakeLetterSource(files={1152156: bad})

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(_token(), letter_source=src, secret=SECRET, now=NOW)

    assert exc.value.log_reason == "letter_not_utf8"
    assert exc.value.log_context.get("vgm_id") == VGM


# --- Seam 1: `_find_letter_by_id` wide test ---------------------------------
#
# Defeats every naive heuristic implied by the four identifier candidates the
# `letter-discovery` spike surfaced (id / document_file_id / counter /
# creation_date) plus list-position picks (`children[0/1/-1]`) plus name lex
# extremes. Target letter satisfies NONE of these extreme positions:
#
#   axis              | min        | T (target) | max
#   ------------------|------------|------------|------------
#   index in list     | 0          | 2          | 4 (last)
#   name (lex order)  | letter[0]  | letter[2]  | letter[4]
#   creation_date     | 2026-05-15 | 2026-05-21 | 2026-05-25
#   document_file_id  | 8000 (D)   | 10000 (T)  | 15000 (B)
#   counter           | 2 (B)      | 3 (T)      | 7 (D)
#
# Any naive pick keyed on these axes returns a non-target letter.
# Only `id == TARGET_LETTER_ID` returns T.

_TARGET_LETTER_ID = "TARGET_LETTER_ID_42"
_TARGET_LETTER_NAME = "_request_letter_2026-05-21T080000Z.txt"
_TARGET_DOC_FILE_ID = 10000


def _multi_letter_fixture() -> tuple[list[dict[str, Any]], dict[int, bytes]]:
    """Five `_request_letter_*.txt` structure-items in a single binder,
    crafted so the target (T) is the unique middle element on EVERY
    identifier axis the implementer might naively key on.

    List order intentionally != name-lex / date / counter / file_id
    order — so `children[0]` is not the lex-smallest, etc. T sits at
    index 2 but is not extreme on any axis.
    """
    target_letter_bytes = serialize_request_letter(
        RequestLetter(
            to="t@example.com",
            cc="",
            subject="Belege Q2 (TARGET)",
            body="This is THE letter T the token must resolve to.",
            questions=(),
        )
    ).encode("utf-8")
    # Letter A (lex-smallest, oldest creation_date)
    a_bytes = b"_unused_a_"  # never downloaded if id-match works
    b_bytes = b"_unused_b_"
    d_bytes = b"_unused_d_"
    e_bytes = b"_unused_e_"

    children: list[dict[str, Any]] = [
        # index 0 — name lex-smallest, oldest, NOT-extreme doc_file_id,
        # NOT-extreme counter. Defeats `children[0]`, lex-min, oldest.
        {
            "name": "_request_letter_2026-05-15T080000Z.txt",
            "counter": 4,
            "type": 1,
            "parent_counter": 0,
            "document_file_id": 12000,
            "creation_date": "2026-05-15T08:00:00.000",
            "size": len(a_bytes),
            "id": "ID_A",
        },
        # index 1 — name second-smallest, second-oldest, HIGHEST doc_file_id,
        # LOWEST counter. Defeats `children[1]`, doc_file_id-max,
        # counter-min.
        {
            "name": "_request_letter_2026-05-19T080000Z.txt",
            "counter": 2,
            "type": 1,
            "parent_counter": 0,
            "document_file_id": 15000,
            "creation_date": "2026-05-19T08:00:00.000",
            "size": len(b_bytes),
            "id": "ID_B",
        },
        # index 2 — TARGET. Middle on EVERY axis.
        {
            "name": _TARGET_LETTER_NAME,
            "counter": 3,
            "type": 1,
            "parent_counter": 0,
            "document_file_id": _TARGET_DOC_FILE_ID,
            "creation_date": "2026-05-21T08:00:00.000",
            "size": len(target_letter_bytes),
            "id": _TARGET_LETTER_ID,
        },
        # index 3 — LOWEST doc_file_id, HIGHEST counter. Defeats
        # doc_file_id-min, counter-max.
        {
            "name": "_request_letter_2026-05-23T080000Z.txt",
            "counter": 7,
            "type": 1,
            "parent_counter": 0,
            "document_file_id": 8000,
            "creation_date": "2026-05-23T08:00:00.000",
            "size": len(d_bytes),
            "id": "ID_D",
        },
        # index 4 (LAST) — name lex-largest, newest, NOT-extreme
        # doc_file_id, NOT-extreme counter. Defeats `children[-1]`,
        # lex-max, newest.
        {
            "name": "_request_letter_2026-05-25T080000Z.txt",
            "counter": 5,
            "type": 1,
            "parent_counter": 0,
            "document_file_id": 9000,
            "creation_date": "2026-05-25T08:00:00.000",
            "size": len(e_bytes),
            "id": "ID_E",
        },
    ]
    files: dict[int, bytes] = {
        12000: a_bytes,
        15000: b_bytes,
        _TARGET_DOC_FILE_ID: target_letter_bytes,
        8000: d_bytes,
        9000: e_bytes,
    }
    return children, files


def test_find_letter_by_id_selects_target_in_multi_letter_binder() -> None:
    """Seam-1 wide test (slice token-instance-binding).

    Resolver MUST pick the letter whose `id` equals the token's `letter_id`,
    NOT some heuristic over `(name, creation_date, document_file_id,
    counter, list-position)`. The fixture above is designed so the target
    is the unique middle element on every identifier axis — any naive
    implementation keyed on one of those axes picks a non-target letter
    and this test fails with a mismatched filename / download id.

    Anti-pattern named: 'one letter in the list = false confidence' —
    the resolver-perf precedent (`return children[0]` would also satisfy
    a single-letter fixture). This test prevents that by forcing a
    discriminator on five letters across five orthogonal axes.
    """
    children, files = _multi_letter_fixture()
    src = _FakeLetterSource(children=children, files=files)

    token = _token(letter_id=_TARGET_LETTER_ID)
    view = resolve_request_view(token, letter_source=src, secret=SECRET, now=NOW)

    assert isinstance(view, RequestView)
    assert view.vgm_id == VGM
    assert view.letter_filename == _TARGET_LETTER_NAME, (
        f"resolver picked wrong letter — expected {_TARGET_LETTER_NAME!r}, "
        f"got {view.letter_filename!r}. Slice contract Seam-1: id-match "
        "selection, not a heuristic."
    )
    assert view.letter.subject == "Belege Q2 (TARGET)"
    # The download MUST go to the target's document_file_id, not any other
    # — catches the case where the right letter record was identified but
    # the wrong file was downloaded (e.g. if find-by-id returned the right
    # dict but the download step indexed by a stale variable).
    assert src.download_calls == [_TARGET_DOC_FILE_ID]


# --- Seam 5: log_reason distinguishability ---------------------------------
#
# The slice's primary D2 rationale (observability) only pays off if the
# implementation distinguishes the three error paths in `log_reason`:
#   - letter_id_not_in_binder : binder has letters, but none match the
#                               token's letter_id (NEW this slice).
#   - letter_missing          : binder has no letters at all (existing).
#   - vgm_not_found           : binder GET returned 404 (existing,
#                               regression-guarded by test_RV4_listing_404
#                               above; not duplicated here).
#
# Naive failure mode: copy-paste from the empty-VGM branch yields
# `raise RequestLinkInvalid(log_reason="letter_missing")` when the real
# condition is `letter_id_not_in_binder`. A test asserting only
# `pytest.raises(RequestLinkInvalid)` PASSES — same exception class. The
# discriminator is the `log_reason` field.


def test_letter_id_not_in_binder_emits_distinct_log_reason() -> None:
    """Seam-5 (new log_reason). Populated VGM whose letters do NOT
    include the token's `letter_id` → distinct `letter_id_not_in_binder`
    log_reason. MUST NOT collapse into `letter_missing` (which means
    'no letters at all')."""
    children, files = _multi_letter_fixture()
    src = _FakeLetterSource(children=children, files=files)

    # Token references a letter_id that is NOT among the binder's letters.
    token = _token(letter_id="LETTER_ID_NOT_IN_BINDER")

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(token, letter_source=src, secret=SECRET, now=NOW)

    assert exc.value.log_reason == "letter_id_not_in_binder", (
        "the slice's primary observability promise (D2): this case MUST be "
        f"distinguishable from `letter_missing`. Got {exc.value.log_reason!r}."
    )
    assert exc.value.log_context.get("vgm_id") == VGM
    # download must NOT have been attempted — we failed before reaching it.
    assert src.download_calls == []


def test_empty_binder_still_emits_letter_missing() -> None:
    """Seam-5 regression guard. An empty VGM (no letters at all) MUST
    keep emitting `letter_missing`, not get re-routed into the new
    `letter_id_not_in_binder` reason. The two cases are operationally
    distinct: empty VGM is a 'where is my letter?' SB-side problem;
    letter_id_not_in_binder is a 'this specific letter is gone or never
    existed' Mandant-stale-link problem."""
    src = _FakeLetterSource(children=[])

    with pytest.raises(RequestLinkInvalid) as exc:
        resolve_request_view(_token(), letter_source=src, secret=SECRET, now=NOW)

    assert exc.value.log_reason == "letter_missing"
    assert exc.value.log_context.get("vgm_id") == VGM
    assert src.download_calls == []
