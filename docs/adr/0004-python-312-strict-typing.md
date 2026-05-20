# ADR-0004: Python 3.12 with strict mypy and Pydantic v2 boundaries

- **Status:** Accepted (retroactive — reconstructed 2026-05-20)
- **Date:** 2026-05-12
- **Deciders:** Owner (sole developer)
- **Supersedes:** none
- **Related:** `~/.claude/CLAUDE.md` (user-level policy: strict typing,
  Pydantic models everywhere, TDD-first)

## Context

The owner's global engineering policy is "strict typing everywhere; all
structured data is Pydantic or `@dataclass(frozen=True)`; `mypy --strict`
is a gate." This project, like every other under that policy, must adopt
a Python version that supports the typing features used (PEP 695 generic
syntax is convenient but not required; `from __future__ import annotations`
plus PEP 604 unions are sufficient) and a Pydantic major version that is
not at end-of-life.

`.python-version` pins `3.12`; `pyproject.toml` declares `requires-python
= ">=3.12"`; `[tool.mypy] strict = true` covers `src`, `tests`, and
`scripts`.

## Considered options

Reconstructed retroactively; alternatives were not formally weighed at the time.

- **Option A — Python 3.11 + Pydantic v2.** Wider OS / distro support;
  loses 3.12 type-syntax ergonomics and some performance work.
- **Option B — Python 3.12 + Pydantic v2.** Current "stable + one back" at
  project start; full type-syntax ergonomics; matches the owner's other
  active projects.
- **Option C — Python 3.13.** Newest at project start but introduces churn
  in tool support; not worth the cost for this internal tool.

## Decision

Pin to **Python 3.12** (`.python-version`, `pyproject.toml requires-python`)
and **Pydantic v2** (`pydantic>=2.7`). Run `mypy --strict` across `src/`,
`tests/`, and `scripts/`. `Any` is disallowed; `# type: ignore` is
disallowed.

All structured data crossing a boundary (CLI args, HTTP request bodies,
DATEV API payloads) is a Pydantic `BaseModel`. Internal value objects are
either Pydantic models or `@dataclass(frozen=True)`; plain dicts are not
used for structured data.

## Consequences

- **Positive:** Boundary errors fail fast with structured `ValidationError`
  output that the CLI and web layers translate uniformly via
  `validation_errors.validation_error_items`. Type drift between modules
  is caught at CI time, not at runtime.
- **Negative / accepted:** Pydantic v2's validation overhead is non-zero;
  for hot loops we use plain dataclasses. `mypy --strict` is unforgiving
  of third-party libraries with poor stubs — occasional `Protocol` or
  small typed shims are needed (e.g. around httpx response shapes), and
  this is preferred over `# type: ignore`.
- **Future moves:** Python upgrades (3.13+) are out-of-scope until a
  concrete benefit appears; a new ADR will record the move when it
  happens.
