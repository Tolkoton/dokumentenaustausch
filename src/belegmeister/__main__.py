"""Entrypoint: `python -m belegmeister <subcommand> ...`.

A humble glue layer: env loading, argparse, exception → exit code.
All testable logic lives in `belegmeister.cli.create_request` and
`belegmeister.magic_link.token` (covered by RC1-6, TG1-2, TV1-5).

Boundary security checks run here, before any side-effect:
- MAGIC_LINK_SECRET   present, >=32 bytes
- MAGIC_LINK_BASE_URL present, https:// (or http://localhost for dev)
- KLARDATEN_API_KEY + KLARDATEN_INSTANCE_ID present

User-facing errors (missing env, malformed args, named domain exceptions)
print `error: <message>` to stderr and exit 1. Unknown exceptions are
left to surface with full traceback — those are bugs, not user errors.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from belegmeister.cli.create_request import (
    CreateRequestArgs,
    UploadFailed,
    run_create_request,
)
from belegmeister.datev.upload import InvalidUploadTarget
from belegmeister.env_validation import (
    validate_base_url,
    validate_required,
    validate_secret,
)
from belegmeister.klardaten.client import KlardatenClient
from belegmeister.validation_errors import validation_error_items


@dataclass(frozen=True)
class _EnvConfig:
    klardaten_base_url: str
    klardaten_api_key: str
    klardaten_instance_id: str
    klardaten_profile_id: str | None
    magic_link_secret: str
    magic_link_base_url: str


class _EnvError(Exception):
    """User-facing configuration error (printed without traceback)."""


def _load_env_config() -> _EnvConfig:
    load_dotenv()

    base_url = os.environ.get("KLARDATEN_BASE_URL", "https://api.klardaten.com")
    profile_id = os.environ.get("KLARDATEN_PROFILE_ID") or None

    # Shared validators (also used by the web lifespan). They raise
    # ValueError; the CLI surface wants _EnvError (printed, exit 1).
    try:
        api_key = validate_required(
            "KLARDATEN_API_KEY", os.environ.get("KLARDATEN_API_KEY")
        )
        instance_id = validate_required(
            "KLARDATEN_INSTANCE_ID", os.environ.get("KLARDATEN_INSTANCE_ID")
        )
        secret = validate_required(
            "MAGIC_LINK_SECRET", os.environ.get("MAGIC_LINK_SECRET")
        )
        validate_secret(secret)
        magic_base = validate_required(
            "MAGIC_LINK_BASE_URL", os.environ.get("MAGIC_LINK_BASE_URL")
        )
        validate_base_url(magic_base)
    except ValueError as exc:
        raise _EnvError(str(exc)) from exc

    return _EnvConfig(
        klardaten_base_url=base_url,
        klardaten_api_key=api_key,
        klardaten_instance_id=instance_id,
        klardaten_profile_id=profile_id,
        magic_link_secret=secret,
        magic_link_base_url=magic_base,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="belegmeister")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser(
        "create-request",
        help="Create a document-request against an existing VGM "
        "(uploads letter, prints magic-link URL).",
    )
    create.add_argument("--vgm-id", required=True, help="VGM (binder) GUID")
    create.add_argument("--to", required=True, help="Recipient email (To header)")
    create.add_argument("--cc", default="", help="Cc email (optional)")
    create.add_argument("--subject", required=True, help="Email subject")
    create.add_argument(
        "--body-file",
        required=True,
        type=Path,
        help="Path to letter body file (UTF-8 text)",
    )
    create.add_argument(
        "--questions-file",
        type=Path,
        default=None,
        help="Optional: file with one question per line (UTF-8); "
        "blank lines skipped. Omit entirely for zero questions.",
    )
    create.add_argument(
        "--ttl-days",
        type=int,
        default=7,
        help="Magic-link lifetime in days (default 7, max 7)",
    )
    return parser


def _format_validation_error(exc: ValidationError) -> str:
    # Thin CLI wrapper over the shared extractor (single source of truth;
    # the SB web surface groups the same items per form field). Output is
    # byte-identical to the pre-extraction inline version.
    lines = ["invalid arguments:"]
    for loc, msg in validation_error_items(exc):
        lines.append(f"  - {loc}: {msg}")
    return "\n".join(lines)


class _CliFileError(Exception):
    """User-facing file-argument error (printed without traceback, exit 1)."""


def _read_utf8(path: Path, label: str) -> str:
    """Read a UTF-8 file argument or raise a clean _CliFileError. ONE
    source of truth for file-arg error semantics — body-file and
    questions-file get identical messages by construction."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise _CliFileError(f"{label} file not found: {path}") from exc
    except UnicodeDecodeError as exc:
        raise _CliFileError(f"{label} file must be UTF-8 encoded: {path}") from exc


def _parse_questions_file(path: Path) -> list[str]:
    """One question per line; blank lines skipped. Re-stripped by the
    CreateRequestArgs validator (single source of truth for the rule)."""
    text = _read_utf8(path, "questions")
    return [line.strip() for line in text.splitlines() if line.strip()]


def _cmd_create_request(args: argparse.Namespace, env: _EnvConfig) -> int:
    try:
        body = _read_utf8(args.body_file, "body")
        questions = (
            _parse_questions_file(args.questions_file)
            if args.questions_file is not None
            else []
        )
    except _CliFileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=args.ttl_days)

    try:
        cr_args = CreateRequestArgs.model_validate(
            {
                "vgm_id": args.vgm_id,
                "to": args.to,
                "cc": args.cc,
                "subject": args.subject,
                "body": body,
                "questions": questions,
                "expires_at": expires_at,
            },
            context={"now": now},
        )
    except ValidationError as exc:
        print(f"error: {_format_validation_error(exc)}", file=sys.stderr)
        return 1

    client = KlardatenClient(
        base_url=env.klardaten_base_url,
        api_key=env.klardaten_api_key,
        instance_id=env.klardaten_instance_id,
        profile_id=env.klardaten_profile_id,
    )

    try:
        url = run_create_request(
            cr_args,
            klardaten_client=client,
            magic_link_secret=env.magic_link_secret,
            magic_link_base_url=env.magic_link_base_url,
            now=now,
        )
    except InvalidUploadTarget as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except UploadFailed as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(url)
    return 0


def main(argv: list[str] | None = None) -> int:
    # Argparse first so --help / -h short-circuit via SystemExit before
    # any env validation runs (env errors should not gate --help output).
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        env = _load_env_config()
    except _EnvError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.command == "create-request":
        return _cmd_create_request(args, env)
    # argparse with `required=True` on subparsers makes this unreachable.
    print(f"error: unknown command: {args.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
