# Phase E — Self-Review

**Goal**: gate before handoff. Every MUST check passes, or back to Phase D. No diff goes to user until E passes.

**Inputs**: completed code + tests from Phase D, full task workspace.

**Outputs**: in-context verification report. Updates `tasks/<id>/PROGRESS.md`. Updates `tasks.yaml` status if and only if all gates pass.

## Hard gates (ALL must pass)

Each gate in order. If any fails, return to Phase D, fix, retry Phase E from the start (not from the failed step — re-run everything since fixes can break earlier gates).

### Gate 1: ruff check

```bash
ruff check --select=ALL --ignore=<project-ignores> src/ tests/
```

Pass: zero violations on changed lines (use `--diff` to focus on changed lines if codebase has legacy violations).

Specifically must pass for paranoid SRP:
- C901 (complexity)
- PLR0915 (too many statements)
- PLR0912 (too many branches)
- PLR0911 (too many return statements)
- PLR0913 (too many arguments)

Fail → Phase D: refactor.

### Gate 2: ruff format

```bash
ruff format --check src/ tests/
```

Pass: no diff.

Fail → `ruff format src/ tests/` then re-run from Gate 1.

### Gate 3: mypy strict

```bash
mypy --strict src/
```

Pass: no errors on changed files. Existing errors in unchanged files are acceptable (legacy debt).

Fail → Phase D: fix type errors.

### Gate 4: pytest full suite

```bash
pytest -q --tb=short
```

Pass: 100% green. Zero failures, zero errors, zero unintended skips.

Skips are allowed only if:
- Explicit `pytest.mark.skip(reason="...")` with concrete reason (not just "TODO")
- Skip is for environment reasons (e.g., "requires Docker not available in CI")
- Reason is documented in test

Fail → Phase D: fix the regression.

### Gate 5: mutmut on changed modules

Mode detection: per `references/mutation-policy.md` (auto-detect critical via keywords, files, imports, QAS refs).

```bash
# Critical mode (no timeout)
mutmut run --paths-to-mutate=<changed-modules>

# Standard mode (2-min timeout)
timeout 120 mutmut run --paths-to-mutate=<changed-modules>
```

Pass criteria:
- **Critical mode**: mutation score ≥80% on changed modules. ALL surviving mutants must be reviewed and either killed (write a missing test) or explicitly accepted with one-line justification in `tasks/<id>/mutation-survivors.md`.
- **Standard mode**: best-effort; partial result OK; record score in `tasks/<id>/mutation-report.md`. No hard threshold, but mutation score <50% is a flag (Phase D: write better tests).

Fail (critical mode <80%) → Phase D: write tests for surviving mutants.

### Gate 6: coverage delta

```bash
pytest --cov=src --cov-report=term --cov-report=json
```

Pass: coverage of changed modules ≥ before-task coverage. No regression.

Threshold: changed modules must reach ≥90% line coverage AND ≥85% branch coverage. (Configurable per-project via `pyproject.toml`.)

Fail → Phase D: add tests for uncovered branches.

### Gate 7: diff size ceiling

```bash
git diff --stat HEAD | tail -1
```

Pass: total LOC changed < 300.

Fail → STOP. Do NOT continue to gate 8. Invoke `feature-architect` to split remaining work into a follow-up task. Mark this task as `PARTIAL` with a note pointing to the split task. Hand off only the completed portion.

### Gate 8: code-reviewer subagent (ALWAYS)

Spawn `code-reviewer` subagent with isolated context:

Cue: _"spawn the code-reviewer subagent to review staged changes"_

Subagent input:
- `git diff HEAD` (all changes)
- Task spec (description + acceptance criteria)
- ADRs referenced in task

Subagent output: structured review with categories:
- **Blocking**: must fix before handoff
- **Should-fix**: highly recommended
- **Consider**: optional improvements
- **Strengths**: what's done well

Pass: zero Blocking. Zero or addressed Should-fix (either fix or document why not addressed).

Fail (Blocking) → Phase D: address.
Partial (Should-fix unresolved) → Document in handoff.md why not addressed.

