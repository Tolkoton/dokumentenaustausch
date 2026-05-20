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
    """Return ``value`` if it is a non-empty string, else raise.

    Treats ``None`` and ``""`` as the same failure case — both are how
    a missing or unset env var surfaces from ``os.environ.get`` / a
    silently-emptied ``.env`` line. Callers stage this check first so
    downstream validators (``validate_secret``, ``validate_base_url``)
    can rely on a real ``str``.

    Args:
        name: Variable name as it appears in the environment (e.g.
            ``"KLARDATEN_API_KEY"``). Echoed verbatim into the error
            message so the operator sees which key is missing.
        value: The candidate value, typically from ``os.environ.get(name)``.

    Returns:
        The same ``value``, narrowed to ``str``, when non-empty.

    Raises:
        ValueError: If ``value`` is ``None`` or empty. Message format:
            ``"<NAME> environment variable is required"``.
    """
    if not value:
        raise ValueError(f"{name} environment variable is required")
    return value


def validate_secret(value: str) -> None:
    """Validate that the magic-link HMAC secret carries enough entropy.

    The threshold is **bytes**, not characters, matching how the secret
    is consumed by ``hmac.new(secret.encode(), …, hashlib.sha256)`` in
    ``belegmeister.magic_link.token``. A short ASCII string and the same
    string after UTF-8 encoding agree on byte length; multi-byte
    characters in a passphrase shorten the *character* count but not the
    byte count, so the rule stays correct for either input shape.

    Args:
        value: The candidate HMAC secret. Must already be a real ``str``
            (use ``validate_required`` first to reject ``None`` / empty).

    Raises:
        ValueError: If ``len(value.encode()) < MIN_SECRET_BYTES`` (32).
            Message includes both the cap and the actual byte length so
            the operator can size the next attempt without guesswork.
    """
    n = len(value.encode())
    if n < MIN_SECRET_BYTES:
        raise ValueError(
            f"MAGIC_LINK_SECRET must be at least {MIN_SECRET_BYTES} bytes (got {n})"
        )


def validate_base_url(value: str) -> None:
    """Validate that the magic-link base URL is HTTPS (or localhost-HTTP).

    The base URL becomes the visible origin of every magic link the SB
    forwards to a Mandant; an ``http://`` origin in production would put
    a still-valid credential on the wire in clear, which the project's
    threat model rules out (see ``docs/SECURITY.md``). ``http://localhost``
    is allowed solely so the dev loop (uvicorn on a developer's machine)
    works without a self-signed certificate.

    Args:
        value: The candidate base URL. The check is intentionally a
            literal prefix match — no full URL parse — because the rule
            it enforces is exactly that: how the URL *starts*.

    Raises:
        ValueError: If ``value`` does not start with ``"https://"`` or
            ``"http://localhost"``. Message names both legal forms.
    """
    if not (value.startswith("https://") or value.startswith("http://localhost")):
        raise ValueError(
            "MAGIC_LINK_BASE_URL must start with 'https://' "
            "(or 'http://localhost' for development)"
        )
