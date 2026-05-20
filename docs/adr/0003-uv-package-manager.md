# ADR-0003: Use `uv` as the package manager and runner

- **Status:** Accepted (retroactive — reconstructed 2026-05-20)
- **Date:** 2026-05-12
- **Deciders:** Owner (sole developer)
- **Supersedes:** none

## Context

The project is a Python 3.12 codebase with a small dependency set (FastAPI,
httpx, Pydantic, Jinja2, python-dotenv, uvicorn) and a dev set (pytest,
mypy, ruff). It is intended to be packaged as a standalone Windows `.exe`
in slice 4c, and to run on a Hetzner Linux server in production. The
deployment surface is small but deterministic builds matter.

## Considered options

Reconstructed retroactively; alternatives were not formally weighed at the time.

- **Option A — `pip` + `requirements.txt`.** Lowest tool surface; manual
  pinning; slow resolver; no integrated virtualenv management.
- **Option B — Poetry.** Mature, ergonomic; slower than uv on cold install;
  larger dependency footprint in dev.
- **Option C — `uv`.** Astral's resolver: fast, single static binary,
  understands `pyproject.toml` and produces a reproducible `uv.lock`.
  `uv run` wraps virtualenv activation.

## Decision

Use `uv` for dependency resolution, locking, and command execution.
The lockfile (`uv.lock`) is committed. All developer commands documented in
`AGENTS.md` use the `uv run …` form so the same invocation works inside or
outside an active virtualenv. The build backend remains `hatchling` (so
the project can be wheel-packaged independently of uv).

## Consequences

- **Positive:** Fast cold installs; reproducible builds via `uv.lock`;
  no need to teach contributors to activate a venv. CI is one binary away.
- **Negative / accepted:** New, less-known tool — onboarding a contributor
  who knows only pip costs a paragraph in `AGENTS.md`. Adds a dependency
  on the Astral ecosystem; if uv becomes unmaintained we fall back to
  pip + a regenerated `requirements.txt`.
- **Operational rule:** `uv add` / `uv remove` are on the autonomy "ask"
  list — dependency churn requires explicit human approval per change.