### Gate 9: security-auditor subagent (if security-relevant)

Auto-detect security relevance per `references/mutation-policy.md` signals.

If detected, spawn `security-auditor` subagent:

Cue: _"spawn the security-auditor subagent to audit security-relevant changes"_

Subagent input: same as code-reviewer.

Subagent output: security-specific findings categorized by OWASP top-10 plus domain-specific concerns.

Pass: zero unmitigated Critical/High findings. Medium findings documented with mitigation plan.

Fail (Critical/High) → Phase D: address. May trigger backtrack (security issue that requires architectural change).

### Gate 10: pre-commit self-review checklist

Delegate to `pre-commit-self-review-checklist` skill:

Cue: _"walk the pre-commit self-review checklist on the staged diff"_

The skill walks 8 sections (naming, error handling, edge cases, performance, security adjacent, tests adequacy, docs, dependencies).

Pass: all sections checked, no flagged items unresolved.

Fail → Phase D: address.

## All gates passed → Phase E success

Update `tasks.yaml`:
```yaml
- id: t007
  status: READY_FOR_REVIEW  # changed from IN_PROGRESS
```

Append to `tasks/<id>/PROGRESS.md`:

```markdown
## Phase E complete: <ISO timestamp>
- Gate 1 (ruff check): PASS
- Gate 2 (ruff format): PASS
- Gate 3 (mypy strict): PASS
- Gate 4 (pytest): PASS — 47 tests, 47 passed
- Gate 5 (mutmut): PASS — critical mode, mutation score 94% (3/47 survivors, all reviewed and killed)
- Gate 6 (coverage): PASS — changed modules 96% line, 91% branch
- Gate 7 (diff size): PASS — 217 LOC
- Gate 8 (code-reviewer): PASS — 2 Should-fix addressed, 4 Strengths
- Gate 9 (security-auditor): PASS — no Critical/High findings
- Gate 10 (pre-commit checklist): PASS

Proceed to Phase F.
```

Proceed to Phase F.

## Gate failure handling

When a gate fails:

1. **Don't escalate to user yet.** Most failures are fixable in Phase D within 1-3 attempts.
2. **Record specifically what failed.** Not "tests failed" but "test_register_duplicate_email_raises failed with AssertionError: expected DuplicateEmailError, got ValueError on line 42 of src/users/service.py".
3. **Return to Phase D** with the specific failure as the next "test to make pass".
4. **Re-run Phase E from gate 1** after Phase D fix (don't assume earlier gates still pass).

If a gate fails 3+ times consecutively → escalate. Likely indicates:
- Design flaw in Phase B
- Missing test in Phase C that would have caught this earlier
- Backtrack signal upstream

## Subagent invocation pattern

When spawning code-reviewer or security-auditor subagents:

1. Stage the changes: `git add -A` (so `git diff --staged` is meaningful)
2. Spawn subagent with cue phrase. Claude Code's skill system handles the actual sub-Task invocation.
3. Wait for subagent return
4. Parse subagent output for categorized findings
5. Address Blocking immediately (return to Phase D)
6. Document Should-fix decisions in `tasks/<id>/review-decisions.md`
7. Note Consider items for future reflection (Phase F session-dreaming)

Do NOT unstage between subagents — they should see the same diff. Unstaging happens only on Phase D return.

## Anti-patterns in Phase E

- **Skipping gates because "I'm sure"**: each gate exists because skipping it has been historically expensive. Don't.
- **Treating Should-fix as "fix later"**: address or document. Don't ignore.
- **Running gates out of order**: format issues mask real issues; type errors mask test failures; the order is calibrated.
- **Re-running only the failed gate after a fix**: fixes can break earlier gates. Re-run from gate 1.
- **Auto-skip critical mode detection**: if any signal triggers critical, treat as critical even if "feels light".
- **Approving mutmut survivors without justification**: each survivor must have an inline reason. "Equivalent mutant" is the only blanket-accept case.
- **Not staging before subagent**: subagent reads `git diff` against HEAD; unstaged changes get missed.
