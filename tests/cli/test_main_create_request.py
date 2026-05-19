"""CLI glue tests for `python -m belegmeister create-request`.

`main(argv)` is exercised end-to-end EXCEPT the network: `run_create_request`
is monkeypatched to record the `CreateRequestArgs` it receives and return a
fixed URL. Env is set via monkeypatch so `_load_env_config` passes without a
real `.env`. Test-code prefix: M<N>.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import belegmeister.__main__ as cli
from belegmeister.cli.create_request import CreateRequestArgs

_GOOD_ENV = {
    "KLARDATEN_API_KEY": "key-xyz",
    "KLARDATEN_INSTANCE_ID": "inst-1",
    "MAGIC_LINK_SECRET": "s" * 48,
    "MAGIC_LINK_BASE_URL": "https://app.example.com",
}


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[CreateRequestArgs]:
    for key, value in _GOOD_ENV.items():
        monkeypatch.setenv(key, value)
    captured: list[CreateRequestArgs] = []

    def _fake_run(args: CreateRequestArgs, **_: Any) -> str:
        captured.append(args)
        return "https://app.example.com/r/tok.sig"

    monkeypatch.setattr(cli, "run_create_request", _fake_run)
    return captured


def _argv(body: Path, **extra: str) -> list[str]:
    argv = [
        "create-request",
        "--vgm-id",
        "11111111-1111-1111-1111-111111111111",
        "--to",
        "mandant@example.com",
        "--subject",
        "Unterlagen 2026",
        "--body-file",
        str(body),
    ]
    for flag, value in extra.items():
        argv += [f"--{flag.replace('_', '-')}", value]
    return argv


def test_M1_all_flags_passed_into_create_request_args(
    tmp_path: Path,
    recorded: list[CreateRequestArgs],
    capsys: pytest.CaptureFixture[str],
) -> None:
    body = tmp_path / "body.md"
    body.write_text("Sehr geehrte Frau Müller,\n\nBitte Belege.", encoding="utf-8")
    qfile = tmp_path / "q.txt"
    qfile.write_text("Frage eins?\nFrage zwei?\n", encoding="utf-8")

    rc = cli.main(_argv(body, cc="kanzlei@example.com", questions_file=str(qfile)))

    assert rc == 0
    assert "https://app.example.com/r/tok.sig" in capsys.readouterr().out
    [args] = recorded
    assert args.vgm_id == "11111111-1111-1111-1111-111111111111"
    assert args.to == "mandant@example.com"
    assert args.cc == "kanzlei@example.com"
    assert args.subject == "Unterlagen 2026"
    assert args.body == "Sehr geehrte Frau Müller,\n\nBitte Belege."
    assert args.questions == ["Frage eins?", "Frage zwei?"]


def test_M2_missing_body_file_clean_error(
    tmp_path: Path,
    recorded: list[CreateRequestArgs],
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = cli.main(_argv(tmp_path / "nope.md"))
    err = capsys.readouterr().err
    assert rc == 1
    assert "error: body file not found" in err
    assert "Traceback" not in err
    assert recorded == []


def test_M3_body_file_invalid_utf8_clean_error(
    tmp_path: Path,
    recorded: list[CreateRequestArgs],
    capsys: pytest.CaptureFixture[str],
) -> None:
    body = tmp_path / "body.md"
    body.write_bytes(b"\xff\xfe not utf-8")
    rc = cli.main(_argv(body))
    err = capsys.readouterr().err
    assert rc == 1
    assert "error: body file must be UTF-8 encoded" in err
    assert recorded == []


def test_M4_questions_file_one_per_line_blank_lines_skipped(
    tmp_path: Path, recorded: list[CreateRequestArgs]
) -> None:
    body = tmp_path / "body.md"
    body.write_text("Bitte Belege.", encoding="utf-8")
    qfile = tmp_path / "q.txt"
    qfile.write_text("\n  Frage eins?  \n\n\nFrage zwei?\n\n", encoding="utf-8")

    rc = cli.main(_argv(body, questions_file=str(qfile)))

    assert rc == 0
    [args] = recorded
    assert args.questions == ["Frage eins?", "Frage zwei?"]


def test_M5_no_questions_file_means_empty_list(
    tmp_path: Path, recorded: list[CreateRequestArgs]
) -> None:
    body = tmp_path / "body.md"
    body.write_text("Bitte Belege.", encoding="utf-8")
    rc = cli.main(_argv(body))
    assert rc == 0
    [args] = recorded
    assert args.questions == []


def test_M6_no_cc_means_empty_string(
    tmp_path: Path, recorded: list[CreateRequestArgs]
) -> None:
    body = tmp_path / "body.md"
    body.write_text("Bitte Belege.", encoding="utf-8")
    rc = cli.main(_argv(body))
    assert rc == 0
    [args] = recorded
    assert args.cc == ""


def test_M7_questions_file_missing_path_clean_error(
    tmp_path: Path,
    recorded: list[CreateRequestArgs],
    capsys: pytest.CaptureFixture[str],
) -> None:
    body = tmp_path / "body.md"
    body.write_text("Bitte Belege.", encoding="utf-8")
    rc = cli.main(_argv(body, questions_file=str(tmp_path / "missing.txt")))
    err = capsys.readouterr().err
    assert rc == 1
    assert "error: questions file not found" in err
    assert "Traceback" not in err
    assert recorded == []


def test_M8_questions_file_invalid_utf8_clean_error(
    tmp_path: Path,
    recorded: list[CreateRequestArgs],
    capsys: pytest.CaptureFixture[str],
) -> None:
    body = tmp_path / "body.md"
    body.write_text("Bitte Belege.", encoding="utf-8")
    qfile = tmp_path / "q.txt"
    qfile.write_bytes(b"\xff Frage?")
    rc = cli.main(_argv(body, questions_file=str(qfile)))
    err = capsys.readouterr().err
    assert rc == 1
    assert "error: questions file must be UTF-8 encoded" in err
    assert recorded == []
