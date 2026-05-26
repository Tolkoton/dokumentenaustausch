"""FastAPI glue for the client magic-link page.

Humble object: wires `resolve_request_view` to GET /r/{token}, renders
the Jinja2 template on success, maps `RequestLinkInvalid` → 404 generic
page + a structured server-side log line (grep-able log_reason +
context, NEVER the token).

Deps (letter source / secret / now) are FastAPI dependencies so the
route is testable via dependency_overrides without env or real DATEV.

`GET /r/{token}` only. `POST /r/{token}/submit` is the next slice — the
form posts there and a click 404s until then (intentional).
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import jinja2
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from belegmeister.env_validation import (
    validate_base_url,
    validate_required,
    validate_secret,
)
from belegmeister.klardaten.client import KlardatenClient
from belegmeister.logging_setup import configure_logging
from belegmeister.web.request_view import (
    LetterSource,
    RequestLinkInvalid,
    resolve_request_view,
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

    Args:
        token: The signed magic-link token from the URL path. Treated
            as opaque; never logged or echoed.
        request: FastAPI request, for the Jinja2 response.
        letter_source: A ``LetterSource``-shaped object — in production
            a ``KlardatenClient``; in tests a fake. Used for both
            ``list_structure_items`` and ``download_document_file``.
        secret: ``MAGIC_LINK_SECRET``, validated at startup.
        now: Injectable wall-clock for expiry checks.

    Returns:
        Either:

        * ``request.html`` at HTTP 200 with ``{"token": token,
          "subject": ..., "body": ..., "questions": ...}`` on the
          happy path — narrowed context at the route boundary;
          ``letter.to`` and ``letter.cc`` are deliberately NEVER
          passed to the Jinja2 namespace (Decision D-S8 — privacy +
          XSS-surface reduction by construction), OR
        * ``invalid.html`` at HTTP 404 on any failure
          (``RequestLinkInvalid``). The client-facing message is the
          same regardless of which stage failed.

    Side effects:
        Reads from klardaten via ``letter_source`` (two calls on the
        happy path: list children, then download bytes). Emits one
        ``WARNING`` log line on rejection with ``log_reason`` and
        ``log_context`` from ``RequestLinkInvalid`` — never the token.
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
    # enter the template namespace. This is privacy-by-construction
    # (Cc would disclose internal recipients to the Mandant; To is
    # redundant with the Mandant's own address) AND XSS-surface-reduction-
    # by-construction (the template cannot accidentally render what was
    # never passed). RequestView still carries to/cc for the future
    # email-slice's SMTP needs.
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
