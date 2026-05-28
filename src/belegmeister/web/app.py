"""FastAPI glue for the client magic-link page.

Humble object: wires `resolve_request_view` to GET /r/{token}, renders
the Jinja2 template on success, maps `RequestLinkInvalid` → 404 generic
page + a structured server-side log line (grep-able log_reason +
context, NEVER the token).

POST /r/{token}/submit is the submit-handler slice. UNIT 2 wires the
handler skeleton with token verify + D7 empty-submit predicate + D2
in-binder replay check + D6 four-branch dispatcher (with stubbed file-
upload loop — UNIT 3 ships the real loop). UNIT 2's sentinel framing:
"branching dispatcher correct against mocked-inventory inputs; loop
stubbed for UNIT 3" — NOT "handler complete".

Deps (letter source / secret / now / upload_orchestrator) are FastAPI
dependencies so the route is testable via dependency_overrides without
env or real DATEV.
"""

from __future__ import annotations

import logging
import os
import time
import uuid as uuid_lib
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
import jinja2
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.datastructures import UploadFile

from belegmeister.env_validation import (
    validate_base_url,
    validate_required,
    validate_secret,
)
from belegmeister.klardaten.client import KlardatenClient
from belegmeister.logging_setup import configure_logging
from belegmeister.magic_link.token import InvalidToken, verify_token
from belegmeister.web.request_view import (
    LetterSource,
    RequestLinkInvalid,
    resolve_request_view,
)
from belegmeister.web.response_format import (
    AttachmentOutcome,
    ResponseDocument,
    ResponseLetterMalformed,
    failure_reason_from_klardaten_outcome,
    serialize_response_letter,
)

# Same bootstrap as the CLI / smoke scripts. Without this, uvicorn runs
# with no .env and the env-reading dependencies KeyError mid-request
# (500, before the route's try/except) instead of serving. Found by the
# Slice-3 smoke — unit tests override the deps so they never hit env.
load_dotenv()

# Configure root logging at module import so `uvicorn belegmeister.web.app:app`
# triggers it directly — not only the `python -m belegmeister` CLI path.
# Idempotent: a no-op when logging is already configured (e.g. pytest caplog).
configure_logging()

logger = logging.getLogger("belegmeister.web")

_TEMPLATES_DIR = Path(__file__).parent / "templates"
# Unconditional autoescape (NOT select_autoescape): XSS protection must
# not depend on a template's file extension. If someone renames
# request.html → request.j2, escaping still applies.
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
)
templates = Jinja2Templates(env=_jinja_env)

# Banner-state values rendered into submit_confirmation.html. Three
# discrete states — kept as a Literal alias so mypy strict catches
# typos at call sites.
BannerState = Literal["full_success", "partial_success", "already_submitted"]

# RequestSubmitFailed log_reasons per ADR-0007 / slice contract D4.
# Five mutually distinguishable signals; the handler catches
# RequestSubmitFailed and dispatches per `.log_reason`.
SubmitFailReason = Literal[
    "upload_failed_all_files",
    "upload_failed_response_doc",
    "replay_rejected",
    "empty_submit",
    "multipart_parse_error",
]


class RequestSubmitFailed(Exception):
    """Client submission attempt failed. Distinct from GET-side
    `RequestLinkInvalid` (which means "the link itself is broken or
    unauthorized"). POST-side recovery differs: typically "retry with
    same link" or — on `replay_rejected` — a friendly "you already
    submitted" page (NOT an error).

    See ADR-0007 + slice contract D4 for the five-value taxonomy and
    the operational meaning of each `log_reason`.
    """

    def __init__(
        self, *, log_reason: SubmitFailReason, log_context: dict[str, Any] | None = None
    ) -> None:
        super().__init__(log_reason)
        self.log_reason: SubmitFailReason = log_reason
        self.log_context: dict[str, Any] = log_context or {}


