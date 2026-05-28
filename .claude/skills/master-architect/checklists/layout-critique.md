# Phase 3 / 4 — Code Layout and Task Decomposition Critique Checklist

Apply during CRITIQUE step of Phase 3 (layout) and Phase 4 (tasks). The two are tightly related — bad layout produces bad tasks. Use the relevant subsections.

## ─── PHASE 3 (Layout) ───

### Tree structure

- [ ] Top-level dirs are minimal (typically: `src/`, `tests/`, `docs/`, `pyproject.toml`, optional: `scripts/`, `migrations/`, `infra/`, `.architecture/`)
- [ ] `src/` layout is used (not flat package at root) for Python projects ≥3 modules
- [ ] Project package name matches `pyproject.toml` `name` field
- [ ] No top-level dir is a single file pretending to be a folder

### Per-container layout

- [ ] Each Phase 2 container has a clear folder home in the tree
- [ ] Container name in Phase 2 matches folder name in Phase 3 (or rename is justified)
- [ ] Within each container, files are organized by **role** not **type** (per `workflow/phase-3-layout.md`)
- [ ] Each folder has at most ~10 immediate files (split if more — see dependency rule)
- [ ] Folders don't nest deeper than 3 levels under `src/<package>/` without strong justification

### Module-by-module spec

- [ ] At least the "notable" modules are specified (those owning >1 class or doing >1 thing)
- [ ] Each notable module's spec includes: what it owns / what it exposes / what it imports / test file
- [ ] No module spec is longer than 3 sentences (longer = SRP violation; split the module)

### Naming conventions

- [ ] File naming convention is stated (e.g., `snake_case.py`, test files `test_<module>.py`)
- [ ] Class naming convention is stated
- [ ] Abstract base class naming is stated (`Base<Name>` vs `<Name>Base` vs `Abstract<Name>` — pick one)
- [ ] Constants naming is stated (UPPER_SNAKE)
- [ ] Module-private naming convention (leading underscore for module-private)

### Dependency rules

- [ ] Dependency direction is explicit (e.g., "domain → ports → adapters", or "app → infrastructure")
- [ ] At least one example forbidden import is stated (e.g., "`domain` MUST NOT import from `infrastructure`")
- [ ] Tooling to enforce is named (e.g., `import-linter`, `pydeps`, custom CI check)
- [ ] Cross-cutting modules (`core/`, `shared/`) have explicit "what's allowed in here" rule

### Tests colocation

- [ ] Test folder structure mirrors source structure
- [ ] Test naming convention is consistent with code naming convention
- [ ] Distinction between unit / integration / e2e tests is in folder structure
- [ ] Fixtures live in `conftest.py` files at appropriate scope

### SRP at module level (paranoid-srp delegation)

- [ ] No module file is doing >1 thing (`users/everything.py` is a red flag)
- [ ] Public exports per module are minimal — at most one main class/function plus its companions
- [ ] No "utils.py" without scope (utils dump = SRP failure; either `<topic>_utils.py` or remove)

### Boundary models (pydantic-v2-conventions delegation)

- [ ] Pydantic models live at the boundary they cross
- [ ] No model file is shared across containers (each container owns its public models)
- [ ] Internal domain types (not crossing boundaries) are dataclasses or plain classes, not Pydantic

### Cross-cutting homes

- [ ] Auth has a clear folder home (typically `<package>/auth/` or `<package>/core/auth.py`)
- [ ] Logging configuration has a home
- [ ] Error types have a home (typically `<package>/core/errors.py`)
- [ ] Configuration has a home (typically `<package>/config.py` with Pydantic Settings)

### Phase 2 consistency

Flags trigger SCOPE-UPSTREAM (Phase 2):

- [ ] Every Phase 2 container has a folder representation
- [ ] Every dependency rule in Phase 3 is consistent with Phase 2 container dependencies
- [ ] No folder represents a concept not in Phase 2 (= scope creep)
- [ ] No Phase 2 container has been silently merged or split in Phase 3

