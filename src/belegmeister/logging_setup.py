"""Logging bootstrap shared across every belegmeister boot path.

Uvicorn's default ``LOGGING_CONFIG`` only configures the ``uvicorn.*``
loggers — the root logger and every ``belegmeister.*`` logger are left
without handlers, so their records are silently dropped at default boot.

``configure_logging`` is the ONE place that fixes this (single source of
truth — CLAUDE.md / AGENTS.md). It is called from each entry point
(``sb.app`` and ``web.app`` at module import, ``__main__.main`` at the
top of the CLI) so no boot path can diverge.
"""

from __future__ import annotations

import logging
import sys


def configure_logging() -> None:
    """Ensure belegmeister.* loggers reach console.

    Uvicorn's default LOGGING_CONFIG only configures uvicorn.* loggers — leaving
    the root logger and app loggers without handlers. Without this bootstrap,
    every logger.info() in belegmeister.* is silently dropped at default config.
    Idempotent: skips reconfiguration if root logger already has handlers (so
    pytest caplog fixture and other test-configured logging are not disturbed).
    """
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )
    logging.getLogger("belegmeister").setLevel(logging.INFO)
