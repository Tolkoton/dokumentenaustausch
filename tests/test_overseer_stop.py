"""Tests for `.claude/hooks/overseer_stop.py` — the Stop hook that auto-triggers
an overseer 12-check audit when the developer claims a unit of work complete.

The redesigned hook reads the finished turn's text from the `last_assistant_message`
field Claude Code now ships on the Stop envelope (field probe PASS, 2026-05-22),
instead of racing the transcript JSONL flush as the abandoned bash hook did. The
transcript is still consulted — but only for the *structural* tool-use signal,
which is a stable historical record by the time Stop fires, never for the
completion text.

The hook fires only when BOTH signals are present:
  * text sentinel — `=== UNIT N COMPLETE ===` on its own line, AND
  * tool signal   — in the current turn, an Edit/Write/MultiEdit on a `src/`
                    path AND a Bash pytest/ruff/mypy command.

Recursion safety is per-branch by design: the audit-request branch is
guarded by `.overseer/.last_audit_sha`; the OVERSEER_PASS → CONTINUE
branch by `.overseer/.last_continue_sha`; halt-marker turns
(BLOCK / ESCALATE / ADR_REQUIRED / SLICE_AWAITING_OWNER / SLICE_COMPLETE)
silent-pass because the owner takes over. An earlier `stop_hook_active`
short-circuit was removed — it preempted the per-branch SHAs on every
hook-initiated turn, breaking the autonomous loop (see test_2 below).

These tests drive the hook as a subprocess with a synthetic Stop envelope and a
fixture transcript — the same way Claude Code invokes it. Every test is
hermetic: `CLAUDE_PROJECT_DIR` is monkeypatched to `tmp_path`, so the
`.overseer/` state and the idempotency file never touch the real repo or any
hardcoded global path.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / ".claude" / "hooks" / "overseer_stop.py"

SENTINEL = "=== UNIT 1 COMPLETE ==="

ToolUse = tuple[str, str]
"""(tool_name, argument): for Bash the argument is the command; for
Edit/Write/MultiEdit/Read it is the file_path."""


# --- fixture helpers --------------------------------------------------------


def _tool_use_record(tool_name: str, arg: str) -> dict[str, object]:
    """One assistant JSONL record carrying a single `tool_use` block — the
    one-block-per-record shape Claude Code writes to the transcript."""
    inp: dict[str, str] = (
        {"command": arg} if tool_name == "Bash" else {"file_path": arg}
    )
    return {
        "type": "assistant",
        "isSidechain": False,
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": tool_name, "input": inp}],
        },
    }


def _user_boundary(text: str = "go") -> dict[str, object]:
    """A genuine user-turn boundary: `message.content` is a bare string. The
    hook's reverse scan must stop here when reconstructing the current turn."""
    return {"type": "user", "message": {"role": "user", "content": text}}


def _tool_result() -> dict[str, object]:
    """A tool-result record — `type:user` with a list body. The reverse scan
    must treat this as transparent, not as a turn boundary."""
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "content": "ok"}],
        },
    }


def write_transcript(path: Path, tool_uses: list[ToolUse]) -> Path:
    """Write a synthetic one-turn transcript JSONL: a user boundary, then an
    assistant tool_use record + tool_result for each entry. Returns `path`."""
    records: list[dict[str, object]] = [_user_boundary()]
    for tool_name, arg in tool_uses:
        records.append(_tool_use_record(tool_name, arg))
        records.append(_tool_result())
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


def write_phase(project_dir: Path, phase: str) -> None:
    """Write `.overseer/state` under the (fixture) project root."""
    overseer = project_dir / ".overseer"
    overseer.mkdir(parents=True, exist_ok=True)
    (overseer / "state").write_text(phase, encoding="utf-8")


def base_payload(
    project_dir: Path,
    *,
    last_assistant_message: str,
    transcript: Path,
    stop_hook_active: bool = False,
) -> dict[str, object]:
    """Build a Stop envelope matching the schema Claude Code puts on stdin."""
    return {
        "session_id": "test-session",
        "transcript_path": str(transcript),
        "cwd": str(project_dir),
        "permission_mode": "acceptEdits",
        "hook_event_name": "Stop",
        "stop_hook_active": stop_hook_active,
        "last_assistant_message": last_assistant_message,
    }


def run_hook(
    payload: dict[str, object], *, extra_args: list[str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Invoke the hook the way Claude Code does: envelope JSON on stdin.
    `CLAUDE_PROJECT_DIR` must already be set in the environment by the caller
    (via `monkeypatch.setenv`) so the hook reads hermetic `tmp_path` state."""
    cmd: list[str] = [sys.executable, str(HOOK)]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(
        cmd,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )


# --- tests ------------------------------------------------------------------


def test_1_hook_script_exists_and_is_executable() -> None:
    """The deliverable: an executable Python hook at the canonical path."""
    assert HOOK.is_file(), f"hook script missing at {HOOK}"
    assert os.access(HOOK, os.X_OK), f"hook script not executable: {HOOK}"


def test_2_stop_hook_active_does_not_preempt_named_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`stop_hook_active=true` arrives on every hook-initiated turn — both
    the audit-PASS turn (triggered by the prior audit-request block) AND the
    next-UNIT turn (triggered by the prior CONTINUE block). It MUST NOT
    preempt the audit-request and PASS-continuation branches, or the
    autonomous loop stalls one step in.

    Recursion safety lives in the per-branch SHA files
    (`.last_audit_sha`, `.last_continue_sha`); see test_7 and test_10
    for the SHA-idempotency contract.

    Regression history: an earlier `stop_hook_active`-based "Guard 1"
    short-circuited BEFORE the per-branch SHA guards, making both
    injection branches unreachable on hook-initiated turns. Empirical
    repro: with Guard 1 in place, this test's audit-fire and PASS-fire
    sub-cases both got silent passthrough; with Guard 1 removed, both
    fire their intended block decisions on the first invocation.
    """
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript = write_transcript(
        tmp_path / "t.jsonl",
        [("Edit", "src/belegmeister/foo.py"), ("Bash", "uv run pytest")],
    )

    # Sub-case A: sentinel + tool signal under stop_hook_active=true
    # → audit-request injected. Recursion guard is `.last_audit_sha`
    # (covered by test_7), NOT the removed Guard 1.
    audit_payload = base_payload(
        tmp_path,
        last_assistant_message=f"All done.\n{SENTINEL}",
        transcript=transcript,
        stop_hook_active=True,
    )
    audit_result = run_hook(audit_payload)
    assert audit_result.returncode == 0, audit_result.stderr
    audit_decision: dict[str, object] = json.loads(audit_result.stdout)
    assert audit_decision["decision"] == "block"
    audit_reason = audit_decision["reason"]
    assert isinstance(audit_reason, str)
    assert "OVERSEER_REQUEST" in audit_reason

    # Sub-case B: OVERSEER_PASS marker under stop_hook_active=true
    # → CONTINUE injected. Recursion guard is `.last_continue_sha`
    # (covered by test_10), NOT the removed Guard 1.
    pass_payload = base_payload(
        tmp_path,
        last_assistant_message="Audit done.\nOVERSEER_PASS",
        transcript=transcript,
        stop_hook_active=True,
    )
    pass_result = run_hook(pass_payload)
    assert pass_result.returncode == 0, pass_result.stderr
    pass_decision: dict[str, object] = json.loads(pass_result.stdout)
    assert pass_decision["decision"] == "block"
    pass_reason = pass_decision["reason"]
    assert isinstance(pass_reason, str)
    assert "OVERSEER_PASS recorded" in pass_reason


def test_3_overseer_marker_short_circuits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recursion guard 3: an OVERSEER verdict marker in the last assistant
    message determines hook behavior per the verdict's class.

    Halt markers (BLOCK / ESCALATE / ADR_REQUIRED / SLICE_AWAITING_OWNER /
    SLICE_COMPLETE) — the owner has taken over (or the slice is shipped);
    the hook silent-passes (no audit re-trigger, no CONTINUE injection).

    PASS marker (OVERSEER_PASS) — autonomous-continuation trigger; the hook
    emits a continue-block JSON whose reason instructs Claude to proceed
    with the next unit per the active slice plan. Idempotency is covered
    by `test_10_overseer_pass_continue_idempotent` (one-shot test_3 here
    only checks the first-invocation contract).
    """
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript = write_transcript(
        tmp_path / "t.jsonl",
        [("Edit", "src/belegmeister/foo.py"), ("Bash", "uv run pytest")],
    )
    halt_markers = (
        "OVERSEER_BLOCK: #4 gap",
        'OVERSEER_ESCALATE: {"question": "x"}',
        "OVERSEER_ADR_REQUIRED: 0005-something",
        "OVERSEER_SLICE_AWAITING_OWNER: handoff",
        "OVERSEER_SLICE_COMPLETE: shipped",
    )
    for marker in halt_markers:
        payload = base_payload(
            tmp_path,
            last_assistant_message=f"{SENTINEL}\n\nAudit done.\n{marker}",
            transcript=transcript,
        )
        result = run_hook(payload)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "", f"halt-marker guard failed on {marker!r}"

    # OVERSEER_PASS — emits continue-block JSON (autonomous-continuation)
    pass_payload = base_payload(
        tmp_path,
        last_assistant_message=f"{SENTINEL}\n\nAudit done.\nOVERSEER_PASS",
        transcript=transcript,
    )
    pass_result = run_hook(pass_payload)
    assert pass_result.returncode == 0, pass_result.stderr
    pass_decision: dict[str, object] = json.loads(pass_result.stdout)
    assert pass_decision["decision"] == "block"
    pass_reason = pass_decision["reason"]
    assert isinstance(pass_reason, str)
    assert "OVERSEER_PASS recorded" in pass_reason


def test_4_text_sentinel_alone_is_insufficient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One signal is not enough: the completion sentinel with no qualifying
    tool activity in the turn must not trigger an audit. A bare claim of
    'done' with no code change is not a unit completion."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    # Transcript holds a Read only — no src edit, no pytest/ruff/mypy Bash.
    transcript = write_transcript(
        tmp_path / "t.jsonl", [("Read", "src/belegmeister/foo.py")]
    )
    payload = base_payload(
        tmp_path,
        last_assistant_message=f"Looks finished.\n{SENTINEL}",
        transcript=transcript,
    )
    result = run_hook(payload)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_5_tool_signal_alone_is_insufficient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One signal is not enough: real tool activity (src edit + pytest) with
    no completion sentinel in the message must not trigger an audit. Work in
    progress is not work claimed complete."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript = write_transcript(
        tmp_path / "t.jsonl",
        [("Edit", "src/belegmeister/foo.py"), ("Bash", "uv run pytest -q")],
    )
    payload = base_payload(
        tmp_path,
        last_assistant_message="Made progress; still wiring the next part.",
        transcript=transcript,
    )
    result = run_hook(payload)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_6_both_signals_emit_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both signals present — completion sentinel in the message AND a src
    edit + a pytest/ruff/mypy Bash in the turn — emits a block decision whose
    reason carries the OVERSEER_REQUEST marker the developer must act on."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript = write_transcript(
        tmp_path / "t.jsonl",
        [
            ("Write", "src/belegmeister/widget.py"),
            ("Bash", "uv run mypy --strict src/"),
        ],
    )
    payload = base_payload(
        tmp_path,
        last_assistant_message=f"Widget slice landed.\n{SENTINEL}",
        transcript=transcript,
    )
    result = run_hook(payload)
    assert result.returncode == 0, result.stderr
    decision: dict[str, object] = json.loads(result.stdout)
    assert decision["decision"] == "block"
    reason = decision["reason"]
    assert isinstance(reason, str)
    assert "OVERSEER_REQUEST" in reason


def test_7_sha_idempotency_suppresses_second_fire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recursion guard 2: once an audit is requested for a given last message,
    a second Stop carrying the *same* message must pass silently — the SHA-256
    of the message is recorded and matched. Without this guard the audit
    re-fires every turn until the message text happens to change."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript = write_transcript(
        tmp_path / "t.jsonl",
        [
            ("Edit", "src/belegmeister/widget.py"),
            ("Bash", "uv run pytest tests/ -q"),
        ],
    )
    payload = base_payload(
        tmp_path,
        last_assistant_message=f"Widget slice landed.\n{SENTINEL}",
        transcript=transcript,
    )
    first = run_hook(payload)
    assert first.returncode == 0, first.stderr
    first_decision: dict[str, object] = json.loads(first.stdout)
    assert first_decision["decision"] == "block"

    second = run_hook(payload)
    assert second.returncode == 0, second.stderr
    assert second.stdout.strip() == ""


def test_8_plan_phase_skips_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In the planning phase the developer is designing, not completing units
    of work — `.overseer/state` holding 'plan' suppresses the audit even when
    both completion signals are present."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    write_phase(tmp_path, "plan")
    transcript = write_transcript(
        tmp_path / "t.jsonl",
        [("Edit", "src/belegmeister/foo.py"), ("Bash", "uv run pytest")],
    )
    payload = base_payload(
        tmp_path,
        last_assistant_message=f"Plan drafted.\n{SENTINEL}",
        transcript=transcript,
    )
    result = run_hook(payload)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_9_dry_run_always_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--dry-run` is the smoke-test affordance: it emits a block decision
    regardless of triggers, so the wiring can be verified without staging a
    real unit completion. The reason names it a dry run, not a real request."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript = write_transcript(tmp_path / "t.jsonl", [])  # no tool activity
    payload = base_payload(
        tmp_path,
        last_assistant_message="Nothing of note happened this turn.",
        transcript=transcript,
    )
    result = run_hook(payload, extra_args=["--dry-run"])
    assert result.returncode == 0, result.stderr
    decision: dict[str, object] = json.loads(result.stdout)
    assert decision["decision"] == "block"
    reason = decision["reason"]
    assert isinstance(reason, str)
    assert "DRY-RUN: would have blocked" in reason


def test_10_overseer_pass_continue_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OVERSEER_PASS triggers a CONTINUE injection on first sight, but the
    injection must be idempotent — a second Stop with the *same*
    `last_assistant_message` must pass silently. Without this guard the
    hook would re-inject the same CONTINUE prompt every turn until the
    message text happens to change, looping the autonomous-continuation
    flow forever on an unchanging PASS.

    Idempotency mirrors the audit-side SHA guard (see test_7), via the
    `.overseer/.last_continue_sha` file. `tmp_path` is hermetic
    per-test — the sha file is cleaned automatically when the test exits,
    no explicit teardown needed.
    """
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    transcript = write_transcript(
        tmp_path / "t.jsonl",
        [("Edit", "src/belegmeister/foo.py"), ("Bash", "uv run pytest")],
    )
    payload = base_payload(
        tmp_path,
        last_assistant_message=f"{SENTINEL}\n\nAudit done.\nOVERSEER_PASS",
        transcript=transcript,
    )

    # First invocation — emits the CONTINUE injection
    first = run_hook(payload)
    assert first.returncode == 0, first.stderr
    first_decision: dict[str, object] = json.loads(first.stdout)
    assert first_decision["decision"] == "block"
    first_reason = first_decision["reason"]
    assert isinstance(first_reason, str)
    assert "OVERSEER_PASS recorded" in first_reason

    # Second invocation with the identical message — silent passthrough
    second = run_hook(payload)
    assert second.returncode == 0, second.stderr
    assert second.stdout.strip() == "", (
        "continue idempotency guard failed: identical message re-triggered CONTINUE"
    )

    # The idempotency artifact lives at the canonical path
    sha_file = tmp_path / ".overseer" / ".last_continue_sha"
    assert sha_file.is_file(), "expected .last_continue_sha to be written"
