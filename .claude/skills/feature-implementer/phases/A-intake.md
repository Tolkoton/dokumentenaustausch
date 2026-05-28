# Phase A — Intake

**Goal**: load the task spec, validate it's ready to implement, build the context needed for Phases B-D.

**Inputs**: tasks.yaml OR direct user request, plus Phase 1-3 artifacts, plus memory files.

**Outputs**: in-context understanding (no file written). Decision: proceed / split / backtrack / refuse.

## Step 1: Determine entry mode

Detect from user phrasing:

- **From tasks.yaml**: user said "take the next task", "implement t007", "next task", "what's the next task"
  - Read `.architecture/tasks.yaml`
  - If task id specified, pick that one
  - Otherwise, find first task with `status: TODO` and all `depends_on` in status `DONE`
  - If none ready, tell user "all unblocked tasks are DONE or in progress; no work to do"

- **Direct from user**: user gave a feature description without task id
  - Synthesize an ad-hoc task spec inline (don't write to tasks.yaml unless user requests)
  - Use minimum required fields: title, description, files_to_touch (guess from request + Phase 3 layout), acceptance_criteria (derive from request)
  - Warn user: "I'll proceed with this as an ad-hoc task. If you want this to be tracked, say so and I'll add it to tasks.yaml."

- **Resume**: user said "continue t007", "resume implementation", "where were we"
  - Read `.architecture/tasks/<id>/PROGRESS.md` if exists
  - Read `.architecture/tasks/<id>/reflections.md` if exists
  - Identify current phase from PROGRESS.md last entry
  - Skip Phases A-B-C if their outputs are already present and valid; pick up at the next pending phase

## Step 2: Validate task readiness

For tasks.yaml entries, check:

- All `depends_on` task IDs exist
- All `depends_on` are in status `DONE` (not `BLOCKED`, not `ABANDONED`, not `READY_FOR_REVIEW`)
- All `files_to_modify` exist on disk (if missing: backtrack signal — Phase 3 inconsistency)
- All `acceptance_criteria` are syntactically parseable (executable test command, curl, file-exists, etc.)
- Task complexity is `S`, `M`, or `L` (if `XL` or absent: refuse, ask for split)

For ad-hoc user requests:
- At least one acceptance criterion must be inferable
- At least one file to touch must be identifiable (otherwise: ask user to specify scope)
- If request implies >5 file changes: warn and propose feature-architect

## Step 3: Size check — escalate to feature-architect?

Hard signals to escalate:
- `complexity: XL`
- More than 5 files in `files_to_modify` + `files_to_create`
- More than 3 entries in `files_to_create`
- More than 10 acceptance criteria
- Description contains "and" connecting independent capabilities (e.g., "Add registration AND login AND password reset")

If any: stop, tell user "This task should be decomposed. Invoking feature-architect to split."

Soft signals (warn but don't auto-escalate):
- Complexity `L` AND any of: touches 3+ different containers, requires new schema migration, depends on >2 prior tasks
- These deserve a "are you sure" pause — user may want to proceed or escalate

## Step 4: Backtrack check

Look for signs the task is broken by upstream:
- Files referenced in `files_to_modify` don't match Phase 3 layout → Phase 3 inconsistency
- Acceptance criteria reference QAS that's not in Phase 1 → Phase 1 gap
- Task in a container not in `components.yaml` → Phase 2 gap

If found: do NOT proceed. Write `.architecture/BACKTRACK-from-task-<id>.md` per `SKILL.md` backtrack rules.

## Step 5: Load context

In this order:

### 5.1 Architecture context (read-only)

```
.architecture/phase-1-system.md         # vision, QASes, user journeys
.architecture/phase-2-architecture.md   # container the task lives in, ADRs that apply
.architecture/phase-3-layout.md         # file conventions, dependency rules
```

Extract specifically:
- Which container this task touches
- Which ADRs apply to this container
- Which QASes this task's acceptance criteria reference (cross-link)
- What dependency rules apply (e.g., "domain cannot import from infrastructure")

### 5.2 Memory files (per-technology + per-project)

Detect technologies:

```python
# Pseudocode for tech detection
detect_technologies(task):
    techs = set()
    # From dependencies
    pyproject = parse_pyproject_toml()
    for dep in pyproject.dependencies:
        techs.add(normalize_dep_name(dep))   # e.g., "fastapi", "pydantic"
    # From imports in files-to-touch
    for f in task.files_to_modify + adjacent_files(task.files_to_create):
        if exists(f):
            for imp in parse_imports(f):
                techs.add(normalize_import(imp))
    # From explicit task tag
    techs.update(task.get("technologies", []))
    # Filter to top-5 most relevant
    return rank_by_relevance(techs)[:5]
```

For each detected technology, read `~/.claude/memory/<tech>/MEMORY.md` if it exists. If file missing, skip silently.

Also always read `.architecture/MEMORY.md` (per-project, if exists).

Inject all loaded MEMORY content into Claude's context as background. Cap total memory injection at ~5K tokens; if larger, take top-3 most-recent lessons per file.

See `references/memory-management.md` for full algorithm.

### 5.3 Existing code

Use `codebase-navigation-strategy` skill (cue: _"navigate to the code I'll touch using grep-before-read pattern"_):

1. `grep -rln <task-keyword>` to locate relevant existing code
2. Read files in `files_to_modify` fully
3. Read 1-2 lines of context around expected insertion points
4. Skim sibling modules for naming conventions

Do NOT read the whole codebase. Concentric circles outward from task scope.

### 5.4 Test fixtures and helpers

Read `tests/conftest.py` at the level where new tests will live. Note available fixtures so Phase C doesn't reinvent them.

## Step 6: Initialize task workspace

```bash
mkdir -p .architecture/tasks/<id>/
```

Create `tasks/<id>/PROGRESS.md` if not exists:

```markdown
# Task <id>: <title>

## Status
- Phase: A (intake)
- Started: <ISO timestamp>
- Last update: <ISO timestamp>

## Context loaded
- Phase 1-3 artifacts: yes/no per file
- Memory files loaded: list of techs
- Files read: list

## Decisions
_(populated through phases)_

## Open questions for user
_(populated when blocked)_
```

Append timestamped notes through subsequent phases.

## Step 7: Approval gate (optional)

For tasks of complexity L, or when user said "be careful": before moving to Phase B, summarize understanding back to user:

> Task understanding for t007:
> - Goal: add `register(email, password)` endpoint
> - Touches: src/users/{models,service,repository}.py, src/api/router.py
> - QASes referenced: QAS-03 (auth brute-force resistance)
> - Boundary models needed: RegisterUserRequest, UserResponse
> - Memory hits: 2 lessons from python-fastapi/MEMORY.md about HTTPException patterns
>
> Proceed to detailed design? (yes / clarify <question> / abort)

For S/M tasks: skip this gate, proceed silently to Phase B. The summary lives in PROGRESS.md.

## Output of Phase A

- Task spec validated and loaded
- All upstream context loaded
- Memory injected
- Workspace initialized
- Decision: PROCEED to Phase B (or REFUSE / SPLIT / BACKTRACK)

## Anti-patterns at intake

- **Skipping memory load**: silently drops cross-project learning. Always read MEMORY.md files even if you "think you know" the tech.
- **Reading the whole codebase**: ACI principle — concentric circles only.
- **Inferring acceptance criteria when ambiguous**: ask user instead of guessing.
- **Proceeding past missing dependencies**: a `BLOCKED` dep means BLOCKED. No "I'll work around it."
- **Treating direct user requests as if they're tasks.yaml**: ad-hoc tasks deserve a warning that they're not tracked.
