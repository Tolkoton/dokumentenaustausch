# Phase F — Handoff

**Goal**: present completed work to user for review and git commit. Distill lessons learned to MEMORY files. Suggest next task. Never commit.

**Inputs**: completed code + all Phase A-E outputs.

**Outputs**: `tasks/<id>/handoff.md`, updates to `~/.claude/memory/*/MEMORY.md` and `.architecture/MEMORY.md`, task status update, presentation to user.

## Step 1: Generate handoff summary

Write `tasks/<id>/handoff.md`:

```markdown
# Handoff for t007: <title>

## Status
- Phase A-E complete: <ISO timestamp>
- Ready for user review and git commit

## What was done
<2-3 sentence summary of the feature, plain English>

## Files changed
- `src/users/service.py` (new, 87 LOC)
- `src/users/models.py` (new, 45 LOC)
- `src/users/repository.py` (new, 53 LOC)
- `src/api/router.py` (modified, +12 LOC)
- `tests/unit/users/test_service.py` (new, 62 LOC)
- `tests/integration/users/test_register_e2e.py` (new, 41 LOC)
- `tests/security/users/test_register_security.py` (new, 38 LOC)

Total: 7 files, 338 LOC code + 141 LOC tests = 479 LOC total
(Code-only diff: 197 LOC, under 300 ceiling)

## Acceptance criteria
- ✅ ac1: `pytest tests/unit/users/test_service.py::test_register_happy_path` passes
- ✅ ac2: `pytest tests/unit/users/test_service.py::test_register_duplicate_email_raises` passes
- ✅ ac3: `pytest tests/integration/users/test_register_e2e.py::test_post_register_returns_201` passes
- ✅ ac4: curl returns 201 (verified manually)
- ✅ ac5: `mypy src/users` succeeds
- ✅ ac6: `ruff check src/users tests/unit/users tests/integration/users` succeeds

## Verification stack results
- ruff check: PASS
- ruff format: PASS
- mypy --strict: PASS
- pytest: 47/47 passed (19 unit, 18 boundary, 2 property, 4 integration, 4 security)
- mutmut (critical mode, auth-relevant): 94% mutation score (3 survivors reviewed and killed)
- coverage: changed modules 96% line / 91% branch
- diff size: 197 LOC code (under 300 ceiling)
- code-reviewer subagent: PASS (2 Should-fix addressed, 0 Blocking)
- security-auditor subagent: PASS (0 Critical/High findings)
- pre-commit-self-review-checklist: PASS

## Design decisions worth noting
<3-5 bullets on non-obvious choices made during this task>

## Open items deferred to future tasks
<any "this would be nice but is out of scope" notes>

## How to verify
\`\`\`bash
git diff --staged
pytest -q
ruff check src/users tests/unit/users tests/integration/users tests/security/users
mypy --strict src/users
\`\`\`

## How to commit (when you're ready)
\`\`\`bash
git diff --staged                  # one more look
git commit -m "feat(users): add register endpoint with TDD test suite

Implements t007. Adds POST /register with full validation, persistence,
and security tests. Follows ADR-002 (JWT) and ADR-007 (argon2 hashing).

Refs: QAS-03"
\`\`\`

## Suggested next task

Based on DAG dependencies in tasks.yaml, the next TODO task with all dependencies DONE is:

**t008**: Add authenticate(email, password) endpoint
  - depends_on: [t001, t002, t007]  ← t007 will be DONE once you commit this
  - complexity: M
  - estimated effort: ~90 min

To start: `> Take the next task.`
```

## Step 2: Session-dreaming (lessons to MEMORY)

Mandatory at end of every task. Delegate to `session-dreaming` skill — cue: _"distill lessons from this task and write to per-tech and per-project MEMORY files"_.

### Identify lessons

From PROGRESS.md and reflections.md, identify:

1. **Things that surprised you** (worth recording, others will hit too)
2. **Patterns that worked well** (worth replicating)
3. **Patterns that failed** (worth avoiding)
4. **Library/framework quirks discovered**
5. **Design choices made and their rationale** (useful future context)

For each lesson:
- 1-3 sentences
- Concrete, not generic ("Pydantic Annotated[str, Field(min_length=N)] raises ValidationError not ValueError at construction" — concrete; "Pydantic is tricky" — generic, skip)
- Tied to a context (which library, which pattern)

### Classify per lesson

For each lesson:

- **Specific to this codebase/client?** → per-project (`.architecture/MEMORY.md`)
  Examples: "We chose to wrap Stripe SDK in stripe_adapter.py to handle their idempotency keys consistently."
  "Our User entity uses CompositeKey(tenant_id, user_id) due to multi-tenancy."

