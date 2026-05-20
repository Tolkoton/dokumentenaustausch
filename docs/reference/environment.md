# Environment variables

All entry points (CLI and the two FastAPI apps) validate environment at
startup via shared helpers in
[`src/belegmeister/env_validation.py`](../../src/belegmeister/env_validation.py).
Missing or malformed values fail fast with a user-facing `error: …` message;
they do not surface as tracebacks.

`.env` is read by `python-dotenv` in dev. The file is hard-denied for editing
by the autonomy hooks — keep secrets there manually and never commit it.

| Variable | Required | Default | Validated by | Notes |
|---|---|---|---|---|
| `KLARDATEN_API_KEY` | yes | — | `validate_required` | Bearer token for the klardaten gateway. |
| `KLARDATEN_INSTANCE_ID` | yes | — | `validate_required` | Klardaten instance / tenant identifier. |
| `KLARDATEN_BASE_URL` | no | `https://api.klardaten.com` | — | Override only for staging / mocks. |
| `KLARDATEN_PROFILE_ID` | no | unset | — | Optional profile selector passed to `KlardatenClient`. |
| `MAGIC_LINK_SECRET` | yes | — | `validate_required`, `validate_secret` | HMAC key for magic-link tokens. Must be **at least 32 bytes** of high-entropy material. |
| `MAGIC_LINK_BASE_URL` | yes | — | `validate_required`, `validate_base_url` | Public origin for `/r/<token>` URLs. Must begin `https://` or `http://localhost`. |

## Where each variable is read

- CLI (`python -m belegmeister`): [`src/belegmeister/__main__.py`](../../src/belegmeister/__main__.py) — `_load_env_config`.
- SB web app: `src/belegmeister/sb/app.py` (FastAPI lifespan).
- Mandant magic-link app: `src/belegmeister/web/app.py` (FastAPI lifespan).

The boundary security check (key length, URL scheme) lives in
`env_validation.py` as a single source of truth — both surfaces call the
same predicates and wrap the raised `ValueError` in their own exception type
(`_EnvError` in the CLI; the framework's startup error in the web apps).
This follows the cross-layer rule documented in `/AGENTS.md`.
