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
from belegmeister.klardaten.client import KlardatenClient

MIN_SECRET_BYTES = 32


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

    api_key = os.environ.get("KLARDATEN_API_KEY")
    instance_id = os.environ.get("KLARDATEN_INSTANCE_ID")
    base_url = os.environ.get("KLARDATEN_BASE_URL", "https://api.klardaten.com")
    profile_id = os.environ.get("KLARDATEN_PROFILE_ID") or None
    secret = os.environ.get("MAGIC_LINK_SECRET")
    magic_base = os.environ.get("MAGIC_LINK_BASE_URL")

    if not api_key:
        raise _EnvError("KLARDATEN_API_KEY environment variable is required")
    if not instance_id:
        raise _EnvError("KLARDATEN_INSTANCE_ID environment variable is required")
    if not secret:
        raise _EnvError("MAGIC_LINK_SECRET environment variable is required")
    if len(secret.encode()) < MIN_SECRET_BYTES:
        raise _EnvError(
            f"MAGIC_LINK_SECRET must be at least {MIN_SECRET_BYTES} bytes "
            f"(got {len(secret.encode())})"
        )
    if not magic_base:
        raise _EnvError("MAGIC_LINK_BASE_URL environment variable is required")
    if not (
        magic_base.startswith("https://") or magic_base.startswith("http://localhost")
    ):
        raise _EnvError(
            "MAGIC_LINK_BASE_URL must start with 'https://' "
            "(or 'http://localhost' for development)"
        )

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
    create.add_argument(
        "--letter-file",
        required=True,
        type=Path,
        help="Path to letter file (UTF-8 text)",
    )
    create.add_argument(
        "--ttl-days",
        type=int,
        default=7,
        help="Magic-link lifetime in days (default 7, max 7)",
    )
    return parser


def _format_validation_error(exc: ValidationError) -> str:
    lines = ["invalid arguments:"]
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)


def _cmd_create_request(args: argparse.Namespace, env: _EnvConfig) -> int:
    letter_path: Path = args.letter_file
    try:
        letter_text = letter_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"error: letter file not found: {letter_path}", file=sys.stderr)
        return 1
    except UnicodeDecodeError:
        print(
            f"error: letter file must be UTF-8 encoded: {letter_path}",
            file=sys.stderr,
        )
        return 1

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=args.ttl_days)

    try:
        cr_args = CreateRequestArgs.model_validate(
            {
                "vgm_id": args.vgm_id,
                "letter_text": letter_text,
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
