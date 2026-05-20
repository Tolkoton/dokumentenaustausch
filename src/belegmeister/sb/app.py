"""LOCAL Steuerberater-facing FastAPI app for creating document-requests.

A SEPARATE FastAPI `app` object from `belegmeister.web.app` (the public,
client-facing `/r/*` handler) — so a public deploy of the web app can
never expose `/sb/*`. This app is meant to run on each SB's machine over
localhost only (no auth: not network-reachable; desktop-app security
profile). Entry point: `uvicorn belegmeister.sb.app:app --port 8731`.

Routes:
- ``GET  /sb``        — render the request-creation form
- ``POST /sb/create`` — resolve VGM number → GUID, validate input, call
  the shared 4a core (`run_create_request`), render the magic link as
  copyable text. NO email send (the SB copies the link by hand, as the
  CLI does today).

The POST handler reuses the SAME core the CLI calls
(`belegmeister.cli.create_request.run_create_request` /
`CreateRequestArgs`) — no parallel request-creation logic. Deps
(klardaten client / secret / base URL / now) are FastAPI dependencies so
the routes are testable via `dependency_overrides` without env or real
DATEV (same humble-object pattern as `belegmeister.web.app`).

This module does NOT:
- bind a port / check 8731 / open a browser / package as an .exe — that
  launcher is its own slice (4c); 4b is run via `uvicorn` by hand
- send email or otherwise notify the client (later slice; v1 SMTP)
- add authentication (none — localhost only)
- change the client-facing `/r/{token}` page (still the Slice-3 layout)
- handle the client's submit / `beantwortete_fragen` (future slice)
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx
import jinja2
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from belegmeister.cli.create_request import (
    MAX_TTL_DAYS,
    CreateRequestArgs,
    UploadFailed,
    run_create_request,
)
from belegmeister.datev.resolver import resolve_binder_guid_by_number
from belegmeister.datev.upload import InvalidUploadTarget
from belegmeister.env_validation import (
    validate_base_url,
    validate_required,
    validate_secret,
)
from belegmeister.klardaten.client import KlardatenClient
from belegmeister.validation_errors import validation_error_items

# Same .env bootstrap rationale as web/app.py: under uvicorn the
# env-reading deps would KeyError mid-request without this (the Slice-3
# load_dotenv-gap smoke finding). Unit tests override the deps.
load_dotenv()

logger = logging.getLogger("belegmeister.sb")

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
# Unconditional autoescape (NOT select_autoescape) — XSS protection must
# not hinge on a template's file extension. The SB's own input is echoed
# back into `value="..."` / `<textarea>` on a validation re-render, so
# escaping here is load-bearing, not cosmetic.
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(_TEMPLATES_DIR),
    autoescape=True,
)
templates = Jinja2Templates(env=_jinja_env)


class FormValidationError(Exception):
    """The submission is invalid at the FORM-SHAPE stage — before the
    resolver or core is ever touched (e.g. the VGM-Nummer is not a
    number). Carries a per-field message map (`field -> message`); the
    handler re-renders the form with it.

    Deliberately distinct from `VgmNotResolved`: "not a number" is the
    SB mistyping a field (same class as a blank subject), whereas
    `VgmNotResolved` is a *resolve-stage* outcome (a syntactically valid
    number DATEV does not know). Merging them would conflate "fix your
    input" with "that case doesn't exist". The `field_errors` shape is
    the structure B6-B12 re-render through.
    """

    def __init__(self, field_errors: dict[str, str]) -> None:
        self.field_errors = field_errors
        super().__init__(f"form invalid: {sorted(field_errors)}")


class VgmNotResolved(Exception):
    """The entered VGM number is syntactically valid but could not be
    turned into a binder GUID (DATEV does not know that number).

    Message embeds the entered value + reason so a single log line is
    self-describing — same pattern as `InvalidUploadTarget` /
    `UploadFailed`. NOT used for "not a number" — that is a
    `FormValidationError` (a different, earlier stage).
    """

    def __init__(self, *, entered: str, reason: str) -> None:
        self.entered = entered
        self.reason = reason
        super().__init__(f"VGM number {entered!r} not resolved: {reason}")


@dataclass(frozen=True)
class _FormInput:
    """The raw form submission, kept verbatim so a validation re-render
    can put every value back where the SB typed it (no retyping a
    multi-paragraph body over one small error)."""

    vgm_number: str
    to: str
    cc: str
    subject: str
    body: str
    questions: list[str] = field(default_factory=list)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Fail fast at startup — mirror of `web.app` C1. A missing/invalid
    env var must stop the SB app coming up, not surface as a mid-request
    500. Same shared `env_validation` helpers; `ValueError ->
    RuntimeError` so uvicorn aborts the boot.

    `MAGIC_LINK_BASE_URL` here points at the PUBLIC client handler (the
    `/r/{token}` deploy) — the SB app composes links the client opens
    elsewhere; it does not serve them itself.
    """
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


