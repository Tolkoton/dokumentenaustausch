#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Stop hook: auto-trigger an overseer 12-check audit on unit completion.

Redesign of the abandoned bash `overseer-on-stop.sh`. The bash hook reconstructed
the last assistant message by parsing the transcript JSONL named in the Stop
envelope — but the transcript is flushed asynchronously, so the hook raced the
writer and read a stale or empty turn (anthropics/claude-code#15813).

Claude Code now ships the finished turn's text directly on the Stop envelope as
`last_assistant_message` (field probe PASS, 2026-05-22 — see
artifacts/spikes/auto-overseer-redesign-2026-05-22.md). This hook reads that
field for the *completion text* and consults the transcript only for the
*structural tool-use signal*, which is a stable historical record by the time
Stop fires.

TRIGGER — both signals required:
  1. text sentinel: `=== UNIT N COMPLETE ===` on its own line in the message.
  2. tool signal:   in the current turn, an Edit/Write/MultiEdit on a `src/`
                    path AND a Bash command matching pytest|ruff|mypy.

RECURSION GUARDS — per-branch, by design:
  - Audit-request branch    — `.overseer/.last_audit_sha` SHA of last message
                              that requested an audit; same-message re-fire
                              is silent.
  - PASS / CONTINUE branch  — `.overseer/.last_continue_sha` SHA of last
                              OVERSEER_PASS message that produced a CONTINUE
                              injection; same-message re-fire is silent.
  - Halt markers (BLOCK / ESCALATE / ADR_REQUIRED / SLICE_AWAITING_OWNER /
    SLICE_COMPLETE) silent-pass — owner takes over.

  An earlier `stop_hook_active`-based "Guard 1" was removed because it
  short-circuited BEFORE the per-branch SHA guards on hook-initiated turns
  (audit-PASS turns and CONTINUE-driven UNIT turns both arrive with
  `stop_hook_active=true`), making both injection branches unreachable in
  the autonomous loop. The per-branch SHAs handle recursion safety for the
  branches they cover.

PHASE GUARD: `.overseer/state` containing `plan` suppresses the audit — the
developer is designing, not completing units of work.

Output: `{"decision":"block","reason":...}` on stdout (exit 0) injects the audit
request and continues the turn; empty stdout (exit 0) passes the turn through.

Invoked by Claude Code as `python3 .claude/hooks/overseer_stop.py` (see
.claude/settings.json Stop hooks). The `uv run` shebang only applies when the
file is executed directly; either way it needs no third-party dependency.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import NoReturn

# `=== UNIT 7 COMPLETE ===` on its own line; surrounding horizontal space is
# tolerated so the sentinel survives minor formatting.
UNIT_DONE_RE = re.compile(r"^[ \t]*=== UNIT \d+ COMPLETE ===[ \t]*$", re.MULTILINE)
# An overseer verdict already emitted this turn — recursion guard 3.
# Halt markers — owner takes over, hook silent-passes
HALT_MARKER_RE = re.compile(
    r"OVERSEER_(?:BLOCK|ESCALATE|ADR_REQUIRED|SLICE_AWAITING_OWNER|SLICE_COMPLETE)"
)
# Pass marker — hook re-injects "continue to next unit" (taskmaster pattern)
PASS_MARKER_RE = re.compile(r"OVERSEER_PASS\b")
# Legacy alias for backward compat — any verdict marker
OVERSEER_MARKER_RE = re.compile(
    r"OVERSEER_(?:PASS|BLOCK|ESCALATE|ADR_REQUIRED|SLICE_AWAITING_OWNER|SLICE_COMPLETE)"
)
# A test / lint / type Bash command — one half of the tool signal.
CHECK_CMD_RE = re.compile(r"\b(?:pytest|ruff|mypy)\b")
# File-mutating tools — the other half of the tool signal.
EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})

CONTINUE_REASON = (
    "OVERSEER_PASS recorded. Proceed with the next unit per the active slice plan in .overseer/slice/. "
    "Do the next pending UNIT's work (src/ edits + pytest/ruff/mypy), then emit `=== UNIT N COMPLETE ===` on its own line. "
    "If the slice has no more code units (only smoke / G4 owner-driven steps remain), or if you are uncertain what UNIT N is, "
    "emit `OVERSEER_SLICE_AWAITING_OWNER: <reason>` on its own line to halt and request owner input. "
    "If the slice's last code unit is complete and smoke / G4 are next, emit `OVERSEER_SLICE_AWAITING_OWNER: smoke and G4 are owner-driven; awaiting owner walkthrough.`"
)

AUDIT_REASON = (
    "OVERSEER_REQUEST (auto-triggered by the Stop hook on a unit-completion "
    "claim). Before yielding control to the owner:\n"
    "1. Read .claude/skills/overseer/SKILL.md and apply the full 12-check "
    "checklist to the work since your last audit.\n"
    "2. Append the prescribed entry to .overseer/ledger.md before replying.\n"
    "3. Output a verdict on its own line, exactly one of: OVERSEER_PASS | "
    "OVERSEER_BLOCK: #N <reason> | OVERSEER_ESCALATE: <JSON> | "
    "OVERSEER_ADR_REQUIRED: <ADR>. Emitting any OVERSEER_ verdict marker is "
    "what stops this hook re-firing on the next turn."
)
DRY_RUN_REASON = (
    "DRY-RUN: would have blocked — the overseer Stop hook is wired and live. "
    "No real unit-completion was evaluated; this is a smoke-test injection."
)


def _emit_block(reason: str) -> NoReturn:
    """Print the block decision and exit 0 — Claude injects `reason` and
    continues the turn."""
    json.dump({"decision": "block", "reason": reason}, sys.stdout)
    sys.exit(0)


