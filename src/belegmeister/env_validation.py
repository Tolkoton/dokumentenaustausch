"""Pure environment-validation helpers, shared by the CLI entrypoint
(`belegmeister.__main__`) and the web app startup (`belegmeister.web.app`
lifespan).

Each function raises `ValueError` with a self-describing message. The
caller transforms that into its own surface: the CLI prints it and
exits 1; the web lifespan re-raises it as `RuntimeError` so uvicorn
refuses to start. No I/O, no env reads here — callers pass the values
in, which keeps these unit-testable in isolation.
"""

from __future__ import annotations

MIN_SECRET_BYTES = 32


def validate_required(name: str, value: str | None) -> str:
    """Return `value` if it is a non-empty string, else raise."""
    if not value:
        raise ValueError(f"{name} environment variable is required")
    return value


def validate_secret(value: str) -> None:
    """The HMAC signing secret must carry enough entropy. Measured in
    bytes (not characters) — consistent with how it is consumed."""
    n = len(value.encode())
    if n < MIN_SECRET_BYTES:
        raise ValueError(
            f"MAGIC_LINK_SECRET must be at least {MIN_SECRET_BYTES} bytes (got {n})"
        )


def validate_base_url(value: str) -> None:
    """Magic-link base URL must be https (or http://localhost for dev)."""
    if not (value.startswith("https://") or value.startswith("http://localhost")):
        raise ValueError(
            "MAGIC_LINK_BASE_URL must start with 'https://' "
            "(or 'http://localhost' for development)"
        )
