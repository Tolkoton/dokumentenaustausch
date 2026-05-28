# feature-implementer

Per-task implementation skill for Claude Code. Runs a strict 6-phase pipeline (Intake → Detailed Design → Test Design → TDD Loop → Self-Review → Handoff) with hard quality gates. Never auto-commits — final diff is presented to the user, who makes the commit decision.

Companion to `master-architect` (which produces tasks) and `feature-architect` (which splits oversized tasks).

## When to use

The skill auto-triggers when the user asks to:
- "implement task t007"
- "take the next task"
- "implement OAuth2 in /auth"
- "do TDD on this"
- "build the next thing"
- "resume t007"

For anything bigger (system design, splitting tasks), it delegates upward.

## What it does

Per task, runs:

1. **Intake (A)**: validates task, loads architecture + memory + code context
2. **Detailed Design (B)**: applies tactical DDD; designs entities, VOs, boundaries
3. **Test Design (C)**: derives a wide test list from spec (types, errors, branches, invariants)
4. **TDD Loop (D)**: RED → GREEN → REFACTOR per test, with skill-level self-check
5. **Self-Review (E)**: full verification stack — ruff, mypy, pytest, mutmut, coverage, complexity, diff size, code-reviewer subagent, security-auditor (if relevant), pre-commit checklist
6. **Handoff (F)**: presents diff for user commit; session-dreaming to per-tech + per-project MEMORY

Refuses or escalates on:
- Tasks >L → invokes `feature-architect`
- Tasks broken by upstream → BACKTRACK to `master-architect`
- Quick edits / one-liners → not the right scope; user edits directly

## Installation

```bash
# Place at user-level (shared across projects)
cp -r feature-implementer ~/.claude/skills/

# Or project-level (this codebase only)
cp -r feature-implementer .claude/skills/
```

Verify:
```bash
ls ~/.claude/skills/feature-implementer/SKILL.md
```

## Usage

In a project where `master-architect` has produced `.architecture/tasks.yaml`:

```
> Take the next task.
```

Or for ad-hoc work:

```
> Implement a /search endpoint for fulltext search across articles.
```

The skill runs all 6 phases. After Phase F, you'll see a presentation:

```
Task t007 ready for your review.

What was done:
<summary>

Files changed: 7 files (+479 LOC including tests)
Tests: 47 passed, 0 failed, mutation score 94%

Review with:
  git diff --staged

When satisfied, commit with:
  git commit -m "<message>"
```

Then `git commit` when you're satisfied.

## Storage layout

Per task: `.architecture/tasks/<task-id>/`

```
.architecture/tasks/t007/
├── design.md                  # Phase B output
├── test-plan.md               # Phase C output
├── PROGRESS.md                # running log through phases
├── reflections.md             # written after every failed attempt
├── mutation-report.md         # Phase E mutmut summary
├── mutation-survivors.md      # if critical mode + survivors accepted
└── handoff.md                 # Phase F final summary
```

Memory: `~/.claude/memory/<tech>/MEMORY.md` (cross-project per-tech) + `<project>/.architecture/MEMORY.md` (per-project).

## Key design decisions

### Sequential pipeline, not parallel

Phase A → B → C → D → E → F. No skipping unless resuming with prior outputs intact. Each phase produces an artifact for the next.

### Skill-level self-check, not TDD hook

Instead of a Claude Code hook that blocks edits, the skill itself reads `pytest --tb=no -q` before each production-code Edit. If no failing test, refuse. Portable across machines, no hook config needed.

### Wide test design, not fixed count

Test count is derived from spec (types, errors, branches, invariants, security). See `references/test-lens-derivation.md`. A 6-test task and a 30-test task are both correct if derived correctly.

### code-reviewer subagent always

Cheap, catches what self-review misses. No opt-out at Phase E.

### Mutation testing auto-detected as critical/standard

Keywords, paths, imports, QAS refs, container markers — any one signal → critical (≥80% score). Otherwise standard (2-min timeout). See `references/mutation-policy.md`.

### Memory per-technology + per-project

