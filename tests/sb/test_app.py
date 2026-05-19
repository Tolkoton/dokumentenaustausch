"""TestClient behavior tests for the LOCAL SB request-creation app.

Same hermetic pattern as the Slice-3 web tests: deps
(klardaten client / secret / base url / now) are FastAPI dependencies
overridden here so no env / real DATEV is touched. `TestClient(app)`
is NOT used as a context manager for route tests, so the lifespan
(env fail-fast) does not run — that is covered separately (B11).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from belegmeister.magic_link.token import verify_token
from belegmeister.request_format import parse_request_letter
from belegmeister.sb.app import (
    app,
    get_base_url,
    get_klardaten_client,
    get_now,
    get_secret,
)

SECRET = "s" * 48
BASE_URL = "https://app.example.com"
NOW = datetime(2026, 5, 19, 12, 0, 0, tzinfo=timezone.utc)
VGM_NUMBER = 395357
VGM_GUID = "3bf17a53-42ca-4a03-9275-213bd1c6b263"


class _FakeClient:
    """Satisfies BOTH the resolver (`list_documents`) and the real
    `upload_to_binder` core (`get_document` -> a valid Vorgangsmappe,
    `attach_file_to_binder` -> a structure-item with an id). Records the
    attach call so a test can prove the number->GUID->core wiring."""

    def __init__(
        self,
        *,
        docs: list[dict[str, Any]] | None = None,
        list_raises: Exception | None = None,
        binder_doc: dict[str, Any] | None = None,
        attach_returns: dict[str, Any] | None = None,
    ) -> None:
        self._docs = (
            docs if docs is not None else [{"number": VGM_NUMBER, "id": VGM_GUID}]
        )
        self._list_raises = list_raises
        # default = a valid Vorgangsmappe; override with a non-VGM doc to
        # drive the real upload_to_binder into InvalidUploadTarget
        self._binder_doc = binder_doc
        # default = a structure-item with an id (success); override with
        # an id-less dict to drive upload_to_binder into success=False
        self._attach_returns = (
            attach_returns if attach_returns is not None else {"id": "struct-9001"}
        )
        self.attached: dict[str, Any] | None = None
        self.list_documents_called = False
        self.get_document_called = False

    def list_documents(self, *, top: int = 1000, skip: int = 0) -> list[dict[str, Any]]:
        self.list_documents_called = True
        if self._list_raises is not None:
            raise self._list_raises
        return self._docs if skip == 0 else []

    def get_document(self, guid: str) -> dict[str, Any]:
        self.get_document_called = True
        if self._binder_doc is not None:
            return self._binder_doc
        return {"is_binder": True, "extension": "VGM", "id": guid}

    def attach_file_to_binder(
        self, *, binder_guid: str, file_name: str, file_bytes: bytes
    ) -> dict[str, Any]:
        self.attached = {
            "binder_guid": binder_guid,
            "file_name": file_name,
            "file_bytes": file_bytes,
        }
        return self._attach_returns


def _client(fake: _FakeClient) -> TestClient:
    app.dependency_overrides[get_klardaten_client] = lambda: fake
    app.dependency_overrides[get_secret] = lambda: SECRET
    app.dependency_overrides[get_base_url] = lambda: BASE_URL
    app.dependency_overrides[get_now] = lambda: NOW
    return TestClient(app, raise_server_exceptions=True)


def _extract_token(body: str, base_url: str) -> str:
    """Pull the magic-link token out of the rendered result page."""
    prefix = f"{base_url}/r/"
    assert prefix in body
    return body.split(prefix, 1)[1].split('"')[0].split("<")[0].strip()


@pytest.fixture(autouse=True)
def _clear_overrides() -> object:
    yield
    app.dependency_overrides.clear()


def test_B1_get_sb_renders_empty_creation_form() -> None:
    client = TestClient(app, raise_server_exceptions=True)

    r = client.get("/sb")

    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    # posts to the create endpoint
    assert 'action="/sb/create"' in body
    assert 'method="POST"' in body or 'method="post"' in body
    # the scalar fields the SB fills in
    assert 'name="vgm_number"' in body
    assert 'name="to"' in body
    assert 'name="cc"' in body
    assert 'name="subject"' in body
    assert 'name="body"' in body  # textarea
    # dynamic questions: a repeated field + an add control
    assert 'name="questions"' in body
    assert "Frage hinzufügen" in body
    # empty form: no error banner, scalar inputs carry no value
    assert 'value=""' in body or "value=" not in body.split("<textarea")[0]


def test_B2_valid_post_resolves_creates_and_shows_copyable_link() -> None:
    fake = _FakeClient()
    client = _client(fake)

    r = client.post(
        "/sb/create",
        data={
            "vgm_number": str(VGM_NUMBER),
            "to": "mandant@example.com",
            "cc": "kanzlei@example.com",
            "subject": "Unterlagen 2026",
            "body": "Sehr geehrte Frau Müller,\n\nbitte Belege.",
            "questions": ["Fahrtkosten 2026?", "Arbeitszimmer genutzt?"],
        },
    )

    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text

    # number -> GUID -> core wiring: the real upload_to_binder was driven
    # with the RESOLVED guid (not the entered number)
    assert fake.attached is not None
    assert fake.attached["binder_guid"] == VGM_GUID
    letter = fake.attached["file_bytes"].decode("utf-8")
    assert "Unterlagen 2026" in letter
    assert "Fahrtkosten 2026?" in letter
    assert "Arbeitszimmer genutzt?" in letter

    # result page (NOT the form) showing a valid, copyable magic link
    assert 'action="/sb/create"' not in body
    payload = verify_token(token=_extract_token(body, BASE_URL), secret=SECRET, now=NOW)
    assert payload.vgm_id == VGM_GUID


def test_B4_multiple_questions_reach_core_in_submitted_order() -> None:
    fake = _FakeClient()
    client = _client(fake)

    # deliberately NON-sorted so an accidental sort/set would be caught;
    # all non-blank (blank handling is _clean_questions' job, not B4's)
    r = client.post(
        "/sb/create",
        data={
            "vgm_number": str(VGM_NUMBER),
            "to": "mandant@example.com",
            "cc": "",
            "subject": "Unterlagen 2026",
            "body": "Sehr geehrte Frau Müller,\n\nbitte Belege.",
            "questions": ["Z erste", "A zweite", "M dritte"],
        },
    )

    assert r.status_code == 200
    assert fake.attached is not None
    letter = parse_request_letter(fake.attached["file_bytes"].decode("utf-8"))
    # exact tuple equality: ORDER preserved, not mere membership
    assert letter.questions == ("Z erste", "A zweite", "M dritte")


def test_B3_post_without_questions_key_creates_with_empty_questions() -> None:
    fake = _FakeClient()
    client = _client(fake)

    # the 'questions' key is entirely ABSENT (not questions=[]) — the SB
    # added no question rows at all
    r = client.post(
        "/sb/create",
        data={
            "vgm_number": str(VGM_NUMBER),
            "to": "mandant@example.com",
            "cc": "",
            "subject": "Unterlagen 2026",
            "body": "Sehr geehrte Frau Müller,\n\nbitte Belege.",
        },
    )

    assert r.status_code == 200
    body = r.text
    assert fake.attached is not None

    letter = parse_request_letter(fake.attached["file_bytes"].decode("utf-8"))
    assert letter.questions == ()  # core received zero questions
    assert letter.subject == "Unterlagen 2026"
    assert "bitte Belege." in letter.body

    payload = verify_token(token=_extract_token(body, BASE_URL), secret=SECRET, now=NOW)
    assert payload.vgm_id == VGM_GUID


def test_B5_non_numeric_vgm_number_rerenders_form_no_resolver_no_core() -> None:
    fake = _FakeClient()
    client = _client(fake)

    r = client.post(
        "/sb/create",
        data={
            "vgm_number": "abc",  # not a number
            "to": "mandant@example.com",
            "cc": "kanzlei@example.com",
            "subject": "Unterlagen 2026",
            "body": "Sehr geehrte Frau Müller,\n\nbitte Belege.",
            "questions": ["Fahrtkosten 2026?", "Arbeitszimmer genutzt?"],
        },
    )

    # not a 500, not a 4xx — the form redisplays itself
    assert r.status_code == 200
    body = r.text
    assert 'action="/sb/create"' in body  # it IS the form
    assert "Zahl" in body  # "... muss eine Zahl sein."

    # neither the resolver nor the core was touched (short-circuit before
    # any network) — this is the form-shape stage, distinct from resolve
    assert fake.list_documents_called is False
    assert fake.attached is None

    # every entered value is preserved (no retyping the body)
    assert 'value="abc"' in body
    assert "mandant@example.com" in body
    assert "kanzlei@example.com" in body
    assert "Unterlagen 2026" in body
    assert "bitte Belege." in body
    pos1 = body.find("Fahrtkosten 2026?")
    pos2 = body.find("Arbeitszimmer genutzt?")
    assert pos1 != -1 and pos2 != -1 and pos1 < pos2  # both, in order


def test_B6_numeric_but_unknown_binder_rerenders_form_no_core() -> None:
    # resolver finds NO doc with this number -> resolve_binder_guid_by_number
    # returns None (distinct from "not a number" B5 and "DATEV down" B12)
    fake = _FakeClient(docs=[{"number": 999999, "id": "other-guid"}])
    client = _client(fake)

    r = client.post(
        "/sb/create",
        data={
            "vgm_number": "395357",  # syntactically valid, just not present
            "to": "mandant@example.com",
            "cc": "kanzlei@example.com",
            "subject": "Unterlagen 2026",
            "body": "Sehr geehrte Frau Müller,\n\nbitte Belege.",
            "questions": ["Fahrtkosten 2026?", "Arbeitszimmer genutzt?"],
        },
    )

    assert r.status_code == 200  # not 500
    body = r.text
    assert 'action="/sb/create"' in body  # the form, re-rendered
    # resolver WAS consulted (this is the resolve stage, unlike B5)
    assert fake.list_documents_called is True
    # core never reached
    assert fake.attached is None
    # message distinguishes "unknown" from "not a number"
    assert "nicht gefunden" in body
    assert "Zahl" not in body
    # values preserved incl. both questions in order
    assert 'value="395357"' in body
    assert "mandant@example.com" in body
    assert "kanzlei@example.com" in body
    assert "Unterlagen 2026" in body
    assert "bitte Belege." in body
    p1 = body.find("Fahrtkosten 2026?")
    p2 = body.find("Arbeitszimmer genutzt?")
    assert p1 != -1 and p2 != -1 and p1 < p2


def test_B7_blank_subject_rerenders_form_with_field_message_no_core() -> None:
    fake = _FakeClient()
    client = _client(fake)

    r = client.post(
        "/sb/create",
        data={
            "vgm_number": "395357",  # valid + resolvable
            "to": "mandant@example.com",
            "cc": "kanzlei@example.com",
            "subject": "   ",  # blank after strip -> CreateRequestArgs fails
            "body": "Sehr geehrte Frau Müller,\n\nbitte Belege.",
            "questions": ["Fahrtkosten 2026?", "Arbeitszimmer genutzt?"],
        },
    )

    assert r.status_code == 200  # not 500
    body = r.text
    assert 'action="/sb/create"' in body  # the form, re-rendered

    # resolve stage SUCCEEDED (valid number) but the core was never
    # reached — validation short-circuits before run_create_request
    assert fake.list_documents_called is True
    assert fake.attached is None

    # the 4a validator's own message, surfaced on the form
    assert "must not be blank" in body
    # not confused with the vgm_number stages
    assert "Zahl" not in body
    assert "nicht gefunden" not in body

    # other scalar values preserved (no retyping the body)
    assert "mandant@example.com" in body
    assert "kanzlei@example.com" in body
    assert "bitte Belege." in body
    assert 'value="395357"' in body
    p1 = body.find("Fahrtkosten 2026?")
    p2 = body.find("Arbeitszimmer genutzt?")
    assert p1 != -1 and p2 != -1 and p1 < p2


def test_B8_blank_question_rerenders_all_rows_with_error_at_that_row() -> None:
    fake = _FakeClient()
    client = _client(fake)

    # 0-based 4a convention: index 1 is the SECOND row -> "question 1"
    r = client.post(
        "/sb/create",
        data={
            "vgm_number": "395357",
            "to": "mandant@example.com",
            "cc": "",
            "subject": "Unterlagen 2026",
            "body": "Sehr geehrte Frau Müller,\n\nbitte Belege.",
            "questions": ["Fahrtkosten 2026?", "   ", "Arbeitszimmer genutzt?"],
        },
    )

    assert r.status_code == 200  # not 500
    body = r.text
    assert 'action="/sb/create"' in body  # the form, re-rendered

    # resolve succeeded, core never reached
    assert fake.list_documents_called is True
    assert fake.attached is None

    # ALL THREE question rows preserved, in order (good rows keep text)
    qfields = body.count('name="questions"')
    # 3 rendered rows + the hidden <template> clone row = 4 inputs
    assert qfields >= 3
    pA = body.find("Fahrtkosten 2026?")
    pC = body.find("Arbeitszimmer genutzt?")
    assert pA != -1 and pC != -1 and pA < pC

    # the 4a message (0-based "question 1") is present...
    assert "question 1 must not be blank" in body
    # ...and CO-LOCATED with the offending (2nd) row, not dumped at top:
    # it appears after the 1st row's value and before the 3rd row's value
    err = body.find("question 1 must not be blank")
    assert pA < err < pC

    # visible human numbering so the row is identifiable in the UI
    assert "Frage 1" in body and "Frage 2" in body and "Frage 3" in body

    # not confused with the other stages
    assert "Zahl" not in body and "nicht gefunden" not in body


@pytest.mark.parametrize(
    ("fake_kwargs", "expected_phrase", "forbidden_internal"),
    [
        # UploadFailed: real upload_to_binder gets an id-less attach
        # response -> UploadResult(success=False) -> run_create_request
        # raises UploadFailed
        (
            {"attach_returns": {}},
            "hochgeladen werden",
            "Unexpected response shape",
        ),
        # InvalidUploadTarget: get_document returns a non-Vorgangsmappe
        # -> upload_to_binder raises InvalidUploadTarget before attach
        (
            {"binder_doc": {"is_binder": False, "extension": "X", "id": VGM_GUID}},
            "keine gültige Vorgangsmappe",
            "is_binder",
        ),
    ],
    ids=["UploadFailed", "InvalidUploadTarget"],
)
def test_B9_core_upload_failure_rerenders_with_curated_banner(
    fake_kwargs: dict[str, Any],
    expected_phrase: str,
    forbidden_internal: str,
) -> None:
    fake = _FakeClient(**fake_kwargs)
    client = _client(fake)

    r = client.post(
        "/sb/create",
        data={
            "vgm_number": "395357",
            "to": "mandant@example.com",
            "cc": "kanzlei@example.com",
            "subject": "Unterlagen 2026",
            "body": "Sehr geehrte Frau Müller,\n\nbitte Belege.",
            "questions": ["Fahrtkosten 2026?", "Arbeitszimmer genutzt?"],
        },
    )

    assert r.status_code == 200  # not 500
    body = r.text
    assert 'action="/sb/create"' in body  # the form, re-rendered

    # CORE WAS REACHED then failed: run_create_request actually entered
    # upload_to_binder (get_document called) — proven positively, NOT via
    # `attached is None` (which can't tell "never reached" from "reached,
    # failed pre-attach")
    assert fake.get_document_called is True

    # curated, user-facing banner — NOT raw str(exc)/internal details
    assert expected_phrase in body
    assert forbidden_internal not in body
    assert "Traceback" not in body
    assert "rejected:" not in body  # InvalidUploadTarget.__str__ guts
    assert "UploadResult" not in body

    # values preserved (no retyping the body after an upload failure)
    assert 'value="395357"' in body
    assert "mandant@example.com" in body
    assert "kanzlei@example.com" in body
    assert "bitte Belege." in body
    p1 = body.find("Fahrtkosten 2026?")
    p2 = body.find("Arbeitszimmer genutzt?")
    assert p1 != -1 and p2 != -1 and p1 < p2


def _assert_escaped(body: str, marker: str) -> None:
    """The raw <script> for `marker` must be ABSENT and its escaped
    form PRESENT — pins autoescape per-field (a future |safe/Markup on
    that one field would resurface its unique raw marker)."""
    assert f"<script>{marker}</script>" not in body
    assert f"&lt;script&gt;{marker}&lt;/script&gt;" in body


def test_B10_every_echoed_surface_is_html_escaped() -> None:
    # test-as-contract: autoescape is already configured (app.py
    # jinja2.Environment(autoescape=True)); no RED expected. The value
    # is the regression pin against a future |safe / Markup().
    TO, CC, SUB, BODY, Q1, Q2, VGM = "TO", "CC", "SUB", "BODY", "Q1", "Q2", "VGM"

    def payload(m: str) -> str:
        return f"<script>{m}</script>"

    # --- Leg A: B5 path (non-numeric vgm -> FormValidationError) ---
    # covers vgm_number (value attr) + to/cc/subject (value attrs) +
    # body (textarea) + each question row
    fake_a = _FakeClient()
    r_a = _client(fake_a).post(
        "/sb/create",
        data={
            "vgm_number": payload(VGM),  # non-numeric -> B5 re-render
            "to": payload(TO),
            "cc": payload(CC),
            "subject": payload(SUB),
            "body": payload(BODY),
            "questions": [payload(Q1), payload(Q2)],
        },
    )
    assert r_a.status_code == 200
    body_a = r_a.text
    assert 'action="/sb/create"' in body_a  # re-rendered form
    for m in (VGM, TO, CC, SUB, BODY, Q1, Q2):
        _assert_escaped(body_a, m)
    # Precise blanket: form.html has exactly 2 FIRST-PARTY `<script`
    # (Tailwind CDN + the add/remove JS). A naive `"<script>" not in
    # body` would false-positive on those; a whitelist-by-COUNT instead
    # catches ANY raw injected <script on ANY echoed surface — including
    # a future new field not in the per-field list above. If a legit
    # first-party script is added, bump this number deliberately.
    assert body_a.count("<script") == 2

    # --- Leg B: B9 banner path (InvalidUploadTarget) ---
    # vgm_number must be numeric+resolvable to REACH the banner branch;
    # all other fields carry <script> and must stay escaped while the
    # curated banner is rendered
    fake_b = _FakeClient(
        binder_doc={"is_binder": False, "extension": "X", "id": VGM_GUID}
    )
    r_b = _client(fake_b).post(
        "/sb/create",
        data={
            "vgm_number": "395357",
            "to": payload(TO),
            "cc": payload(CC),
            "subject": payload(SUB),
            "body": payload(BODY),
            "questions": [payload(Q1), payload(Q2)],
        },
    )
    assert r_b.status_code == 200
    body_b = r_b.text
    assert "keine gültige Vorgangsmappe" in body_b  # banner branch hit
    for m in (TO, CC, SUB, BODY, Q1, Q2):
        _assert_escaped(body_b, m)
    assert body_b.count("<script") == 2  # same first-party whitelist-by-count


_REQ = __import__("httpx").Request("GET", "https://api.klardaten.com/documents")


@pytest.mark.parametrize(
    ("exc", "expect_present", "expect_absent"),
    [
        # transient: connection refused (RequestError) -> retry-implying
        (
            __import__("httpx").ConnectError("connection refused"),
            "nicht erreichbar",
            "Zugangsdaten",
        ),
        # transient: 5xx -> retry-implying
        (
            __import__("httpx").HTTPStatusError(
                "server error",
                request=_REQ,
                response=__import__("httpx").Response(503, request=_REQ),
            ),
            "nicht erreichbar",
            "Zugangsdaten",
        ),
        # NON-transient: 403 -> credentials/config, NO retry promise
        (
            __import__("httpx").HTTPStatusError(
                "forbidden",
                request=_REQ,
                response=__import__("httpx").Response(403, request=_REQ),
            ),
            "Zugangsdaten",
            "nicht erreichbar",
        ),
    ],
    ids=["RequestError", "5xx", "4xx-403"],
)
def test_B12_resolver_http_error_rerenders_classified_banner(
    exc: Exception, expect_present: str, expect_absent: str
) -> None:
    fake = _FakeClient(list_raises=exc)
    client = _client(fake)

    r = client.post(
        "/sb/create",
        data={
            "vgm_number": "395357",  # syntactically valid -> reaches resolver
            "to": "mandant@example.com",
            "cc": "kanzlei@example.com",
            "subject": "Unterlagen 2026",
            "body": "Sehr geehrte Frau Müller,\n\nbitte Belege.",
            "questions": ["Fahrtkosten 2026?", "Arbeitszimmer genutzt?"],
        },
    )

    assert r.status_code == 200  # not 500
    body = r.text
    assert 'action="/sb/create"' in body  # form re-rendered

    # resolve stage: resolver WAS consulted, core never reached
    assert fake.list_documents_called is True
    assert fake.attached is None

    # classified, distinct from B6's "nicht gefunden"
    assert expect_present in body
    assert expect_absent not in body
    assert "nicht gefunden" not in body
    assert "Traceback" not in body

    # values preserved
    assert 'value="395357"' in body
    assert "bitte Belege." in body
    p1 = body.find("Fahrtkosten 2026?")
    p2 = body.find("Arbeitszimmer genutzt?")
    assert p1 != -1 and p2 != -1 and p1 < p2


def test_B13_local_file_oserror_rerenders_distinct_banner_not_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local temp-file write fails inside the REAL run_create_request
    (stdlib Path.write_text patched to raise — the core itself is NOT
    mocked, same real-wiring discipline as B9/B12). This is a distinct
    stage from B9 (upload) and not a programmer bug."""
    wrote: list[bool] = []

    def boom(self: object, *a: object, **k: object) -> int:
        wrote.append(True)
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("pathlib.Path.write_text", boom)

    fake = _FakeClient()
    client = _client(fake)

    r = client.post(
        "/sb/create",
        data={
            "vgm_number": "395357",
            "to": "mandant@example.com",
            "cc": "kanzlei@example.com",
            "subject": "Unterlagen 2026",
            "body": "Sehr geehrte Frau Müller,\n\nbitte Belege.",
            "questions": ["Fahrtkosten 2026?", "Arbeitszimmer genutzt?"],
        },
    )

    assert r.status_code == 200  # NOT 500
    body = r.text
    assert 'action="/sb/create"' in body  # form re-rendered

    # real core path reached: resolve done, run_create_request entered
    # and hit the write step (spy fired), upload never reached
    assert fake.list_documents_called is True
    assert wrote == [True]
    assert fake.attached is None

    # distinct B13 banner; B9 wordings MUST be absent
    assert "lokal" in body or "Dateisystem" in body
    assert "hochgeladen werden" not in body
    assert "keine gültige Vorgangsmappe" not in body
    assert "nicht erreichbar" not in body  # not B12 either
    assert "Traceback" not in body

    # values preserved
    assert 'value="395357"' in body
    assert "bitte Belege." in body
    p1 = body.find("Fahrtkosten 2026?")
    p2 = body.find("Arbeitszimmer genutzt?")
    assert p1 != -1 and p2 != -1 and p1 < p2


