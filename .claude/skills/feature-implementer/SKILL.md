---
name: feature-implementer
description: Implements one task from .architecture/tasks.yaml or from direct user request, using strict TDD discipline (RED, GREEN, REFACTOR) with wide test design, paranoid SRP enforcement, Pydantic boundaries, and a multi-stage failure ladder when stuck. Use this skill WHENEVER the user asks to "implement this feature", "code this up", "take the next task", "implement task tN", "build the next thing", "do TDD on this", "write the code for X", "finish what the architect started", or any per-feature implementation work. Also use when continuing implementation ("resume task", "continue t007"). DO NOT use for high-level design (that's master-architect), for splitting too-large tasks (that's feature-architect), or for ad-hoc one-line fixes.
---

# Feature Implementer

Per-task implementation skill. Runs a strict 6-phase pipeline (Intake → Detailed Design → Test Design → TDD Loop → Self-Review → Handoff) with hard quality gates. Never auto-commits — staged diff is presented to the user, who makes the commit decision.

## When to invoke

**Default trigger**: user wants to build a feature, implement a task, or write code. Entry modes:

- **From tasks.yaml** (`"take the next task"`, `"implement t007"`) → read task, validate dependencies, proceed
- **Direct from user** (`"implement OAuth2 in /auth"`, `"add a /search endpoint"`) → synthesize an ad-hoc task spec, then proceed normally
- **Resume** (`"continue t007"`, `"resume implementation"`) → read `.architecture/tasks/<id>/PROGRESS.md`, continue from last checkpoint

## Refusal modes

Refuse and redirect when:
- Task is obviously >L complexity (>5 files, >3 new files, >10 new tests) → invoke `feature-architect` to split
- Task references files outside Phase 3 layout → backtrack signal to master-architect
- User asks for "quick edit" / one-liner / typo fix → not a feature, just edit directly without the pipeline
- User asks for project-level design → invoke `master-architect` instead

## State and storage

Per-task workspace at `.architecture/tasks/<task-id>/`:

```
.architecture/
├── tasks.yaml                          # Source of truth (from master-architect)
└── tasks/
    └── t007/                            # Per-task folder
        ├── design.md                    # Phase B output: detailed design
        ├── test-plan.md                 # Phase C output: wide test list
        ├── PROGRESS.md                  # Phase D running log
        ├── reflections.md               # Reflexion notes after failures
        └── handoff.md                   # Phase F summary for user
```

Code goes into the project's `src/` per Phase 3 layout. Tests into `tests/`. Master-architect's `.architecture/` folder is read-only for feature-implementer except for the per-task subfolder above and `tasks.yaml` status updates.

## The pipeline (6 phases, sequential)

```
┌─────────────────────────────────────────────────────────────────┐
│ A. INTAKE                                                        │
│    - Load task spec (tasks.yaml or user request)                 │
│    - Validate dependencies DONE                                  │
│    - Size check (refuse → feature-architect if >L)               │
│    - Load context: Phase 1-3 artifacts, MEMORY.md (per-tech)     │
│    - Load relevant code (codebase-navigation-strategy)           │
│    - See phases/A-intake.md                                      │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ B. DETAILED DESIGN ("the DDD phase")                             │
│    - Think hard. Apply tactical DDD per task scope.              │
│    - Design: public surface, signatures, error types             │
│    - Decide: boundary Pydantic models, internal dataclasses      │
│    - Run karpathy-pre-action-check                               │
│    - Output: .architecture/tasks/<id>/design.md                  │
│    - Check design.md against checklists/design-quality.md        │
│    - See phases/B-detailed-design.md                             │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ C. TEST DESIGN ("wide tests")                                    │
│    - Derive test count logically from spec (not fixed number)    │
│    - 6 categories: happy / boundary / error / property /          │
│                    integration / security                         │
│    - Consult references/test-lens-derivation.md                  │
│    - Delegate property pattern selection to                      │
│      property-based-testing-with-hypothesis                      │
│    - Output: .architecture/tasks/<id>/test-plan.md               │
│    - Check test-plan.md against checklists/test-completeness.md  │
│    - See phases/C-test-design.md                                 │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ D. TDD LOOP (per test from test-plan.md, in declared order)      │
│    For each test:                                                 │
│      RED:      write failing test, verify failure reason         │
│      GREEN:    minimum production code; testmon scope            │
│      REFACTOR: paranoid SRP applied                              │
│    Self-check: never edit production without a failing test      │
│    Diff size tracked (300 LOC ceiling)                           │
│    If stuck on GREEN → failure ladder (references/failure-ladder.md)│
│    Reflexion mandatory after each failed attempt                 │
│    See phases/D-tdd-loop.md                                      │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ E. SELF-REVIEW (verification stack)                              │
│    MUST all pass before proceeding to F:                         │
│      - ruff check                                                │
│      - mypy --strict                                             │
│      - pytest full suite                                         │
│      - mutmut on changed modules (critical mode if detected)     │
│      - coverage delta (no regression)                            │
│      - complexity check (PLR0915, C901)                          │
│      - diff size <300 LOC                                        │
│      - code-reviewer subagent (always)                           │
│      - security-auditor subagent (if security-relevant)          │
│    Any MUST fails → back to Phase D                              │
│    See phases/E-self-review.md                                   │
└────────────────────────┬────────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ F. HANDOFF                                                       │
│    - Update tasks.yaml: status TODO → READY_FOR_REVIEW           │
│    - Present diff to user with summary                           │
│    - Session-dreaming: write lessons to per-tech + per-project   │
│      MEMORY.md files (references/memory-management.md)           │
│    - Suggest next task in DAG                                    │
│    - DO NOT git commit                                           │
│    - See phases/F-handoff.md                                     │
└─────────────────────────────────────────────────────────────────┘
```

