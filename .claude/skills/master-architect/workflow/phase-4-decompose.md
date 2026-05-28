# Phase 4 — Task Decomposition

**Goal**: split the design into independently-implementable tasks, each small enough for one Claude Code session to complete with high reliability. Output is `tasks.yaml`, the **only** handoff to the implementation agent.

**Consumes**: `phase-1-system.md`, `phase-2-architecture.md`, `phase-3-layout.md` (all APPROVED).

**Hands off to**: feature-implementer skill (or feature-planner → feature-implementer chain).

## What "approved Phase 4" looks like

A single YAML file `phase-4-tasks.yaml` in the schema from `templates/tasks.yaml`. Plus a brief `phase-4-tasks.md` that documents:
- The decomposition rationale (why these specific cuts)
- The task DAG (which tasks block which)
- Vertical slice strategy (each task should deliver user-visible value, not "create skeleton")

## Decomposition principles (apply in order)

### 1. Vertical slices, not horizontal layers

GOOD task: "Add `register(email, password)` endpoint end-to-end — handler, service, repo, model, tests, migration, docs."

BAD task: "Create all Pydantic models for the user domain." (Horizontal — nothing works after it.)

Each task, when APPROVED + MERGED, leaves the system in a useful state. The exception is the very first scaffolding task (project init), which is unavoidably horizontal.

### 2. One bounded context per task

Phase 2 component boundaries → task boundaries. A task should not span multiple containers from Phase 2.

If a feature genuinely requires changes in 2+ containers, split into:
- Task A: container 1 changes + new public interface
- Task B: container 2 changes consuming container 1's interface

Task B depends on Task A in the DAG.

### 3. Each task fits one Claude Code session

Heuristic: if you imagine reading the task spec aloud, and the description plus relevant files would exceed ~50K tokens, it's too big. Split.

Concrete signals to split:
- Touches >5 files
- Requires >3 new files
- Needs >10 new tests
- Modifies an existing class that's currently >200 lines

### 4. Acceptance criteria are executable

Each task lists 3-7 acceptance criteria expressed as:
- Executable test assertion ("`pytest tests/users/test_register.py::test_happy_path` passes")
- Concrete observation ("`curl POST /register` with valid body returns 201")
- Type/lint check passes ("`mypy src/users` succeeds")
- Build artifact exists ("migration file `<timestamp>_create_users_table.py` present")

NOT acceptance criteria:
- "Code looks clean"
- "Users can register"
- "It works"

Delegate to `tdd-enforcer-python` skill if available — cue: _"verify each task has clear test acceptance criteria following TDD discipline"_.

### 5. Dependencies are explicit

Each task declares `depends_on: [task_id_1, task_id_2]`. The DAG must be acyclic. Master-architect verifies this before approving Phase 4.

### 6. Foundation first

The first 1-3 tasks are foundational: project init, base models, shared kernel, test infrastructure. After foundation, all subsequent tasks should be vertical slices.

## GENERATE step

### BASIC track

For each Phase 1 user journey:
1. Identify the smallest end-to-end vertical slice that delivers a step of the journey
2. Map to Phase 2 containers and Phase 3 file paths
3. Write task spec using `templates/tasks.yaml` schema
4. Identify dependencies (which earlier tasks must complete first)
5. Order into a DAG

Foundational tasks come first (project init, shared models, test setup), then journey-derived tasks in DAG order.

Delegate to `plan-mode-and-task-decomposition` skill if available — cue: _"use plan-mode-and-task-decomposition heuristics to decompose this into vertical slices"_.

### DEEP track

Rare. Use only when:
- The system has >20 tasks (need grouping/phases)
- Tasks have heavy interdependence (need critical-path analysis)
- Multi-team handoff (not the typical solo-dev case)

In those cases, generate decomposition with explicit milestones (group tasks into "Milestone 1: minimal usable system", "Milestone 2: ...") and present milestone-level summary first, then expand.

## CRITIQUE step

Apply `checklists/layout-critique.md` adapted for tasks (the file covers Phase 3-4 since both deal with concrete code-level concerns).

**Required delegations**:
- `tdd-enforcer-python` — _"audit acceptance criteria for TDD-compatibility"_

**Phase 4-specific failure modes**:
- **Horizontal-layer tasks** masquerading as vertical (e.g., "Add models" task with no service or endpoint)
- **Acceptance criteria not executable** (vague language, no concrete check)
- **DAG with cycles** (master-architect verifies algorithmically)
- **Task too big** (>5 files, >3 new files, >10 new tests — split it)
- **Missing dependency**: task X references something task Y must create, but Y is not in `depends_on`
- **Foundation deferred**: project init shows up at task 7 instead of task 1
- **No first-week task**: task 1 should be completable in one session by the user. If task 1 is "Build the auth system", that's not a task, that's a milestone.

## REFINE step

SCOPE-LOCAL: split a task, add a missing dependency, sharpen acceptance criteria.

SCOPE-UPSTREAM (Phase 3): task description references file paths that don't fit the Phase 3 layout → either layout is wrong or task is wrong; usually task description, but check.

SCOPE-UPSTREAM (Phase 2): a task requires a capability not owned by any container → Phase 2 has a gap.

SCOPE-UPSTREAM (Phase 1): a task delivers something not in Phase 1 functional capabilities → scope creep, either expand Phase 1 explicitly or cut the task.

## Hand-off

After Phase 4 APPROVED:
1. The file `.architecture/phase-4-tasks.yaml` exists and is the SINGLE source of truth for what to build
2. The feature-implementer skill takes the next `STATUS: TODO` task with all dependencies APPROVED
3. Master-architect's job is done; if implementer requests architecture changes, that's a backtrack signal to a prior phase

Tell the user explicitly when Phase 4 is APPROVED:
> "Architecture phase complete. Tasks ready at `.architecture/phase-4-tasks.yaml`. To start implementation, in a new session, ask the feature-implementer skill (or feature-planner) to take the first task with `STATUS: TODO`."

## Templates

- `templates/tasks.yaml` — full schema for the tasks file

## What NEVER happens in Phase 4

- Writing actual code
- Modifying any file outside `.architecture/`
- Running tests
- Committing
- Installing packages
- Making decisions that should have been made in Phase 2 or 3 (if needed, BACKTRACK)
