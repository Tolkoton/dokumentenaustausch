"""Guard: belegmeister.* loggers must reach the console at default boot.

Regression guard for the resolver-perf Stage-3 finding — uvicorn's default
``LOGGING_CONFIG`` configures only ``uvicorn.*`` loggers, so every
``logger.info()`` in ``belegmeister.*`` was silently dropped at default
boot. ``configure_logging()`` (wired into every boot path) fixes that.

These tests assert the END behavior — a belegmeister.* log line is
actually visible on stderr — NOT that ``configure_logging`` was called.
The two app-boot tests run in a fresh interpreter on purpose: no pytest,
no caplog, no inherited handlers — a genuine default boot.
"""

from __future__ import annotations

import logging
import subprocess
import sys

import pytest

from belegmeister.__main__ import main
from belegmeister.logging_setup import configure_logging

_PROBE = "fresh-boot-visibility-probe"


def _emit_in_fresh_interpreter(module: str) -> subprocess.CompletedProcess[str]:
    """Import ``module`` in a brand-new interpreter, emit one
    ``belegmeister.*`` INFO line, and return the completed process so the
    caller can inspect stderr. A fresh process has no handlers on its root
    logger — exactly the default-boot state uvicorn leaves behind."""
    code = (
        f"import {module}\n"
        "import logging\n"
        f"logging.getLogger('belegmeister.datev.refresh').info({_PROBE!r})\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_sb_app_import_makes_belegmeister_logs_visible() -> None:
    """`uvicorn belegmeister.sb.app:app` boot path: importing the SB app
    module must leave belegmeister.* INFO logs flowing to stderr."""
    result = _emit_in_fresh_interpreter("belegmeister.sb.app")
    assert result.returncode == 0, result.stderr
    assert _PROBE in result.stderr


def test_web_app_import_makes_belegmeister_logs_visible() -> None:
    """`uvicorn belegmeister.web.app:app` boot path: importing the web app
    module must leave belegmeister.* INFO logs flowing to stderr."""
    result = _emit_in_fresh_interpreter("belegmeister.web.app")
    assert result.returncode == 0, result.stderr
    assert _PROBE in result.stderr


def test_main_entrypoint_configures_logging() -> None:
    """`python -m belegmeister` boot path: `main()` configures root logging
    before it dispatches. `--help` short-circuits via SystemExit, but only
    after `configure_logging()` has already run."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    saved_bm_level = logging.getLogger("belegmeister").level
    try:
        root.handlers = []
        root.setLevel(logging.WARNING)
        with pytest.raises(SystemExit):
            main(["--help"])
        assert root.handlers, "main() must attach a root handler at boot"
        assert logging.getLogger("belegmeister").level == logging.INFO
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)
        logging.getLogger("belegmeister").setLevel(saved_bm_level)


def test_configure_logging_idempotent_when_root_already_configured() -> None:
    """Idempotency guard: with a handler already on the root logger (pytest
    caplog, or any test-configured logging), `configure_logging()` is a
    no-op — it must not replace or duplicate the existing handler."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    try:
        sentinel = logging.NullHandler()
        root.handlers = [sentinel]
        configure_logging()
        assert root.handlers == [sentinel]
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)