Lessons from each task get classified: tech-general → `~/.claude/memory/<tech>/MEMORY.md` (cross-project); codebase-specific → `<project>/.architecture/MEMORY.md`. Ambiguous → both.

### Never commits

`git commit` is the human checkpoint. The skill stages, tests, reviews, but stops before commit. User reviews diff, then commits.

### 300 LOC ceiling per task

Hard. If approaching, stop and ask `feature-architect` to split remaining work.

## Companion skills (recommended)

These are invoked by feature-implementer per phase. Install for full functionality:

- `master-architect` — produces tasks.yaml; backtrack target
- `feature-architect` — splits oversized tasks
- `karpathy-pre-action-check` — silent-assumption check at Phase B
- `pydantic-v2-conventions` — boundary model verification
- `tdd-enforcer-python` — RED-GREEN discipline at Phase D
- `paranoid-srp-python` — SRP audit at REFACTOR
- `srp-refactor` — refactor heuristics
- `property-based-testing-with-hypothesis` — property selection at Phase C
- `execution-feedback-debugging` — CRITIC at failure ladder Tier 3
- `code-reviewer` (subagent) — Phase E gate
- `security-auditor` (subagent) — Phase E gate when security-relevant
- `pre-commit-self-review-checklist` — final Phase E walkthrough
- `session-dreaming` — Phase F memory distillation
- `progress-file-for-long-tasks` — PROGRESS.md hygiene

Without companion skills, feature-implementer falls back to inline checklists. Quality drops but function remains.

## Layout

```
feature-implementer/
├── SKILL.md                                  # state machine + operational rules
├── README.md                                 # this file
├── phases/
│   ├── A-intake.md
│   ├── B-detailed-design.md
│   ├── C-test-design.md
│   ├── D-tdd-loop.md
│   ├── E-self-review.md
│   └── F-handoff.md
├── references/
│   ├── test-lens-derivation.md               # test count algorithm + worked examples
│   ├── failure-ladder.md                     # GREEN-stuck escalation
│   ├── ddd-task-application.md               # tactical DDD at task scope
│   ├── mutation-policy.md                    # critical mode auto-detection
│   └── memory-management.md                  # per-tech + per-project memory
└── checklists/
    ├── intake-readiness.md
    ├── design-quality.md
    ├── test-completeness.md
    └── pre-handoff.md
```

## Configuration

Project-level config in `pyproject.toml`:

```toml
[tool.feature-implementer]
diff_loc_ceiling = 300
critical_mutation_threshold = 80
standard_mutation_timeout_sec = 120
coverage_line_threshold = 90
coverage_branch_threshold = 85
complexity_max_grade = "B"
```

User-level config in `~/.claude/config.yaml`:

```yaml
feature-implementer:
  memory_token_budget: 5000
  memory_top_n_per_file: 20
  auto_run_code_reviewer: true
  auto_run_security_auditor: true  # auto-detect; this enables auto-spawn
```

## Operational rules (the Iron Laws)

1. Never write production code without a failing test currently in pytest output
2. Never commit
3. Never exceed 300 LOC diff in one task
4. Never proceed to Phase F if any Phase E MUST fails
5. Never modify `.architecture/` artifacts outside `tasks/<id>/` and `tasks.yaml` status
6. Never refactor without all-green state
7. Always write reflection notes after failed attempts
8. Always run code-reviewer subagent at Phase E
9. Always update tasks.yaml status atomically with phase transitions
10. Always do session-dreaming at end of task

## Compatibility

- Claude Code v2.1+
- Python 3.12+ recommended
- Works with poetry, uv, pip-tools, conda, hatch
- Tested with FastAPI, Pydantic v2, SQLAlchemy 2.0, Hypothesis 6+, pytest 8+

## Changelog

### v1.0 (2026-05-12)

- Initial release
- 6-phase pipeline with bundled phase guidance files
- Skill-level TDD self-check (no hook dependency)
- Critical mutation mode auto-detection
- Per-tech + per-project memory layout
- code-reviewer subagent always; security-auditor on detection
- 300 LOC hard ceiling with feature-architect escape
- Backtrack signals to master-architect
