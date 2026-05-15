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
    return templates.TemplateResponse(
        request,
        "request.html",
        {"token": token, "letter_text": view.letter_text},
    )
