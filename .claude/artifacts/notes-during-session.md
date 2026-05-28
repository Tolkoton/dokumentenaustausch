# Notes during session — tangential observations, not acted on

## 2026-05-22 — CLAUDE.md describes a Stop hook that does not exist

`CLAUDE.md` line 89 (`## Overseer protocol`) states: *"A Stop hook runs an
overseer triage after every turn. If it blocks with `ESCALATE_TO_OVERSEER`
..."*. But `settings.json`'s `Stop` array contains only `verify-on-stop.sh`
(lint / typecheck / test). No overseer-triage Stop hook is registered, and
`verify-on-stop.sh` does not perform any overseer triage.

The `overseer-on-stop.sh` task is presumably what is meant to make that
CLAUDE.md line true. Until then it is doc-vs-reality drift. Not fixed — out
of scope for this task. Flagged for the owner.

## 2026-05-22 — verdict-marker format diverges: `OVERSEER PASS` vs `OVERSEER_PASS`

`overseer-on-stop.sh` (this task) injects an instruction to "Output verdict on
its own line, exactly one of: OVERSEER PASS / OVERSEER BLOCK / OVERSEER
ESCALATE" (space-separated, bare line), and its recursion guard greps for
exactly that bare form: `^[[:space:]]*OVERSEER (PASS|BLOCK|ESCALATE)[[:space:]]*$`.

But the existing overseer protocol in `CLAUDE.md` (lines 91–95) uses an
UNDERSCORE form with trailing detail: `OVERSEER_PASS`, `OVERSEER_BLOCK: #N
<...>`, `OVERSEER_ESCALATE: <JSON>`.

The hook is internally consistent (it injects the bare space form and greps
for the bare space form, so the recursion guard terminates when the coder
follows the just-injected instruction). The risk: if the coder follows
CLAUDE.md habit and emits `OVERSEER_PASS` (underscore) or `OVERSEER_BLOCK: #3
...` (trailing text), the guard will not match and the hook re-fires.

Implemented per the task spec verbatim (bare space form). Not silently
widened — the owner should decide whether to harmonise the two formats
(either relax the guard regex, or align the task's injected wording with
CLAUDE.md's underscore form).

## 2026-05-22 — Schema edge case: hook extracts last entry, not joined turn

Schema edge case: hook extracts only the last transcript entry, not the joined turn — fix needed if real smoke shows missed triggers when turns end in `tool_use` rather than text (Case F / Design B, deliberately deferred).