def _passthrough() -> NoReturn:
    """Exit silently with no decision — the turn ends normally."""
    sys.exit(0)


def _read_envelope() -> dict[str, object]:
    """Parse the Stop envelope from stdin. A malformed or non-object payload
    degrades to an empty envelope, never a crash — a hook must not break a
    turn over bad input."""
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): value for key, value in data.items()}


def _str_field(envelope: dict[str, object], key: str) -> str:
    """Read a string field from the envelope, or `""` if absent / wrong type."""
    value = envelope.get(key)
    return value if isinstance(value, str) else ""


def _is_turn_boundary(record: dict[str, object]) -> bool:
    """True if `record` is a genuine user message — `message.content` is a bare
    string. Tool-result records are `type:user` too but carry a list body, so
    they return False and the reverse scan treats them as transparent."""
    message = record.get("message")
    if not isinstance(message, dict):
        return False
    return isinstance(message.get("content"), str)


def _is_src_path(file_path: str) -> bool:
    """True if the path points inside a `src/` directory — absolute or
    relative. `/home/x/proj/src/foo.py` and `src/foo.py` both match."""
    normalized = file_path.replace("\\", "/")
    return normalized.startswith("src/") or "/src/" in normalized


def _has_tool_signal(transcript_path: str) -> bool:
    """True if the current turn contains BOTH an Edit/Write/MultiEdit on a
    `src/` path AND a Bash pytest/ruff/mypy command.

    The transcript is walked in reverse; the current turn is the run of records
    after the most recent genuine user message. Claude Code writes one content
    block per JSONL record, so a turn spans several assistant records.
    """
    if not transcript_path:
        return False
    path = Path(transcript_path)
    if not path.is_file():
        return False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False

    saw_src_edit = False
    saw_check_cmd = False
    for raw_line in reversed(lines):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(record, dict):
            continue
        record_type = record.get("type")
        if record_type == "user":
            if _is_turn_boundary(record):
                break  # start of the current turn — stop scanning.
            continue  # tool-result record — transparent.
        if record_type != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name")
            tool_input = block.get("input")
            if not isinstance(tool_input, dict):
                continue
            if name in EDIT_TOOLS:
                file_path = tool_input.get("file_path")
                if isinstance(file_path, str) and _is_src_path(file_path):
                    saw_src_edit = True
            elif name == "Bash":
                command = tool_input.get("command")
                if isinstance(command, str) and CHECK_CMD_RE.search(command):
                    saw_check_cmd = True
        if saw_src_edit and saw_check_cmd:
            return True
    return saw_src_edit and saw_check_cmd


def _phase_is_plan(project_dir: Path) -> bool:
    """True if `.overseer/state` exists and names the planning phase."""
    try:
        content = (project_dir / ".overseer" / "state").read_text(encoding="utf-8")
    except OSError:
        return False
    return "plan" in content.lower()


def _audit_sha_file(project_dir: Path) -> Path:
    return project_dir / ".overseer" / ".last_audit_sha"


def _message_digest(message: str) -> str:
    return hashlib.sha256(message.encode("utf-8")).hexdigest()


def _already_audited(project_dir: Path, message: str) -> bool:
    """True if an audit was already requested for this exact message text."""
    try:
        recorded = _audit_sha_file(project_dir).read_text(encoding="utf-8")
    except OSError:
        return False
    return recorded.strip() == _message_digest(message)


def _record_audit(project_dir: Path, message: str) -> None:
    """Persist this message's digest so the SHA guard suppresses a re-fire."""
    sha_file = _audit_sha_file(project_dir)
    sha_file.parent.mkdir(parents=True, exist_ok=True)
    sha_file.write_text(_message_digest(message) + "\n", encoding="utf-8")


def main() -> NoReturn:
    # NOTE — `stop_hook_active`-based Guard 1 was removed (see module
    # docstring "RECURSION GUARDS"). It preempted the per-branch SHA
    # idempotency on every hook-initiated turn — making both injection
    # branches (audit-request, PASS→CONTINUE) unreachable in the
    # autonomous loop. Per-branch SHAs at `.overseer/.last_audit_sha`
    # and `.overseer/.last_continue_sha` are the design's intended
    # recursion guards and are sufficient.
    dry_run = "--dry-run" in sys.argv[1:]
    envelope = _read_envelope()

    if dry_run:
        _emit_block(DRY_RUN_REASON)

    message = _str_field(envelope, "last_assistant_message")

    # Halt markers — owner takes over, hook silent-passes.
    if HALT_MARKER_RE.search(message):
        _passthrough()

    # PASS marker — re-inject "continue to next unit" (taskmaster pattern: keep blocking until slice done)
    if PASS_MARKER_RE.search(message):
        sha_file = (
            Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
            / ".overseer"
            / ".last_continue_sha"
        )
        digest = _message_digest(message)
        try:
            if sha_file.read_text(encoding="utf-8").strip() == digest:
                _passthrough()
        except OSError:
            pass
        sha_file.parent.mkdir(parents=True, exist_ok=True)
        sha_file.write_text(digest + "\n", encoding="utf-8")
        print(json.dumps({"decision": "block", "reason": CONTINUE_REASON}))
        sys.exit(0)

    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()

    # Phase guard: the developer is planning, not completing units of work.
    if _phase_is_plan(project_dir):
        _passthrough()

    # Guard 2: this exact message already requested an audit.
    if _already_audited(project_dir, message):
        _passthrough()

    # Two-signal trigger — both halves required.
    sentinel = UNIT_DONE_RE.search(message) is not None
    tool_signal = _has_tool_signal(_str_field(envelope, "transcript_path"))
    if not (sentinel and tool_signal):
        _passthrough()

    _record_audit(project_dir, message)
    _emit_block(AUDIT_REASON)


if __name__ == "__main__":
    main()