### Final pass (Phase 3)

- [ ] Tree could be created by `mkdir -p` and `touch` commands directly from this document
- [ ] A new contributor could navigate to any feature based on Phase 3 alone
- [ ] No open question would block Phase 4 task writing

## ─── PHASE 4 (Tasks) ───

### Task granularity

- [ ] Every task is a vertical slice (delivers user-visible value when merged)
- [ ] Exception is the first 1-3 foundational tasks (project init, shared kernel, test setup)
- [ ] No task touches >5 files (or has explicit justification why)
- [ ] No task introduces >3 new files (or has explicit justification)
- [ ] No task requires >10 new tests
- [ ] No task description is longer than ~30 lines

### Acceptance criteria

- [ ] Every task has 3-7 acceptance criteria
- [ ] Every criterion is executable or directly observable (test command, curl, file presence, type-check, lint)
- [ ] No criterion uses vague language ("works", "clean", "complete")
- [ ] Tests-as-criteria reference test file paths, not test functions yet to be written

### TDD compatibility (tdd-enforcer delegation)

- [ ] Each task has at least one failing-test criterion (the test that the task's implementation makes pass)
- [ ] Tests can be written before implementation (RED) — criteria don't require implementation to exist
- [ ] Test files are at the path predicted by Phase 3 conventions

### Dependency DAG

- [ ] Every task lists `depends_on:` (empty list is allowed for the foundational task)
- [ ] DAG is acyclic (verify algorithmically or by inspection)
- [ ] Dependencies are real (task X needs something task Y produces, not "X feels like Y comes first")
- [ ] No "ghost dependencies" (X depends on Y but doesn't actually use anything Y produces)

### Foundation tasks

- [ ] Task 1 is foundational (project init: `pyproject.toml`, `src/` skeleton, `.gitignore`, basic CLAUDE.md)
- [ ] Task 1 can be completed in ≤30 minutes by an implementer
- [ ] Task 1 leaves a runnable (if empty) project
- [ ] Subsequent foundational tasks (shared kernel, test infrastructure) are explicitly marked

### Vertical-slice tasks

- [ ] Each vertical slice references files from Phase 3 layout
- [ ] Each vertical slice references at least one Phase 1 user journey or capability
- [ ] Each vertical slice respects Phase 3 dependency rules
- [ ] Each vertical slice modifies code in only one or two containers (cross-container = split into chained tasks)

### Karpathy pre-action checks

- [ ] **Silent assumptions**: every task assumes what it actually needs (don't say "use the database" if database setup isn't in dependencies)
- [ ] **Over-complication**: no task is gold-plated. Acceptance criteria match the minimum useful slice.
- [ ] **Unrequested scope**: no task implements something not traceable to Phase 1-3

### Phase 3 consistency

Flags trigger SCOPE-UPSTREAM (Phase 3):

- [ ] Every task's file paths exist in Phase 3 layout (or are clearly being created by the task)
- [ ] No task implies a layout not matching Phase 3
- [ ] Tasks respect Phase 3 dependency rules (no task imports forbidden)

### Phase 2 consistency

Flags trigger SCOPE-UPSTREAM (Phase 2):

- [ ] No task implies a container not in Phase 2
- [ ] No task crosses container boundaries without explicit dependency on the boundary-establishing task

### Phase 1 consistency

Flags trigger SCOPE-UPSTREAM (Phase 1):

- [ ] No task delivers a capability not in Phase 1 functional capabilities
- [ ] Task ordering supports building toward Phase 1 user journeys

### Final pass (Phase 4)

- [ ] An implementer could pick up task 1 with no clarifying questions
- [ ] An implementer could pick up the second task in DAG order with no clarifying questions
- [ ] tasks.yaml is parseable as YAML (you can verify with `python -c "import yaml; yaml.safe_load(open('phase-4-tasks.yaml'))"`)
- [ ] Total task count is reasonable for the scope (typically 8-40; outside = either too coarse or too fine)