## Failure ladder (when GREEN won't come)

Per `references/failure-ladder.md`:

```
3× simple fix attempts (read traceback, fix obvious)
   ↓ if not green AND no progress
2× Self-Refine attempts (regenerate impl with critique in context)
   ↓ if not green AND no progress
1+× CRITIC attempts (capture execution trace, debug from trace)
   ↓ if not green AND no progress
3× KB algorithm attempts (consult master-architect/algorithms.md)
   ↓ if not green AND no progress for 3 consecutive
ESCALATE to user with reflections.md and structured analysis
```

**"Progress" formal definition**: at least one of
- Failing test count decreased
- Failure mode changed (different exception, different line, different message)
- Coverage delta increased
- Failure area narrowed (assertion moved from outer to inner scope)

Same error after attempt = ZERO progress. 3 consecutive zero-progress attempts → automatic tier escalation.

## Backtrack signals (escalate to master-architect)

When implementation reveals a problem in upstream architecture:

1. Acceptance criteria genuinely impossible given current Phase 2/3
2. Task requires files/modules not in Phase 3 layout
3. Phase 1 QAS missed a critical concern that surfaces only at code level

Action:
1. Pause implementation
2. Write `.architecture/BACKTRACK-from-task-<id>.md` describing:
   - What was attempted
   - What architectural constraint blocks completion
   - Which Phase (1, 2, or 3) needs revision
3. Update `tasks.yaml` status: TODO → BLOCKED
4. Ask user to either: revise architecture (re-invoke master-architect from broken phase) OR abandon task

Do NOT continue implementation past a confirmed backtrack signal.

## Self-check rules (replacing TDD Guard hook)

Since the user opted for skill-level self-check (no hook), feature-implementer enforces TDD discipline by reading pytest output before each production-code Edit:

**Before EVERY edit to `src/`**:
1. Run `pytest --tb=no -q | tail -5` to see current state
2. If output shows `passed` only (no failures, no errors) → REFUSE edit, "must write a failing test first"
3. If output shows `failed` (≥1 failing test) → ALLOW edit
4. After edit, re-run to confirm intent (still RED if still in RED phase; GREEN if implementation complete)

Exception: pure refactoring during REFACTOR step is allowed in fully-green state, but only if:
- All tests currently pass
- The refactor doesn't change any public interface
- After refactor, all tests still pass

## Memory layout (per-tech + per-project)

Two memory layers, both read at Phase A intake, both written at Phase F handoff:

```
~/.claude/memory/                       # User-level, cross-project per technology
├── datev/MEMORY.md
├── python-fastapi/MEMORY.md
├── pydantic-v2/MEMORY.md
├── postgres/MEMORY.md
├── sqlalchemy/MEMORY.md
└── ...

<project_root>/.architecture/MEMORY.md  # Per-project, this codebase's quirks
```

Technology detection per task: read `pyproject.toml` top-level deps + imports in files-to-touch. Top 5 most-relevant → load each `MEMORY.md`. See `references/memory-management.md` for details.

## Mutation-testing policy

Mutmut runs in Phase E on changed modules. Mode auto-detected via signals:

**Critical mode** (no timeout, mutation score ≥80% required) when ANY of:
- Task keywords: `auth`, `password`, `payment`, `money`, `tax`, `invoice`, `decimal`, `audit`, `pii`, `gdpr`, `crypto`, `signature`, `permission`, `role`, `acl`
- Files touched match: `*/auth/*`, `*/security/*`, `*/billing/*`, `*/payments/*`, `*/accounts/*`
- Imports detected: `Decimal`, `Money`, `cryptography`, `hashlib`, `secrets`, `jwt`
- Phase 1 QAS reference is in category: security, integrity, audit, financial
- tasks.yaml has explicit `criticality: critical`

