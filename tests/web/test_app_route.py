"""Route tests for GET /r/{token} via FastAPI TestClient.

The route is humble glue. Deps (letter source, secret, now) are FastAPI
dependencies overridden here so no env / real DATEV is touched.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from belegmeister.magic_link.token import generate_token
from belegmeister.request_format import RequestLetter, serialize_request_letter
from belegmeister.web.app import app, get_letter_source, get_now, get_secret

SECRET = "w" * 48
NOW = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)
VGM = "3bf17a53-42ca-4a03-9275-213bd1c6b263"

# Wire-format `request/v1` payload — after Step 0, `resolve_request_view`
# parses the downloaded bytes before producing the `RequestView`.
_LETTER_BODY = "Sehr geehrte Damen und Herren,\nbitte Belege 2026 senden."
LETTER = serialize_request_letter(
    RequestLetter(
        to="client@example.com",
        cc="",
        subject="Belege 2026",
        body=_LETTER_BODY,
        questions=(),
    )
)


def _make_letter_bytes(
    *,
    to: str = "client@example.com",
    cc: str = "",
    subject: str = "Belege 2026",
    body: str = _LETTER_BODY,
    questions: tuple[str, ...] = (),
) -> bytes:
    """Build a valid wire-format letter file content for fixture use.

    Per-test customization via kwargs; defaults match the module-level
    happy-path `LETTER`. All inputs flow through `serialize_request_letter`
    so the codec is the single source of truth for the wire format —
    handwritten payloads would drift if the codec evolves.
    """
    return serialize_request_letter(
        RequestLetter(to=to, cc=cc, subject=subject, body=body, questions=questions)
    ).encode("utf-8")


class _FakeSource:
    def __init__(
        self,
        *,
        children: list[dict[str, Any]] | None = None,
        files: dict[int, bytes] | None = None,
    ) -> None:
        self._children = (
            children
            if children is not None
            else [
                {
                    "name": "_request_letter_2026-05-15T080805Z.txt",
                    "type": 1,
                    "counter": 2,
                    "document_file_id": 1152156,
                    "id": "1170198",
                }
            ]
        )
        self._files = files if files is not None else {1152156: LETTER.encode("utf-8")}

    def list_structure_items(self, binder_guid: str) -> list[dict[str, Any]]:
        return self._children

    def download_document_file(self, document_file_id: int) -> bytes:
        return self._files[document_file_id]


def _valid_token() -> str:
    return generate_token(vgm_id=VGM, expires_at=NOW + timedelta(days=3), secret=SECRET)


def _client(src: _FakeSource) -> TestClient:
    app.dependency_overrides[get_letter_source] = lambda: src
    app.dependency_overrides[get_secret] = lambda: SECRET
    app.dependency_overrides[get_now] = lambda: NOW
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(autouse=True)
def _clear_overrides() -> Any:
    yield
    app.dependency_overrides.clear()


def test_RT1_valid_token_renders_200_with_letter_and_form() -> None:
    token = _valid_token()
    client = _client(_FakeSource())

    r = client.get(f"/r/{token}")

    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    # letter content present (escaped in <pre>, plain text here)
    assert "Sehr geehrte Damen und Herren," in body
    # form wired for the (future) submit endpoint, multipart + required
    assert f'action="/r/{token}/submit"' in body
    assert 'method="POST"' in body
    assert 'enctype="multipart/form-data"' in body
    assert 'name="files"' in body
    assert "multiple" in body
    assert 'name="response"' in body


def test_RT2_invalid_token_404_generic_no_disclosure_structured_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    forged = generate_token(
        vgm_id=VGM, expires_at=NOW + timedelta(days=3), secret="OTHER" * 8
    )
    client = _client(_FakeSource())

    with caplog.at_level(logging.WARNING, logger="belegmeister.web"):
        r = client.get(f"/r/{forged}")

    assert r.status_code == 404
    assert "text/html" in r.headers["content-type"]
    body = r.text
    # generic message, no cause disclosure to the client
    assert "ungültig" in body or "abgelaufen" in body
    assert "token_bad_signature" not in body
    assert "token_expired" not in body
    # structured server log: forged secret → bad_signature (tamper
    # signal), reason present, token NEVER logged
    assert "magic_link_rejected" in caplog.text
    assert "token_bad_signature" in caplog.text
    assert forged not in caplog.text


# =============================================================================
# G1 RED tests for slice magic-link-ui (Bucket 1 — 10 new tests)
# See .overseer/slice/magic-link-ui.md § Hardest seams + § Exit criterion.
#
# RT3 (`test_RT3_xss_letter_text_is_html_escaped`) was deleted in UNIT 3
# of this slice — it tested a variable (`letter_text`) that no longer
# exists in the template context after the Step 0 refactor (Decision
# D-C). Coverage of XSS escape on the new rendered surfaces is now
# split across S3-T1 (subject), S3-T2 (body), and S3-T3 (question
# text) below.
# =============================================================================


def test_parsed_subject_renders_in_h1() -> None:
    """Primary goal: the parsed letter.subject must appear inside <h1>.

    Anti-pattern ruled out: rendered template carries the SB's subject
    only as a hidden field or in the <title>, leaving the Mandant
    uncertain which request this is.

    Mutation argument: change the template's `<h1>{{ letter.subject }}</h1>`
    back to a hardcoded heading and this test fires.

    Classification (G1): textbook RED — h1 is currently hardcoded
    'Dokumentanforderung Ihrer Kanzlei'; subject doesn't appear there.
    """
    src = _FakeSource(files={1152156: _make_letter_bytes(subject="Belege Q1-2026")})
    token = _valid_token()
    client = _client(src)

    r = client.get(f"/r/{token}")

    assert r.status_code == 200
    body = r.text
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.DOTALL)
    assert h1_match is not None, "no <h1> in rendered page"
    assert "Belege Q1-2026" in h1_match.group(1)


def test_parsed_body_renders_without_wire_markers() -> None:
    """Primary goal: the rendered Mandant page must NEVER contain
    wire-format sentinel markers (`==BELEGMEISTER==`, `request/v1`,
    `fragen`, `end`).

    Pre-refactor the template rendered raw `letter_text`, leaking the
    full wire format into the Mandant's view (Phase 0 P6). Step 0
    swapped in parsed `letter.body`. This test pins the leak does not
    return.

    Anti-pattern ruled out: a future refactor that pipes raw wire
    text back into the template (e.g., for 'debug viewing'), or a
    template that includes header lines verbatim.

    Mutation argument: change `{{ letter.body }}` back to a
    reconstructed `serialize_request_letter(letter)` rendering and
    this test fires immediately.

    Classification (G1): regression guard — Step 0 already delivers
    the fix; this test pins the headline behavior against future
    drift. PASSES on first run.
    """
    src = _FakeSource(
        files={
            1152156: _make_letter_bytes(
                body="Bitte um die folgenden Belege.",
                questions=("Datum?",),
            )
        }
    )
    token = _valid_token()
    client = _client(src)

    r = client.get(f"/r/{token}")

    assert r.status_code == 200
    body = r.text
    assert "==BELEGMEISTER==" not in body
    # Sanity: we are actually rendering body content (not an empty page)
    assert "Bitte um die folgenden Belege." in body


def test_per_question_inputs_have_distinct_indexed_names() -> None:
    """S2-T1: each question gets a distinct 0-indexed `answer_<N>` input.

    Anti-pattern ruled out: hardcoded index in the loop (`name="answer_0"`
    repeated for every question), or off-by-one between `loop.index`
    (1-based) and `loop.index0` (0-based, the contract per D-E).

    Mutation argument: swap `loop.index0` → `loop.index` and this test
    fires (matches become `[answer_1, answer_2, answer_3]`). Hardcode
    `name="answer_0"` and matches collapse to `[answer_0, answer_0,
    answer_0]`.

    Fixture-design note (artifact D-smoke-fixture): question strings
    are deliberately non-substring-colliding ("Question alpha"/
    "Question beta"/"Question gamma" share no prefixes with each
    other or with form chrome). Do NOT substitute "Frage 1/2/3" —
    that would silently weaken S2-T2's byte-offset assertion.

    Classification (G1): textbook RED — no question-loop exists in
    the template yet; zero `answer_<N>` matches → fails.
    """
    src = _FakeSource(
        files={
            1152156: _make_letter_bytes(
                questions=("Question alpha", "Question beta", "Question gamma"),
            )
        }
    )
    token = _valid_token()
    client = _client(src)

    r = client.get(f"/r/{token}")

    assert r.status_code == 200
    body = r.text
    matches = re.findall(r'name="(answer_\d+)"', body)
    assert matches == ["answer_0", "answer_1", "answer_2"], (
        f"expected exactly [answer_0, answer_1, answer_2] in order; got {matches}"
    )


def test_per_question_inputs_ordered_with_question_text() -> None:
    """S2-T2: question text precedes its `answer_<N>` input in DOM
    order, alternating with the next question.

    Anti-pattern ruled out: rendering inputs in reverse order, or
    pairing each input with the wrong question label (a 'Frage 2'
    visible label sitting next to `name="answer_0"`).

    Mutation argument: render the questions tuple in reverse and the
    byte-offset chain breaks.

    Fixture-design note: non-substring-colliding strings (artifact
    D-smoke-fixture) are LOAD-BEARING here — `body.index("Question alpha")`
    must be unambiguous.

    Classification (G1): textbook RED — no question-loop exists yet;
    `body.index("Question alpha")` raises ValueError (text absent).
    """
    src = _FakeSource(
        files={
            1152156: _make_letter_bytes(
                questions=("Question alpha", "Question beta", "Question gamma"),
            )
        }
    )
    token = _valid_token()
    client = _client(src)

    r = client.get(f"/r/{token}")

    assert r.status_code == 200
    body = r.text
    # Byte-offset ordering: alpha < answer_0 < beta < answer_1 < gamma < answer_2
    i_alpha = body.index("Question alpha")
    i_a0 = body.index('name="answer_0"')
    i_beta = body.index("Question beta")
    i_a1 = body.index('name="answer_1"')
    i_gamma = body.index("Question gamma")
    i_a2 = body.index('name="answer_2"')
    assert i_alpha < i_a0 < i_beta < i_a1 < i_gamma < i_a2, (
        f"ordering broken: alpha@{i_alpha} a0@{i_a0} beta@{i_beta} "
        f"a1@{i_a1} gamma@{i_gamma} a2@{i_a2}"
    )


def test_subject_html_escaped() -> None:
    """S3-T1: a `<script>` payload in parsed letter.subject must be
    HTML-escaped in the rendered page.

    Anti-pattern ruled out: `{{ letter.subject | safe }}` or a
    `{% autoescape false %}` block around the heading.

    Mutation argument: add `| safe` filter to the subject template
    variable and this test fires.

    Classification (G1): feature-absent RED — subject is not yet
    rendered into <h1>, so the escaped-script-marker assertion fails
    (the escaped form simply isn't in the body anywhere). After
    UNIT 2 lands the h1 rendering, this becomes a real regression
    guard against `| safe` introduction.
    """
    payload = '<script>alert("xss-subject")</script>'
    src = _FakeSource(files={1152156: _make_letter_bytes(subject=payload)})
    token = _valid_token()
    client = _client(src)

    r = client.get(f"/r/{token}")

    assert r.status_code == 200
    body = r.text
    # Raw script tag must NOT appear in body (would be live XSS)
    assert '<script>alert("xss-subject")</script>' not in body
    # Escaped form must appear (proves autoescape ran on this surface)
    assert "&lt;script&gt;" in body
    assert "&lt;/script&gt;" in body
    # And the unique inner identifier must be present (escaped quotes vary
    # by Jinja2 version; the inner text is invariant)
    assert "xss-subject" in body


def test_body_html_escaped() -> None:
    """S3-T2: a `<script>` payload in parsed letter.body must be
    HTML-escaped in the rendered page.

    Anti-pattern ruled out: `{{ letter.body | safe }}` or a
    `{% autoescape false %}` block around the body section.

    Mutation argument: disable autoescape on the body section and
    this test fires.

    Classification (G1): regression guard — Step 0 renders
    `{{ letter.body }}` with autoescape=True (structural Jinja2 env
    setting at request_view.py-rendering layer); autoescape is on
    for `.html` templates AND unconditionally per `web/app.py:60-63`.
    PASSES on first run.
    """
    body_payload = '<script>alert("xss-body")</script>'
    src = _FakeSource(files={1152156: _make_letter_bytes(body=body_payload)})
    token = _valid_token()
    client = _client(src)

    r = client.get(f"/r/{token}")

    assert r.status_code == 200
    body = r.text
    assert '<script>alert("xss-body")</script>' not in body
    assert "&lt;script&gt;" in body
    assert "&lt;/script&gt;" in body
    assert "xss-body" in body


def test_question_text_html_escaped() -> None:
    """S3-T3: a `<script>` payload in a parsed letter.questions entry
    must be HTML-escaped in the rendered page.

    Anti-pattern ruled out: `{{ q | safe }}` inside the question loop
    or `{% autoescape false %}` around the questions section.

    Mutation argument: add `| safe` filter inside the loop and this
    test fires.

    Classification (G1): feature-absent RED — no question loop yet,
    so the injected script doesn't appear anywhere in body (neither
    raw nor escaped), failing the `&lt;script&gt; in body` assertion.
    After UNIT 2 lands the loop, this becomes a real regression
    guard.
    """
    question_payload = '<script>alert("xss-question")</script>'
    src = _FakeSource(
        files={1152156: _make_letter_bytes(questions=(question_payload,))}
    )
    token = _valid_token()
    client = _client(src)

    r = client.get(f"/r/{token}")

    assert r.status_code == 200
    body = r.text
    assert '<script>alert("xss-question")</script>' not in body
    assert "&lt;script&gt;" in body
    assert "&lt;/script&gt;" in body
    assert "xss-question" in body


def test_question_section_hidden_when_no_questions() -> None:
    """S4: when the letter has no questions, the question section
    wrapper must be entirely absent from the rendered page.

    Anti-pattern ruled out: a section heading or empty `<fieldset>`
    wrapper that renders regardless of question count, leaving a
    visually orphaned label or empty bordered container.

    Mutation argument: remove the `{% if letter.questions %}` guard
    in UNIT 2's template change and this test fires (wrapper renders
    with zero children, `questions-block` id present in body).

    Classification (G1): regression guard pre-UNIT-2 (no wrapper
    exists yet to test) — becomes load-bearing AFTER UNIT 2 lands
    the unconditional `<section id="questions-block">` wrapper. The
    user's plan §6 R2 sequences this so UNIT 2 ships wrapper+guard
    together, making S4 a regression guard from the moment it has a
    surface. PASSES on first run.
    """
    src = _FakeSource(files={1152156: _make_letter_bytes(questions=())})
    token = _valid_token()
    client = _client(src)

    r = client.get(f"/r/{token}")

    assert r.status_code == 200
    body = r.text
    assert "questions-block" not in body


def test_letter_malformed_logs_reason_and_returns_404(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """S5: bytes that decode as UTF-8 but fail `parse_request_letter`
    map to the canonical log_reason 'letter_malformed' (Decision
    D-D); client still sees the generic 404.

    Anti-pattern ruled out: collapsing parse failures into
    `letter_not_utf8` (semantic loss across distinct failure modes),
    or letting `RequestLetterMalformed` bubble unhandled to a 500.

    Mutation argument: remove the try/except around `parse_request_letter`
    in `_parse_letter` and this test fires (uncaught exception → 500
    rather than 404 + log_reason).

    Classification (G1): regression guard — UNIT 1's Step 0 refactor
    added the `_parse_letter` helper with the catch and log_reason
    mapping. PASSES on first run; pins the handling against future
    removal.
    """
    # Valid UTF-8, but not a wire-format `request/v1` payload
    src = _FakeSource(files={1152156: b"not a valid wire format\n"})
    token = _valid_token()
    client = _client(src)

    with caplog.at_level(logging.WARNING, logger="belegmeister.web"):
        r = client.get(f"/r/{token}")

    assert r.status_code == 404
    # Exactly one WARNING record from belegmeister.web (artifact S5)
    web_warnings = [
        rec
        for rec in caplog.records
        if rec.name == "belegmeister.web" and rec.levelname == "WARNING"
    ]
    assert len(web_warnings) == 1, (
        f"expected 1 belegmeister.web WARNING, got {len(web_warnings)}"
    )
    msg = web_warnings[0].getMessage()
    assert "magic_link_rejected" in msg
    assert "reason=letter_malformed" in msg
    # log_context must include vgm_id AND codec's short reason
    assert "vgm_id" in msg
    assert "reason" in msg  # the codec's short code key inside the dict


def test_to_and_cc_not_in_rendered_page() -> None:
    """S8: parsed letter.to and letter.cc values MUST NEVER appear in
    the rendered Mandant page (Decision D-S8 — privacy +
    XSS-surface-by-construction).

    Anti-pattern ruled out: passing the full letter to the template
    AND the template rendering `{{ letter.to }}` or `{{ letter.cc }}`
    anywhere — OR a `**asdict(letter)` style context expansion that
    silently leaks both into the namespace where a future innocent
    `{{ to }}` would pick them up.

    Mutation argument: add `{{ letter.to }}` or `{{ letter.cc }}`
    anywhere in `request.html` (e.g., for 'transparency') and this
    test fires immediately.

    Classification (G1): regression guard — Step 0 passes the full
    letter to the template (deferring the narrow to UNIT 4 / S8
    GREEN so this test has a meaningful surface) BUT the template
    does not reference to/cc. UNIT 4 narrows the context at the
    route boundary, after which leak becomes structurally
    impossible — but this test still fires if a future developer
    re-widens the context. PASSES on first run.

    Sentinel design: 'SENTINEL_TO_VALUE_xyz123' / 'SENTINEL_CC_VALUE_abc789'
    are deliberately longer and higher-hash-distance than the
    artifact's bare names (per user approval) — no substring
    collision possible with form chrome.
    """
    src = _FakeSource(
        files={
            1152156: _make_letter_bytes(
                to="SENTINEL_TO_VALUE_xyz123@example.com",
                cc="SENTINEL_CC_VALUE_abc789@example.com",
            )
        }
    )
    token = _valid_token()
    client = _client(src)

    r = client.get(f"/r/{token}")

    assert r.status_code == 200
    body = r.text
    assert "SENTINEL_TO_VALUE_xyz123" not in body
    assert "SENTINEL_CC_VALUE_abc789" not in body


def test_response_textarea_is_optional() -> None:
    """UNIT 7 — Anmerkungen textarea must not be marked `required` at the
    HTML level.

    Per Decision D-P1.2 (wire-contract lock), required-ness is submit-
    handler policy, NOT wire contract. The textarea must accept empty
    submission so the submit-slice can decide validation server-side.
    Discovered during smoke walkthrough: the original template carried
    a stray `required` attribute that browser-level HTML5 validation
    enforced before the request hit the handler — pre-locking what
    should be a server-side policy choice.

    Anti-pattern ruled out: `<textarea name="response" required>` —
    browser-side HTML5 `required` makes empty submission impossible
    without dev-tools tinkering, contradicting D-P1.2's framing.

    Mutation argument: re-add `required` to the textarea opening tag
    and this test fires.

    Implementation note: uses regex on the textarea opening tag (matches
    the file's existing convention — S2-T1/T2 also use regex; no BS4
    dependency added).
    """
    src = _FakeSource()
    token = _valid_token()
    client = _client(src)

    r = client.get(f"/r/{token}")

    assert r.status_code == 200
    body = r.text
    # Match the opening tag of the response textarea; capture attributes
    # up to (but not including) the closing `>` of the opening tag.
    # `[^>]*` includes newlines because newline ≠ '>' — the textarea
    # opening tag spans two source lines in the template. No `\b`
    # word-boundary after `"response"` — both `"` and the next whitespace
    # are non-word characters, so `\b` would not match (and the search
    # would silently fail to find a real textarea).
    match = re.search(r'<textarea\s+name="response"([^>]*)>', body)
    assert match is not None, "response textarea opening tag not found"
    attrs = match.group(1)
    # The `required` attribute must NOT appear among the opening tag's
    # attributes. The label text "(optional)" lives in a separate
    # `<label>` element, not inside this group, so it cannot trigger a
    # false positive. Check both whitespace-leading forms (`name=" required"`
    # would be a value, not a flag — also excluded).
    assert " required" not in attrs and "\trequired" not in attrs, (
        f"response textarea must not have HTML-level `required`; got: {attrs!r}"
    )