@dataclass(frozen=True)
class SubmitDispatch:
    """Output of D6 four-branch dispatcher.

    Either ``commit_response_doc=True`` with one of the success
    `banner_state` values, OR ``commit_response_doc=False`` with
    ``bailout_log_reason="upload_failed_all_files"``. The handler
    branches on `bailout_log_reason is not None` to decide raise-vs-commit.
    """

    commit_response_doc: bool
    banner_state: Literal["full_success", "partial_success"] | None
    bailout_log_reason: Literal["upload_failed_all_files"] | None


def dispatch_submit_outcome(
    inventory: tuple[AttachmentOutcome, ...],
) -> SubmitDispatch:
    """Pure D6 four-branch dispatcher. Maps an upload inventory to a
    commit-or-bailout decision plus banner state.

    Branches (see slice contract D6):
    1. ``files_attempted == 0`` → commit (full_success banner, empty ATTACHMENTS).
    2. ``files_attempted > 0 AND files_succeeded == 0`` → bailout (no commit, no burn).
    3. ``0 < files_succeeded < files_attempted`` → commit (partial_success banner).
    4. ``files_succeeded == files_attempted`` → commit (full_success banner).

    Branch order matters: check (2) before (4) since both can match when
    ``files_attempted == 0`` (the answers-only case must hit (1), not (4)).
    """
    files_attempted = len(inventory)
    files_succeeded = sum(1 for a in inventory if a.status == "succeeded")
    if files_attempted == 0:
        # Branch 1: answers-only / Anmerkungen-only. files_succeeded == 0
        # too, but we route by attempted-vs-succeeded shape not by raw
        # counts — empty inventory is success, not bailout.
        return SubmitDispatch(
            commit_response_doc=True,
            banner_state="full_success",
            bailout_log_reason=None,
        )
    if files_succeeded == 0:
        # Branch 2: bailout. Mandant attached files and ALL failed.
        # No response doc; token not burned; Mandant can retry.
        return SubmitDispatch(
            commit_response_doc=False,
            banner_state=None,
            bailout_log_reason="upload_failed_all_files",
        )
    if files_succeeded == files_attempted:
        # Branch 4: clean full success.
        return SubmitDispatch(
            commit_response_doc=True,
            banner_state="full_success",
            bailout_log_reason=None,
        )
    # Branch 3: partial (0 < files_succeeded < files_attempted).
    return SubmitDispatch(
        commit_response_doc=True,
        banner_state="partial_success",
        bailout_log_reason=None,
    )


def is_empty_submit(*, answers: list[str], anmerkungen: str, file_count: int) -> bool:
    """D7 server-side predicate (tightened 2026-05-27 — pre-existing
    UX defect fix, NOT a slice contract revision; the slice's history
    in `.claude/overseer/slice/submit-handler.md` is preserved unchanged).

    True iff the submission is incomplete — i.e. at least one of the
    request letter's questions has an empty answer (after whitespace
    strip). Files and Anmerkungen are OPTIONAL supplements and do NOT
    affect this check.

    Rule:
      - ALL entries in ``answers`` (one per request-letter question)
        must be non-empty AFTER ``.strip()``. Whitespace-only counts
        as empty (otherwise a Mandant pasting `" "` would slip past
        the template's HTML5 ``required`` attribute at the server).
      - ``file_count`` and ``anmerkungen`` are ignored — they are
        optional supplements per the revised product semantic.
      - Zero questions (``answers == []``) is vacuously not-empty —
        the SB intentionally created a letter without questions, so
        any submit reaches the codec without an answer requirement.

    Was: "≥1 file OR ≥1 non-empty answer OR non-empty Anmerkungen ⇒
    accept" — allowed edge case "Mandant submits Anmerkungen only,
    no answers to actual questions" which is product-wrong for
    Beleganforderung (the SB asked specific questions; they need
    those specific answers, supplements are nice-to-have).

    The template's ``required`` attribute on each answer ``<input>``
    is the realistic-case JS-enforcement; this predicate is the
    correctness backstop (disabled JS, scripted bypass, etc.).
    """
    del file_count, anmerkungen  # optional supplements per the new semantic
    return any(not a.strip() for a in answers)