**Standard mode** (2-min timeout, partial accepted) otherwise.

See `references/mutation-policy.md`.

## Operational rules (NEVER violate)

1. **Never write production code without a failing test currently in pytest output.** Enforced via skill-level self-check.
2. **Never commit.** Git operations are read-only (`git status`, `git diff`, `git log`). User commits.
3. **Never exceed 300 LOC diff in one task.** Hard ceiling. If approached, stop and propose split to feature-architect.
4. **Never proceed to Phase F if any MUST gate in Phase E fails.** Back to Phase D.
5. **Never modify `.architecture/` artifacts outside `tasks/<id>/`** or `tasks.yaml` status field. Master-architect owns the rest.
6. **Never refactor without all-green state.** REFACTOR step requires GREEN entry.
7. **Always write reflection notes after failed attempts.** `tasks/<id>/reflections.md`. Mandatory.
8. **Always run code-reviewer subagent at Phase E.** Cheap insurance, no exceptions.
9. **Always update tasks.yaml status** atomically with phase transitions (READY_FOR_REVIEW only after E passes).
10. **Always do session-dreaming at end of task** to MEMORY.md files. Skipping silently drops learning.

## Phase contracts

| Phase | Reads | Writes | Quality gate |
|-------|-------|--------|--------------|
| A — Intake | tasks.yaml, Phase 1-3 artifacts, MEMORY.md files, code in files_to_touch | _(in-context only)_ | checklists/intake-readiness.md |
| B — Detailed Design | Phase A context | `tasks/<id>/design.md` | checklists/design-quality.md |
| C — Test Design | Phase A+B context, references/test-lens-derivation.md | `tasks/<id>/test-plan.md` | checklists/test-completeness.md |
| D — TDD Loop | test-plan.md (one test at a time) | `tests/**`, `src/**`, `tasks/<id>/PROGRESS.md`, `tasks/<id>/reflections.md` | All tests in test-plan green |
| E — Self-Review | Diff, code, test results | _(in-context only; updates tasks.yaml status)_ | checklists/pre-handoff.md (all MUST) |
| F — Handoff | All prior outputs | `tasks/<id>/handoff.md`, `~/.claude/memory/*/MEMORY.md`, `.architecture/MEMORY.md`, tasks.yaml | None — terminal |

## Delegation map

Master-architect uses `delegation.md` for this map. Feature-implementer's equivalent:

| Phase × moment | Delegate to | Cue phrase | Required? |
|-----------|-------------|------------|-----------|
| B Design | `karpathy-pre-action-check` | "run pre-action check on this design" | always |
| B Design | `pydantic-v2-conventions` | "verify boundary models follow Pydantic conventions" | when boundary touched |
| C Test Design | `property-based-testing-with-hypothesis` | "select Hypothesis patterns for these invariants" | always |
| D TDD Loop | `tdd-enforcer-python` | "enforce TDD discipline on this RED-GREEN cycle" | always |
| D Refactor | `paranoid-srp-python` | "audit this for SRP violations" | when function >20 lines |
| D Refactor | `srp-refactor` | "apply srp-refactor heuristics" | when module organization unclear |
| D Stuck | `execution-feedback-debugging` | "apply CRITIC discipline to debug this failure" | failure ladder tier 3 |
| E Review | `code-reviewer` | "spawn code-reviewer subagent on staged diff" | always |
| E Review | `security-auditor` | "spawn security-auditor subagent on changed code" | critical mode (auto-detect) |
| E Review | `pre-commit-self-review-checklist` | "walk pre-commit-self-review checklist" | always |
| A-F Memory | `progress-file-for-long-tasks` | "update progress file for this task" | always at phase boundaries |
| F Handoff | `session-dreaming` | "distill lessons from this task to MEMORY files" | always |

See individual `phases/*.md` files for full delegation context per phase.

## What feature-implementer never does

- Write code without a failing test (TDD Guard self-check)
- Commit code (`git commit` is human checkpoint)
- Skip Phase B or C ("just code it up" is the path to backtracking later)
- Cross 300 LOC in one task
- Pretend a flaky test is fine (flake = bug; investigate or quarantine with explicit reason)
- Modify other tasks' work (each task is atomic)
- Touch `.architecture/phase-{0..4}-*.md` (master-architect's territory)
- Auto-promote task to DONE (only user commit can DONE a task)
- Run pre-commit hooks that aren't documented in the project
- Install new dependencies without explicit user request

## Compatibility

- Claude Code v2.1+
- Python 3.12+ assumed (skill is Python-flavored)
- Requires `master-architect` skill installed if backtracking is to function fully
- Requires `feature-architect` skill installed if oversized tasks may arrive
- Works without companion skills (falls back to inline checklists) but quality drops