- **Would bite me in any project using this tech?** → per-tech (`~/.claude/memory/<tech>/MEMORY.md`)
  Examples: "Pydantic v2 Annotated[str, Field(...)] doesn't allow `default=` unless wrapped in `Field(default=...)`."
  "argon2-cffi's `hash` method returns a string; `verify` raises `VerificationError` not returns bool."

- **Ambiguous?** → write to BOTH (cheap, prevents missing).

### Detect target technologies

From task context (re-use detection from Phase A):
- pyproject.toml deps
- imports in changed files
- Phase 1 system tags

Take top-3 most-touched technologies. Write to each.

### Append, don't overwrite

`MEMORY.md` files use append-only format:

```markdown
# Memory: <tech>

## 2026-05-12 — t007 — Pydantic v2 Annotated default value

Pydantic v2 `Annotated[str, Field(min_length=8)]` does NOT accept `= "default"` directly.
Use `Annotated[str, Field(min_length=8, default="default")]` instead.
Discovered via test_register_password_optional that failed with confusing error.

Source task: t007 / project: rss-reader

## 2026-05-12 — t007 — Argon2 verify behavior

`argon2-cffi`'s `PasswordHasher.verify(hash, password)` raises `VerifyMismatchError`
on mismatch — it does NOT return False. Catch the exception or use try/except.

Source task: t007 / project: rss-reader

## <earlier date> — <earlier task> — <earlier lesson>
...
```

Order: newest at top.

### Lesson curation (over time)

`MEMORY.md` files grow indefinitely. Periodic curation strategy:

- **Read at Phase A**: top-100 most recent lessons per file (or first ~5K tokens).
- **Manual curation**: user periodically reviews `MEMORY.md` files, consolidates similar lessons, prunes outdated ones.
- **Don't auto-prune**: skill doesn't delete lessons. Only user does.

See `references/memory-management.md` for the full algorithm.

## Step 3: Update tasks.yaml

```yaml
- id: t007
  status: READY_FOR_REVIEW  # already set in Phase E
  # Add timestamp marker:
  ready_for_review_at: "2026-05-12T16:45:00Z"
```

**Do NOT** mark status as `DONE`. Only the user marks DONE (typically via a git hook on commit, or manually).

## Step 4: Present to user

Final message structure (this is what the user sees):

```
Task t007 ready for your review.

What was done:
<one paragraph>

Files changed: 7 files (+479 LOC including tests)
Tests: 47 passed, 0 failed, mutation score 94%

Verification stack: all gates passed (ruff, mypy, pytest, mutmut, coverage,
diff size, code-reviewer subagent, security-auditor, pre-commit checklist).

Review with:
  git diff --staged

When satisfied, commit with:
  git commit -m "<suggested message>"

Next task ready in DAG: t008 (authenticate endpoint). Say "take the next
task" when you've committed this one.

Full handoff details: .architecture/tasks/t007/handoff.md
```

## Step 5: Idle

After handoff message, feature-implementer's job for this task is DONE.

The skill does NOT:
- Wait for user's commit (that's external)
- Auto-progress to the next task (user decides when)
- Modify task status to DONE (user does it)
- Run `git commit` (never)
- Update any file outside `.architecture/tasks/<id>/`, `~/.claude/memory/`, `.architecture/MEMORY.md`, and `tasks.yaml` status field

## If user changes their mind during review

Common case: user reviews diff, asks for change. Behavior:

- **Small change (one-liner, doc fix)**: do it in the same context, re-run Phase E gates 1-7 (subagents can be skipped if change is trivial), update handoff.md.
- **Behavior change**: re-enter Phase D for one more cycle. New test for new behavior. Then Phase E. Then Phase F.
- **Design change**: go back to Phase B. Update design.md with what changed and why.
- **Architecture change**: backtrack signal. Write `BACKTRACK-from-task-<id>.md`, ask user about master-architect re-run.

## Anti-patterns in Phase F

- **Committing**: never. The cardinal sin. User commits.
- **Skipping session-dreaming**: drops compound learning across tasks. Always do it.
- **Generic lessons**: "Pydantic is tricky" teaches nothing. Concrete or skip.
- **Promoting to DONE before user commits**: only commit-confirmed → DONE.
- **Forgetting per-tech write**: per-project alone misses cross-project value.
- **Re-running full pipeline on small fixes**: re-run only what's affected. Phase E gates 1-7 yes; subagents only if substantive change.