def get_klardaten_client() -> KlardatenClient:
    """Real KlardatenClient from env (satisfies both the resolver's
    document-lister shape and the upload `BinderClient` shape).
    Overridden in tests."""
    return KlardatenClient(
        base_url=os.environ.get("KLARDATEN_BASE_URL", "https://api.klardaten.com"),
        api_key=os.environ["KLARDATEN_API_KEY"],
        instance_id=os.environ["KLARDATEN_INSTANCE_ID"],
        profile_id=os.environ.get("KLARDATEN_PROFILE_ID") or None,
    )


def get_secret() -> str:
    """MAGIC_LINK_SECRET from env. Overridden in tests."""
    return os.environ["MAGIC_LINK_SECRET"]


def get_base_url() -> str:
    """MAGIC_LINK_BASE_URL (the PUBLIC client handler). Overridden in tests."""
    return os.environ["MAGIC_LINK_BASE_URL"]


def get_now() -> datetime:
    """Injectable wall-clock so token expiry is deterministic in tests."""
    return datetime.now(timezone.utc)


# TTL is fixed at the policy cap (same as the CLI's default). A
# longer-lived link is a MAX_TTL_DAYS policy change + an exposure
# conversation, not an SB form field.
_TTL = timedelta(days=MAX_TTL_DAYS)


_EMPTY_FORM = _FormInput(vgm_number="", to="", cc="", subject="", body="", questions=[])


# The 4a `_clean_questions` validator embeds a 0-based index in its
# message ("question 0 must not be blank", ...). We read that index to
# co-locate the error at the offending row — a cross-layer read of the
# 4a message-as-contract (pinned by B8; same discipline as Slice-3's
# literal pinning). 0-based is the 4a `enumerate` default, NOT a choice
# we make here.
_QUESTION_INDEX_RE = re.compile(r"\bquestion (\d+)\b")


def _split_errors(
    exc: ValidationError,
) -> tuple[dict[str, str], dict[int, str]]:
    """Map a `CreateRequestArgs` ValidationError onto the form, via the
    SHARED `validation_error_items` (one source of truth with the CLI —
    CLAUDE.md). Returns (scalar_field_errors, question_errors):

    - scalar: top-level loc segment (`subject`, `to`, ...) -> message.
      One slot per field in the template; if a field ever raised more
      than once the last wins — that is a *template* constraint, NOT a
      promised contract (the 4a validators happen to raise at most one
      per field today; do not rely on it).
    - questions: `("questions",)` loc with the 0-based index in the 4a
      message -> `{index: message}`, so the error renders AT that row
      instead of flattening into one useless top-of-form line. The 4a
      validator short-circuits at the first bad question, so today this
      map holds one entry; the shape supports more if 4a ever collects."""
    field_errors: dict[str, str] = {}
    question_errors: dict[int, str] = {}
    for loc, msg in validation_error_items(exc):
        field = loc.split(".")[0]
        if field == "questions" and (m := _QUESTION_INDEX_RE.search(msg)):
            question_errors[int(m.group(1))] = msg
        else:
            field_errors[field] = msg
    return field_errors, question_errors


