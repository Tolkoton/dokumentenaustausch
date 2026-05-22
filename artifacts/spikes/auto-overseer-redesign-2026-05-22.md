# Auto-overseer Stop hook — redesign (2026-05-22)

Supersedes the bash `overseer-on-stop.sh` approach. This note records WHY the
bash hook was abandoned, WHAT replaced it, and the post-restart smoke procedure
(STEP 7) the owner must run to confirm the wiring end-to-end.

## Old approach — bash hook reading the transcript (abandoned)

`.claude/hooks/overseer-on-stop.sh` reconstructed the last assistant message by
opening the transcript JSONL named in the Stop envelope's `transcript_path` and
re-deriving the final conceptual turn with a multi-stage `jq` pipeline.

Why it was abandoned:

- **Transcript flush race.** The transcript is written asynchronously. When the
  Stop hook runs, the final assistant records may not be flushed yet, so the
  hook read a stale or empty turn — see anthropics/claude-code#15813. The hook
  silently passed exactly when it should have fired.
- **Schema fragility.** Claude Code writes one content block per JSONL record;
  the first cut assumed one record == one message and missed completion phrases
  emitted before a late tool call. Design B (turn reconstruction) patched the
  schema bug but kept the underlying flush race.
- **Untestable end-to-end in-session.** Hook config is snapshotted at session
  start, so the hook could never be observed in the session that wrote it.

## New approach — Python hook reading `last_assistant_message`

`.claude/hooks/overseer_stop.py` — single-file, stdlib-only (`uv run` shebang +
PEP-723 block; invoked as `python3` from `settings.json`). It reads the
finished turn's text from the `last_assistant_message` field Claude Code now
ships **directly on the Stop envelope (stdin)** — no transcript parsing for the
completion text. The transcript is still opened, but only for the *structural
tool-use signal*, which is stable history by the time Stop fires (it is not the
racing tail).

Trigger — both signals required:

1. **Text sentinel** — `=== UNIT N COMPLETE ===` on its own line in
   `last_assistant_message`.
2. **Tool signal** — in the current turn, an `Edit`/`Write`/`MultiEdit` on a
   `src/` path AND a Bash `pytest`/`ruff`/`mypy` command.

Recursion guards (any one suppresses): `stop_hook_active` flag · SHA-256
idempotency file `.overseer/.last_audit_sha` · `OVERSEER_` verdict marker.
Phase guard: `.overseer/state` containing `plan` skips the audit.

Output: `{"decision":"block","reason":...}` on stdout (exit 0) injects the audit
request; empty stdout (exit 0) passes the turn through.

Behaviour is pinned by `tests/test_overseer_stop.py` (9 hermetic tests, every
one driving the hook as a subprocess with a synthetic envelope under a
`tmp_path` `CLAUDE_PROJECT_DIR` — no global-state coupling).

## Evidence

- **Field probe PASS (2026-05-22).** `_field_probe.sh` was wired as a Stop hook
  and observed two real fires in `/tmp/field-probe.log`:
  - Fire 1 (`12:36:58Z`, line 2) and Fire 2 (`12:38:17Z`, line 8) — both
    envelopes carry a fully-populated `last_assistant_message` field. Fire 2
    captured the complete "Run ls" response verbatim. The field-reading premise
    is sound.
- **Version.** Per the research report that scoped this task, the
  `last_assistant_message` field was added to the Stop envelope in Claude Code
  v2.1.47. That version number is the report's claim and was not independently
  verified here; what the field probe confirmed directly is the field's
  *presence* in the Claude Code version running this project.

## Design decision — tool signal is `src/`-only

`overseer_stop.py` recognises a code change only when the `Edit`/`Write`/
`MultiEdit` target is under `src/`. Edits confined to `tests/`, `docs/`, or
`.claude/` do not satisfy the tool signal.

Rationale: the overseer audits *completed units of production work*. A turn
that touches only tests (a RED-only turn) or only docs is not the kind of
completion the 12-check checklist is built to review — and the developer should
not emit the `=== UNIT N COMPLETE ===` sentinel for it anyway. Broadening the
match to `tests/` was considered and rejected: it would let a RED-only turn
trigger a premature audit. **Consequence:** the STEP 7 smoke must edit a `src/`
file, not `PROGRESS.md` — see the procedure below.

## STEP 7 — post-restart end-to-end smoke (owner runs)

The hook only goes live after a Claude Code restart (hook config is snapshotted
at session start). After reviewing and committing the staged changes:

1. **Restart Claude Code** so the Stop-hook snapshot reloads.
2. **Quick wiring check (no audit logic):**
   `echo '{}' | python3 .claude/hooks/overseer_stop.py --dry-run`
   → must print `{"decision": "block", "reason": "DRY-RUN: would have blocked ...`
3. **Real two-signal smoke.** Trigger one turn with this prompt:
   > Create `src/belegmeister/_smoke_marker.py` containing the single line
   > `# overseer smoke marker`. Run `uv run pytest tests/ -q`. End your final
   > message with the exact line, alone on its own line:
   > `=== UNIT 1 COMPLETE ===`
   That turn carries both signals — a `Write` under `src/` and a `pytest` Bash.
4. **Observe:** the next turn must begin with the injected `OVERSEER_REQUEST`
   audit prompt — the overseer 12-check runs, ending in an `OVERSEER_` verdict.
5. **Confirm recursion guard:** the turn *after* the verdict ends normally —
   the hook does not re-fire (guard 3: the verdict marker; guard 2: the SHA).
6. **Cleanup:** delete `src/belegmeister/_smoke_marker.py` and the
   `.overseer/.last_audit_sha` file the smoke wrote.

PASS criteria:

- `OVERSEER_REQUEST` injected after the unit-completion turn.
- No re-fire after the verdict turn.
- No injection on a turn with no sentinel (e.g. a plain question).

OUTCOME (owner to record)

- [x] PASS — 2026-05-22T13:25Z — All three PASS criteria met end-to-end. Hook live and operational.
- [ ] FAIL — notes:
