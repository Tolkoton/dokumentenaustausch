# Pre-Handoff Checklist (Phase E)

Master checklist that consolidates all Phase E gates. Apply at end of Phase E before transitioning to Phase F. Every MUST item is a blocker — failure means back to Phase D.

## Gate 1: Static checks

### ruff check
- [ ] **MUST** zero violations on changed lines
- [ ] **MUST** C901 (complexity) passes
- [ ] **MUST** PLR0915 (too many statements) passes
- [ ] **MUST** PLR0912 (too many branches) passes
- [ ] **MUST** PLR0911 (too many returns) passes
- [ ] **MUST** PLR0913 (too many arguments) passes
- [ ] **MUST** project-configured rules pass

Command: `ruff check --select=ALL --ignore=<project-ignores> src/ tests/`

### ruff format
- [ ] **MUST** zero diff after format check
- [ ] **MUST** formatted consistently with project config

Command: `ruff format --check src/ tests/`

## Gate 2: Type checks

### mypy strict
- [ ] **MUST** zero errors on changed files
- [ ] **MUST** strict mode enabled (`mypy --strict`)
- [ ] **MUST** no `# type: ignore` added without inline justification
- [ ] **MUST** no `Any` introduced (must use specific types)

Command: `mypy --strict src/`

## Gate 3: Test execution

### pytest full suite
- [ ] **MUST** 100% green (zero failures, zero errors)
- [ ] **MUST** every skipped test has explicit reason (no silent `xfail` or skip)
- [ ] **MUST** no flaky tests (re-run failing test 3× to verify)

Command: `pytest -q --tb=short`

### pytest with coverage
- [ ] **MUST** changed modules ≥90% line coverage
- [ ] **MUST** changed modules ≥85% branch coverage
- [ ] **MUST** no coverage regression in unchanged modules

Command: `pytest --cov=src --cov-report=term --cov-report=json`

## Gate 4: Mutation testing

### Mode detection (per `references/mutation-policy.md`)
- [ ] **MUST** correctly detected critical vs standard mode
- [ ] **MUST** detection rationale recorded in `tasks/<id>/mutation-report.md`

### Critical mode (if detected)
- [ ] **MUST** mutation score ≥80% on changed modules
- [ ] **MUST** every surviving mutant reviewed
- [ ] **MUST** every accepted survivor has one-line justification in `tasks/<id>/mutation-survivors.md`

### Standard mode
- [ ] **SHOULD** mutation score ≥50% (informational)
- [ ] **MUST** mutation report saved regardless of score

Command: `mutmut run --paths-to-mutate=<changed-modules> -- pytest -x -q`

## Gate 5: Complexity

### Cyclomatic complexity
- [ ] **MUST** every function has CC ≤ 8 (Xenon grade B max)
- [ ] **MUST** module average is grade A (CC average ≤ 5)

Command: `xenon --max-absolute B --max-modules A --max-average A src/`

### Cognitive complexity
- [ ] **MUST** every function has cognitive complexity ≤ 15

Command: `complexipy src/`

### Dead code
- [ ] **MUST** zero unused code introduced
- [ ] **MUST** any pre-existing dead code on changed files is removed

Command: `vulture src/ tests/`

## Gate 6: Diff size

### Lines of code ceiling
- [ ] **MUST** total LOC changed < 300 (production code only; tests don't count toward ceiling)
- [ ] **SHOULD** under 200 for typical tasks

Command: `git diff --stat HEAD -- 'src/**'` (production only)

### File count
- [ ] **MUST** ≤7 files touched total (including tests)
- [ ] **MUST** ≤5 production files touched

### Hunks per file
- [ ] **MUST** each file has ≤5 logical hunks (per `laser-change-discipline`)

## Gate 7: Code-reviewer subagent (ALWAYS)

### Invocation
- [ ] **MUST** staged changes presented to subagent via `git diff --staged`
- [ ] **MUST** task spec + relevant ADRs provided as context

### Findings handling
- [ ] **MUST** zero Blocking findings (or all addressed in Phase D revision)
- [ ] **MUST** every Should-fix either addressed OR documented with rationale
- [ ] **SHOULD** Consider items noted for Phase F session-dreaming

## Gate 8: Security-auditor subagent (IF security-relevant)

### Trigger detection
- [ ] **MUST** security relevance auto-detected per `references/mutation-policy.md`

### If triggered
- [ ] **MUST** subagent invoked
- [ ] **MUST** zero Critical/High findings (or all addressed)
- [ ] **MUST** Medium findings documented with mitigation plan

### If not triggered
- [ ] **MUST** "not security-relevant" with rationale noted in mutation-report.md

## Gate 9: Pre-commit self-review

### Walk all 8 sections of pre-commit-self-review-checklist
- [ ] **MUST** Section 1: Naming (clear, consistent, no abbreviations except domain terms)
- [ ] **MUST** Section 2: Error handling (specific exceptions, useful messages, no swallowing)
- [ ] **MUST** Section 3: Edge cases (None, empty, boundary values all tested)
- [ ] **MUST** Section 4: Performance (no obvious O(n²) where O(n) possible)
- [ ] **MUST** Section 5: Security-adjacent (no logging of secrets, no string formatting of SQL, etc.)
- [ ] **MUST** Section 6: Tests adequacy (cover happy + error + boundary + property + integration as relevant)
- [ ] **MUST** Section 7: Docs (public APIs have docstrings; non-obvious decisions have comments)
- [ ] **MUST** Section 8: Dependencies (no new dep introduced silently; if introduced, has justification)

## Gate 10: Architectural conformance

### Cross-check with Phase 1-3
- [ ] **MUST** no Phase 3 dependency rule violated (no forbidden imports)
- [ ] **MUST** code lives in the container assigned in design.md
- [ ] **MUST** ADR references in design.md are still consistent with code
- [ ] **MUST** QAS references in design.md are met by code (e.g., if QAS says "<200ms latency", verify)

## Gate 11: Reflection notes complete

### Process artifacts
- [ ] **MUST** `tasks/<id>/PROGRESS.md` has entries for each phase transition
- [ ] **MUST** `tasks/<id>/reflections.md` has notes for each failed attempt (or "no failures" if perfect)
- [ ] **MUST** all open questions raised during phases B-D are resolved (no TODOs left)

## Gate 12: Tasks.yaml update

### Status
- [ ] **MUST** task status updated to `READY_FOR_REVIEW` (only after all above gates PASS)
- [ ] **MUST** ready_for_review_at timestamp set
- [ ] **MUST NOT** task auto-marked `DONE` (user does that on commit)

## Final pass before Phase F

- [ ] All MUST items checked PASS
- [ ] Any Should-fix items documented
- [ ] PROGRESS.md updated with Phase E completion
- [ ] No accumulated debt items left for Phase F
- [ ] Ready to write handoff.md and present to user