# Upload orchestrator dependency. Production default
# (`_real_upload_orchestrator`) implements the D6 + D8 continue-past-
# failures sequential loop. Tests can still override the dependency
# (e.g. the S1 branching matrix injects controllable inventory).
UploadOrchestrator = Callable[
    [list[UploadFile], str, str, LetterSource],
    tuple[AttachmentOutcome, ...],
]


def _real_upload_orchestrator(
    files: list[UploadFile],
    letter_id: str,
    vgm_id: str,
    letter_source: LetterSource,
) -> tuple[AttachmentOutcome, ...]:
    """Continue-past-failures sequential file-upload loop per ADR-0007
    + slice contract D6 / D8.

    For each Mandant-supplied file:
      1. Generate D3 stored filename
         ``_attachment_<letter_id>_<8-char-uuid>_<original>``. UUID
         prevents collision when Mandant uploads the same original
         name twice (S6 seam).
      2. Read the file bytes (sync via the underlying
         ``SpooledTemporaryFile`` — works inside the async handler).
      3. Call ``attach_file_to_binder``; on success record the
         klardaten-returned ``id`` + ``document_file_id``.
      4. On ANY exception (httpx error, EOF, encoding issue, …),
         record a failed ``AttachmentOutcome`` with
         ``failure_reason`` from
         ``failure_reason_from_klardaten_outcome``. **Continue to
         the next file** — never abort the loop. Bailout (all-failed
         case) is the dispatcher's call, not the loop's.

    Excludes ``BaseException`` (keep ``KeyboardInterrupt`` /
    ``SystemExit`` escapable). Inside ``Exception`` catch-all so
    nothing surprises bubbles out as a 500 mid-loop.
    """
    outcomes: list[AttachmentOutcome] = []
    for upload in files:
        original = upload.filename or ""
        uuid_suffix = uuid_lib.uuid4().hex[:8]
        stored = f"_attachment_{letter_id}_{uuid_suffix}_{original}"
        started = time.monotonic()
        try:
            file_bytes = upload.file.read()
            result = letter_source.attach_file_to_binder(
                binder_guid=vgm_id, file_name=stored, file_bytes=file_bytes
            )
        except Exception as exc:  # noqa: BLE001 — broad-by-design; per ADR-0007
            elapsed = time.monotonic() - started
            outcomes.append(
                AttachmentOutcome(
                    original_filename=original,
                    stored_filename=None,
                    structure_item_id=None,
                    document_file_id=None,
                    status="failed",
                    failure_reason=failure_reason_from_klardaten_outcome(exc),
                    elapsed_s=round(elapsed, 3),
                )
            )
            continue
        elapsed = time.monotonic() - started
        sid_raw = result.get("id")
        dfid_raw = result.get("document_file_id")
        outcomes.append(
            AttachmentOutcome(
                original_filename=original,
                stored_filename=stored,
                structure_item_id=str(sid_raw) if sid_raw is not None else None,
                document_file_id=int(dfid_raw) if isinstance(dfid_raw, int) else None,
                status="succeeded",
                failure_reason=None,
                elapsed_s=round(elapsed, 3),
            )
        )
    return tuple(outcomes)