def _render_form(
    request: Request,
    form: _FormInput,
    *,
    field_errors: dict[str, str] | None = None,
    question_errors: dict[int, str] | None = None,
    banner: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render the creation form. ONE source of truth for the form's
    template context — GET (empty) and every POST/exception re-render
    (preserved values + per-field messages / banner) go through here, so
    the surfaces cannot drift. INVARIANT: a friendly re-render is always
    HTTP 200 — an HTML form app redisplays itself on bad input, it does
    not 4xx the page. `status_code` is explicit (not left to default)
    because the RequestValidationError handler would otherwise inherit
    FastAPI's 422; B5-B13 and B14 must all be 200, uniformly."""
    return templates.TemplateResponse(
        request,
        "form.html",
        {
            "form": form,
            "questions": form.questions,
            "field_errors": field_errors or {},
            "question_errors": question_errors or {},
            "banner": banner,
        },
        status_code=status_code,
    )


def _render_result(request: Request, link: str) -> HTMLResponse:
    """Render the success page: the magic link as copyable text. No
    email send — the SB copies it by hand (same as the CLI today)."""
    return templates.TemplateResponse(request, "result.html", {"link": link})


def _collect_form_input(
    *,
    vgm_number: str,
    to: str,
    cc: str,
    subject: str,
    body: str,
    questions: list[str],
) -> _FormInput:
    """Capture the submission VERBATIM. Empty question rows the SB added
    themselves are kept as-is — they added them, they should see them on
    a re-render. Rejecting/stripping blank questions is the job of
    `CreateRequestArgs._clean_questions` at submit, NOT of the form
    round-trip. (Explicit decision, not incidental.)"""
    return _FormInput(
        vgm_number=vgm_number,
        to=to,
        cc=cc,
        subject=subject,
        body=body,
        questions=list(questions),
    )


def _datev_resolve_banner(exc: httpx.HTTPError) -> str:
    """Classify a resolve-stage httpx failure into a CURATED banner.

    `httpx.HTTPError` is the base of both `RequestError` (down/timeout)
    and `HTTPStatusError` (4xx AND 5xx — `raise_for_status`). The spec's
    "nicht erreichbar / retry" wording is honest only for transient
    failures. A 4xx (esp. 401/403) is a credentials/configuration
    problem the SB cannot fix by retrying — it gets a distinct,
    non-retry-implying message. 5xx / RequestError / other (e.g.
    `DecodingError`) fall into the transient bucket."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if 400 <= code < 500:
            return (
                f"DATEV-Zugriff fehlgeschlagen (HTTP {code}). Bitte "
                f"Zugangsdaten und Konfiguration prüfen."
            )
    return (
        "DATEV ist derzeit nicht erreichbar oder antwortet fehlerhaft. "
        "Bitte versuchen Sie es später erneut."
    )


def _parse_vgm_number(entered: str) -> int:
    """Form-shape stage: the entered VGM-Nummer must be a plain integer
    (DATEV Dokumentnummern are positive ints). One responsibility:
    string -> int, or a field-keyed `FormValidationError`. No network."""
    stripped = entered.strip()
    if not stripped.isdigit():
        raise FormValidationError(
            {"vgm_number": "VGM-Nummer muss eine Zahl sein (Dokumentnummer aus DATEV)."}
        )
    return int(stripped)


def _resolve_vgm_guid(number: int, client: KlardatenClient) -> str:
    """Resolve stage: turn a syntactically valid Dokumentnummer into a
    binder GUID. One responsibility: int -> GUID, or a self-describing
    `VgmNotResolved` (number DATEV does not know)."""
    guid = resolve_binder_guid_by_number(client, number)
    if guid is None:
        # mypy narrows str|None here; this branch's behaviour (unknown
        # number -> friendly re-render) is pinned by B6.
        raise VgmNotResolved(entered=str(number), reason="not found in DATEV")
    return guid


async def _salvage_form_input(request: Request) -> _FormInput:
    """Best-effort reconstruction of what the SB typed, from the partial
    request body, so a pre-handler RequestValidationError re-render does
    NOT wipe the form (the smoke showed _EMPTY_FORM's cost — B5-B13 all
    preserve; B14 must not be the lone exception). The body is still
    available here (FastAPI already parsed it to attempt validation, so
    `request.form()` returns the cached FormData). Any failure (non-form
    body, body consumed) falls back to the empty form — a degraded but
    still-friendly re-render, never a raw error."""
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001 - degrade to empty, never 500 here
        return _EMPTY_FORM

    def one(name: str) -> str:
        v = form.get(name, "")
        return v if isinstance(v, str) else ""

    questions = [q for q in form.getlist("questions") if isinstance(q, str)]
    return _FormInput(
        vgm_number=one("vgm_number"),
        to=one("to"),
        cc=one("cc"),
        subject=one("subject"),
        body=one("body"),
        questions=questions,
    )


@app.exception_handler(RequestValidationError)
async def _on_request_validation_error(
    request: Request, _exc: RequestValidationError
) -> HTMLResponse:
    """Pre-handler safety net. FastAPI validates the `Form(...)` params
    BEFORE `create_request_page`'s body runs, so a bare/incomplete POST
    raises `RequestValidationError` and never reaches the B5-B13
    try/except — by default that surfaces as raw 422 JSON. Re-render the
    form with the submitted values SALVAGED (B14 must preserve like
    B5-B13 — revised after the smoke showed the no-salvage cost) plus a
    banner, at HTTP 200 (the friendly-re-render invariant; without an
    explicit status this would inherit FastAPI's 422). Only POST
    /sb/create has body validation; GET /sb has no params, so this is
    effectively scoped to that endpoint."""
    logger.warning("sb_request_validation_error path=%s", request.url.path)
    return _render_form(
        request,
        await _salvage_form_input(request),
        banner=(
            "Das Formular wurde unvollständig übermittelt. Bitte füllen "
            "Sie alle Pflichtfelder aus und senden Sie es erneut."
        ),
        status_code=200,
    )


@app.get("/sb", response_class=HTMLResponse)
def form_page(request: Request) -> HTMLResponse:
    """Render the empty request-creation form (GET ``/sb``).

    First-touch route: every field is empty, no banners, HTTP 200.
    All re-render branches in ``create_request_page`` share the same
    template through ``_render_form`` so GET and re-render cannot
    diverge in shape.

    Args:
        request: FastAPI request, used by Jinja2's template-response
            machinery to expose ``request`` to the template.

    Returns:
        An HTML 200 response carrying the freshly-rendered ``form.html``.
    """
    return _render_form(request, _EMPTY_FORM)


@app.get("/sb/create")
def create_get_redirect() -> RedirectResponse:
    """A GET on the POST-only action URL (navigated / refreshed /
    bookmarked) bounces to the form instead of a raw 405 JSON.
    Conscious tradeoff: /sb/create is now GET-redirect + POST-handle,
    not POST-only — chosen for SB-friendliness on a localhost tool."""
    return RedirectResponse(url="/sb", status_code=303)


@app.post("/sb/create", response_class=HTMLResponse)
def create_request_page(
    request: Request,
    vgm_number: str = Form(...),
    to: str = Form(...),
    cc: str = Form(""),
    subject: str = Form(...),
    body: str = Form(...),
    questions: list[str] = Form(default=[]),
    client: KlardatenClient = Depends(get_klardaten_client),
    secret: str = Depends(get_secret),
    base_url: str = Depends(get_base_url),
    now: datetime = Depends(get_now),
) -> HTMLResponse:
    """Handle ``POST /sb/create``: validate, resolve, run the 4a core, render.

    Stage-by-stage flow, each with its own re-render branch (the B5–B12
    behavior labels in ``tests/sb/``):

    1. **Collect** the submission verbatim via ``_collect_form_input``
       so re-renders preserve the SB's typing.
    2. **Form-shape** parse: ``_parse_vgm_number`` rejects non-digit
       VGM-Nummer with a ``FormValidationError`` (B5).
    3. **Resolve** via ``resolve_binder_guid_by_number`` (klardaten
       ``GET /documents`` pagination — see ADR-0001 for why this is
       slow). ``VgmNotResolved`` (B6) and ``httpx.HTTPError``
       (B11/B12, classified by ``_datev_resolve_banner``) get curated
       banners. Note: a 4xx (auth/config) is shown as a NON-retry
       message because retrying will not fix it.
    4. **Validate** ``CreateRequestArgs`` against the resolved GUID
       and the form's text fields, with the shared ``now`` in
       validation context. Field-mapped errors render at their field
       (``_split_errors`` routes the ``questions`` indices to the
       offending row).
    5. **Core**: ``run_create_request`` performs the klardaten attach
       and returns the magic-link URL. ``InvalidUploadTarget`` and
       ``UploadFailed`` (B9/B10) render distinct banners; an
       ``OSError`` from the local tempfile path renders the
       "Dateisystemfehler" banner (the only place ``OSError`` can
       originate inside the core is the temp-file write).
    6. **Render result**: ``_render_result`` shows the magic link as
       copyable text — no email send; the SB copies the link by hand.

    Args:
        request: FastAPI request, threaded to the Jinja2 template
            response.
        vgm_number: Raw form field ``vgm_number`` (string, not yet
            parsed). The Dokumentnummer the SB typed.
        to: Recipient email form field.
        cc: Optional Cc form field (defaults to empty).
        subject: Subject line form field.
        body: Letter body, verbatim.
        questions: Zero or more question rows (FastAPI binds repeated
            form fields to ``list[str]``). Empty trailing rows ARE
            preserved through re-render — the SB chose to add them.
        client: ``KlardatenClient`` (or test override). Used for both
            resolve and core upload — the same instance, so a
            connection pool can be shared.
        secret: ``MAGIC_LINK_SECRET`` (validated at startup; injected
            here for testability).
        base_url: ``MAGIC_LINK_BASE_URL`` of the PUBLIC client handler
            (the ``/r/<token>`` deploy) — the SB app composes links
            the Mandant opens elsewhere.
        now: Injectable wall-clock; pinned in tests.

    Returns:
        Always an HTML response, always HTTP 200. The happy path
        renders ``result.html`` with the magic link; every failure
        stage re-renders ``form.html`` with the preserved form values
        plus a banner or per-field message. A friendly re-render NEVER
        4xx-es; the page redisplays itself on bad input.

    Side effects:
        Network calls to klardaten via ``client`` during the resolve
        stage (one or more ``GET /documents``) and the core stage (one
        ``GET /documents/{guid}``, then two ``POST``s — see
        ``run_create_request``). Writes a tempfile inside the OS
        tempdir (auto-cleaned by the core). Emits structured ``WARNING``
        log lines via ``belegmeister.sb`` for every failure branch (no
        secrets, no token, no full URL).
    """
    form = _collect_form_input(
        vgm_number=vgm_number,
        to=to,
        cc=cc,
        subject=subject,
        body=body,
        questions=questions,
    )
    try:
        number = _parse_vgm_number(form.vgm_number)
        guid = _resolve_vgm_guid(number, client)
    except FormValidationError as exc:
        return _render_form(request, form, field_errors=exc.field_errors)
    except VgmNotResolved:
        # Resolve stage: a valid number DATEV does not know. Same field
        # ("vgm_number") as B5 but a distinct message — the SB should
        # check the number, not its format.
        return _render_form(
            request,
            form,
            field_errors={
                "vgm_number": (
                    f"VGM-Nummer {form.vgm_number.strip()} "
                    f"wurde in DATEV nicht gefunden."
                )
            },
        )
    except httpx.HTTPError as exc:
        # Resolve-stage transport/HTTP failure (DATEV listing). Detail to
        # the server log; the SB sees a CLASSIFIED banner so they take
        # the right action: a 4xx (esp. 401/403) is a credentials/config
        # problem — telling them to "retry" would misdirect — whereas
        # down/timeout/5xx is genuinely transient.
        logger.warning("sb_resolve_datev_error detail=%r", exc)
        return _render_form(request, form, banner=_datev_resolve_banner(exc))
    try:
        args = CreateRequestArgs.model_validate(
            {
                "vgm_id": guid,
                "to": form.to,
                "cc": form.cc,
                "subject": form.subject,
                "body": form.body,
                "questions": form.questions,
                "expires_at": now + _TTL,
            },
            context={"now": now},
        )
    except ValidationError as exc:
        field_errors, question_errors = _split_errors(exc)
        return _render_form(
            request,
            form,
            field_errors=field_errors,
            question_errors=question_errors,
        )
    try:
        link = run_create_request(
            args,
            klardaten_client=client,
            magic_link_secret=secret,
            magic_link_base_url=base_url,
            now=now,
        )
    except InvalidUploadTarget as exc:
        # The named exception already carries target id + reason — log it
        # in full server-side (self-describing, no traceback dive); show
        # the SB a CURATED line, never str(exc)/internals.
        logger.warning("sb_upload_rejected detail=%s", exc)
        return _render_form(
            request,
            form,
            banner=(
                f"VGM {form.vgm_number.strip()} ist keine gültige "
                f"Vorgangsmappe. Bitte prüfen Sie die VGM-Nummer."
            ),
        )
    except UploadFailed as exc:
        logger.warning("sb_upload_failed detail=%s", exc)
        return _render_form(
            request,
            form,
            banner=(
                f"Der Anforderungsbrief konnte nicht in VGM "
                f"{form.vgm_number.strip()} hochgeladen werden. "
                f"Bitte versuchen Sie es erneut."
            ),
        )
    except OSError as exc:
        # Local-FS failure INSIDE run_create_request (temp-dir create /
        # write_text / read-back). Re-read of the core confirms OSError
        # there can ONLY be the local temp file — network is httpx,
        # serialize/token are pure — so a broad `except OSError` is
        # precise. NOT B9 (upload stage) and NOT a programmer bug: it
        # means the SB's machine couldn't write the temp file.
        logger.warning("sb_local_file_error detail=%r", exc)
        return _render_form(
            request,
            form,
            banner=(
                "Der Anforderungsbrief konnte lokal nicht erstellt "
                "werden (Dateisystemfehler). Bitte Speicherplatz und "
                "Schreibrechte des temporären Verzeichnisses prüfen."
            ),
        )
    return _render_result(request, link)