def test_B14_bare_post_rerenders_form_banner_200_not_raw_422() -> None:
    """FastAPI validates Form(...) BEFORE the handler body, so a bare
    POST raises RequestValidationError and never reaches B5-B13. It must
    re-render the form + banner at HTTP 200, NOT raw 422 JSON."""
    fake = _FakeClient()
    client = _client(fake)

    r = client.post("/sb/create")  # no body at all

    assert r.status_code == 200  # friendly-re-render invariant, NOT 422
    assert "text/html" in r.headers["content-type"]  # NOT application/json
    body = r.text
    assert 'action="/sb/create"' in body
    assert "Pflichtfelder" in body or "unvollständig" in body
    assert '"detail"' not in body  # not the raw FastAPI JSON error shape
    # pre-handler: nothing downstream touched
    assert fake.list_documents_called is False
    assert fake.attached is None


def test_B14_incomplete_post_salvages_submitted_values() -> None:
    """Partial body (some fields present, a REQUIRED one absent ->
    RequestValidationError). B14 must preserve what the SB typed, like
    B5-B13 — the no-salvage approach was revised after the smoke showed
    its cost (an accidental submit wiped a multi-paragraph body)."""
    fake = _FakeClient()
    client = _client(fake)

    # 'vgm_number' and 'body' (required) omitted -> pre-handler 422;
    # 'to'/'subject'/'questions' were typed and must survive
    r = client.post(
        "/sb/create",
        data={
            "to": "mandant@example.com",
            "subject": "Unterlagen 2026",
            "questions": ["Fahrtkosten 2026?", "Arbeitszimmer genutzt?"],
        },
    )

    assert r.status_code == 200
    body = r.text
    assert 'action="/sb/create"' in body
    assert "Pflichtfelder" in body or "unvollständig" in body
    # SALVAGED values present (not wiped to an empty form)
    assert "mandant@example.com" in body
    assert "Unterlagen 2026" in body
    p1 = body.find("Fahrtkosten 2026?")
    p2 = body.find("Arbeitszimmer genutzt?")
    assert p1 != -1 and p2 != -1 and p1 < p2
    assert fake.list_documents_called is False
    assert fake.attached is None


def test_B15_get_on_post_only_create_redirects_to_form_not_405() -> None:
    """A GET to the action URL (navigated / refreshed / bookmarked) must
    bounce to /sb, not emit a raw 405 Method Not Allowed JSON."""
    client = _client(_FakeClient())

    r = client.get("/sb/create", follow_redirects=False)

    assert r.status_code == 303  # See Other -> GET /sb
    assert r.headers["location"] == "/sb"