def get_upload_orchestrator() -> UploadOrchestrator:
    """DI seam for the upload orchestrator. Production returns the
    real continue-past-failures loop; tests can override (e.g. the
    S1 branching matrix injects controllable inventory)."""
    return _real_upload_orchestrator


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Fail fast at startup: a missing/invalid env var must stop the
    server coming up, not surface as a mid-request 500. Same checks the
    CLI runs (shared `env_validation` helpers); ValueError → RuntimeError
    so uvicorn aborts the boot."""
    try:
        validate_secret(
            validate_required("MAGIC_LINK_SECRET", os.environ.get("MAGIC_LINK_SECRET"))
        )
        validate_base_url(
            validate_required(
                "MAGIC_LINK_BASE_URL", os.environ.get("MAGIC_LINK_BASE_URL")
            )
        )
        validate_required("KLARDATEN_API_KEY", os.environ.get("KLARDATEN_API_KEY"))
        validate_required(
            "KLARDATEN_INSTANCE_ID", os.environ.get("KLARDATEN_INSTANCE_ID")
        )
    except ValueError as exc:
        raise RuntimeError(f"Environment validation failed: {exc}") from exc
    yield


app = FastAPI(lifespan=lifespan)


def get_letter_source() -> LetterSource:
    """Real KlardatenClient from env. Overridden in tests."""
    return KlardatenClient(
        base_url=os.environ.get("KLARDATEN_BASE_URL", "https://api.klardaten.com"),
        api_key=os.environ["KLARDATEN_API_KEY"],
        instance_id=os.environ["KLARDATEN_INSTANCE_ID"],
        profile_id=os.environ.get("KLARDATEN_PROFILE_ID") or None,
    )


def get_secret() -> str:
    """MAGIC_LINK_SECRET from env. Overridden in tests."""
    return os.environ["MAGIC_LINK_SECRET"]


def get_now() -> datetime:
    """Injectable wall-clock so token expiry is deterministic in tests."""
    return datetime.now(timezone.utc)


def _is_already_submitted(
    letter_source: LetterSource, *, vgm_id: str, letter_id: str
) -> bool:
    """D2 in-binder replay check. True iff a ``_response_<letter_id>_*``
    structure-item already exists in the VGM.

    Per ADR-0006, this is defense-in-depth (the JS lockSubmit handles
    same-tab double-click; this catches deliberate replay / refresh /
    captured-token resend). TOCTOU window is accepted residual risk.

    HTTP errors during the check propagate to the caller (handler
    catches via the same `RequestLinkInvalid` path as GET-side: a
    transient klardaten outage during a POST is operationally
    indistinguishable from one during a GET).
    """
    children = letter_source.list_structure_items(vgm_id)
    response_prefix = f"_response_{letter_id}_"
    return any(
        isinstance(c.get("name"), str) and c["name"].startswith(response_prefix)
        for c in children
    )


def _response_filename(letter_id: str, submitted_at: datetime) -> str:
    """Build the canonical ``_response_<letter_id>_<ISO>.txt`` filename
    per slice contract D3. ISO format uses ``%Y%m%dT%H%M%SZ`` (compact
    Z-suffix) to mirror the existing ``_request_letter_<ISO>.txt``
    convention from 4a/vgm_files."""
    iso = submitted_at.strftime("%Y%m%dT%H%M%SZ")
    return f"_response_{letter_id}_{iso}.txt"


def _extract_answers(form: dict[str, Any], n_questions: int) -> list[str]:
    """Pull ``answer_0``, ``answer_1``, ... from a multipart form into
    a positional list, padding missing fields with empty strings.

    The form template (`request.html`) emits one input per question
    with `name="answer_{i}"`; the handler reconstructs positional
    list-of-answers from these. Missing fields are treated as empty
    (Mandant deleted the input client-side or browser quirk)."""
    answers: list[str] = []
    for i in range(n_questions):
        value = form.get(f"answer_{i}", "")
        answers.append(value if isinstance(value, str) else "")
    return answers


@app.get("/r/{token}", response_class=HTMLResponse)
def request_page(
    token: str,
    request: Request,
    letter_source: LetterSource = Depends(get_letter_source),
    secret: str = Depends(get_secret),
    now: datetime = Depends(get_now),
) -> HTMLResponse:
    """Handle ``GET /r/{token}``: render the Mandant's request letter.

    Humble wiring around ``resolve_request_view``: verify the HMAC
    token, fetch the newest ``_request_letter_*.txt`` from inside the
    bound VGM via klardaten's ``GET /documents/{vgm}/structure-items``
    and ``GET /document-files/{id}``, render ``request.html``. Any
    failure becomes the GENERIC ``invalid.html`` page at HTTP 404 — the
    client never sees which step failed (information-disclosure risk;
    see ``docs/SECURITY.md``). The real reason is in the server log
    with a structured ``log_reason`` + ``log_context`` (token never in
    the log line).
    """
    try:
        view = resolve_request_view(
            token, letter_source=letter_source, secret=secret, now=now
        )
    except RequestLinkInvalid as exc:
        # Structured, grep-able, NEVER the token.
        logger.warning(
            "magic_link_rejected reason=%s context=%s",
            exc.log_reason,
            exc.log_context,
        )
        return templates.TemplateResponse(request, "invalid.html", status_code=404)
    # S8 narrow (Decision D-S8): the Jinja2 template context carries
    # ONLY {subject, body, questions} from the parsed letter — `letter.to`
    # and `letter.cc` are filtered out at the route boundary and never
    # enter the template namespace.
    return templates.TemplateResponse(
        request,
        "request.html",
        {
            "token": token,
            "subject": view.letter.subject,
            "body": view.letter.body,
            "questions": view.letter.questions,
        },
    )


@app.post("/r/{token}/submit", response_class=HTMLResponse)
async def submit_post(
    token: str,
    request: Request,
    letter_source: LetterSource = Depends(get_letter_source),
    secret: str = Depends(get_secret),
    now: datetime = Depends(get_now),
    upload_orchestrator: UploadOrchestrator = Depends(get_upload_orchestrator),
) -> HTMLResponse:
    """Handle ``POST /r/{token}/submit``: accept Mandant's answers +
    Anmerkungen + N files; commit a response doc + per-file uploads;
    render the confirmation page.

    Flow (per slice contract D6 / D8):

    1. Verify token (reuse `verify_token`); on failure → 404 generic
       (same disclosure discipline as GET-side).
    2. Replay check (D2 / ADR-0006): if a ``_response_<letter_id>_*``
       exists, render confirmation with `banner=already_submitted`.
    3. Fetch letter (need question text for Q/A pairs); failure →
       404 generic same as GET.
    4. Parse multipart form: pull ``answer_0``, ``answer_1``, ...,
       the ``response`` textarea (Anmerkungen), and ``files`` list.
    5. D7 empty-submit predicate; if all empty → 422 error page.
    6. Invoke `upload_orchestrator` (UNIT 2 stubs this raising; tests
       override with controllable inventory; UNIT 3 ships the real
       continue-past-failures loop).
    7. D6 dispatcher: bailout → 500 error page; commit branches →
       serialize response doc + upload + render confirmation.
    """
    # 1. Token verify. Generic 404 on failure mirrors GET-side.
    try:
        payload = verify_token(token=token, secret=secret, now=now)
    except InvalidToken as exc:
        logger.warning(
            "submit_token_rejected reason=%s",
            exc.reason.value,
        )
        return templates.TemplateResponse(request, "invalid.html", status_code=404)

    # 2. Replay check. Wrap in try so klardaten transport errors here
    # surface as the same generic 404 as a GET-side outage — the
    # Mandant cannot distinguish "VGM gone" from "klardaten down" and
    # the recovery is identical (wait + retry / contact SB).
    try:
        if _is_already_submitted(
            letter_source, vgm_id=payload.vgm_id, letter_id=payload.letter_id
        ):
            logger.info(
                "submit_replay_rejected vgm_id=%s letter_id=%s",
                payload.vgm_id,
                payload.letter_id,
            )
            return _render_confirmation(
                request, banner="already_submitted", n_succeeded=0, n_total=0
            )
    except httpx.HTTPError as exc:
        logger.warning(
            "submit_replay_check_failed vgm_id=%s error=%s",
            payload.vgm_id,
            type(exc).__name__,
        )
        return templates.TemplateResponse(request, "invalid.html", status_code=404)

    # 3. Fetch letter (need question texts for response doc).
    try:
        view = resolve_request_view(
            token, letter_source=letter_source, secret=secret, now=now
        )
    except RequestLinkInvalid as exc:
        logger.warning(
            "submit_letter_fetch_failed reason=%s context=%s",
            exc.log_reason,
            exc.log_context,
        )
        return templates.TemplateResponse(request, "invalid.html", status_code=404)

    # 4. Parse multipart form. ``request.form()`` returns a FormData
    # object; we extract dynamic ``answer_<i>`` fields by position
    # against the parsed letter's question count.
    form = await request.form()
    form_dict = dict(form)
    answers = _extract_answers(form_dict, n_questions=len(view.letter.questions))
    raw_anmerkungen = form_dict.get("response", "")
    anmerkungen = raw_anmerkungen if isinstance(raw_anmerkungen, str) else ""
    # `files` may be absent, a single UploadFile, or a list. Normalize
    # to a list. FastAPI's UploadFile is distinguished by having
    # `.filename` + `.read()`; raw str is not a file.
    files = _collect_upload_files(form)

    # 5. D7 server-side check.
    if is_empty_submit(answers=answers, anmerkungen=anmerkungen, file_count=len(files)):
        logger.info("submit_empty vgm_id=%s", payload.vgm_id)
        return templates.TemplateResponse(request, "submit_error.html", status_code=422)

    # 6. File upload loop (UNIT 2 stub; tests override).
    inventory = upload_orchestrator(
        files, payload.letter_id, payload.vgm_id, letter_source
    )

    # 7. D6 dispatcher.
    outcome = dispatch_submit_outcome(inventory)
    if outcome.bailout_log_reason is not None:
        logger.warning(
            "submit_bailout reason=%s vgm_id=%s files_attempted=%d",
            outcome.bailout_log_reason,
            payload.vgm_id,
            len(inventory),
        )
        return templates.TemplateResponse(request, "submit_error.html", status_code=500)

    # 8. Build + serialize + upload response doc. Q/A pairs zip
    # parsed questions with positional answers.
    qa_pairs = tuple(zip(view.letter.questions, answers, strict=False))
    doc = ResponseDocument(
        letter_id=payload.letter_id,
        submitted_at=now,
        qa_pairs=qa_pairs,
        anmerkungen=anmerkungen,
        attachments=inventory,
    )
    try:
        wire = serialize_response_letter(doc)
    except ResponseLetterMalformed as exc:
        logger.error(
            "submit_response_doc_malformed vgm_id=%s reason=%s",
            payload.vgm_id,
            exc.reason,
        )
        return templates.TemplateResponse(request, "submit_error.html", status_code=500)
    try:
        letter_source.attach_file_to_binder(
            binder_guid=payload.vgm_id,
            file_name=_response_filename(payload.letter_id, now),
            file_bytes=wire.encode("utf-8"),
        )
    except httpx.HTTPError as exc:
        logger.warning(
            "submit_response_doc_upload_failed vgm_id=%s error=%s",
            payload.vgm_id,
            type(exc).__name__,
        )
        return templates.TemplateResponse(request, "submit_error.html", status_code=500)

    # 9. Render confirmation with banner.
    assert outcome.banner_state is not None  # commit branches always have a banner
    n_succeeded = sum(1 for a in inventory if a.status == "succeeded")
    return _render_confirmation(
        request,
        banner=outcome.banner_state,
        n_succeeded=n_succeeded,
        n_total=len(inventory),
    )


def _render_confirmation(
    request: Request,
    *,
    banner: BannerState,
    n_succeeded: int,
    n_total: int,
) -> HTMLResponse:
    """Render the single confirmation template with the appropriate
    banner state. Three states (full_success / partial_success /
    already_submitted) per ADR-0007 + slice contract D5.

    The partial_success banner MUST NOT claim "SB has been notified"
    (A4 confirmed there is no notification channel); the template
    text uses the locked copy from ADR-0007.
    """
    return templates.TemplateResponse(
        request,
        "submit_confirmation.html",
        {
            "banner": banner,
            "n_succeeded": n_succeeded,
            "n_total": n_total,
        },
    )


def _collect_upload_files(form: Any) -> list[UploadFile]:
    """Pull UploadFile instances from a parsed FormData.

    The ``files`` form field can be absent / single / multi. Starlette's
    FormData lets us iterate `getlist("files")`. We filter for
    UploadFile instances and ignore empty-filename uploads (browsers
    emit an empty placeholder when no file is selected — they have
    `filename == ""`).
    """
    raw = form.getlist("files") if hasattr(form, "getlist") else []
    result: list[UploadFile] = []
    for item in raw:
        if isinstance(item, UploadFile) and item.filename:
            result.append(item)
    return result
