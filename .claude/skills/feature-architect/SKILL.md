---
name: feature-architect
description: Decomposes a single oversized or fuzzy task into a DAG of smaller vertical-slice sub-tasks that fit feature-implementer's complexity ceiling. Use this skill WHENEVER feature-implementer encounters a task too big to complete in one session (more than 5 files, more than 3 new files, more than 10 new tests, or complexity L plus), or when the user explicitly says "split this task", "decompose this feature", "this task is too big", "break t007 into sub-tasks", "help me chunk this", or similar. Updates .architecture/tasks.yaml so that the original task is marked SPLIT_INTO, sub-tasks added with parent reference and proper DAG dependencies. DO NOT use for project-level decomposition (that's master-architect Phase 4), for one-off implementations, or when the original task is already S or M complexity.
---

# Feature Architect

Single-task decomposer. When feature-implementer encounters a task too large or too fuzzy to handle in one session, this skill applies Phase 4 decomposition rules (from master-architect) to that ONE task, producing a DAG of vertical-slice sub-tasks.

Scope is intentionally narrow: one task in, N sub-tasks out. Does not redesign the system, does not modify architecture, does not touch code.

## When to invoke

Explicit triggers (user phrasing):
- "split task t007"
- "decompose this feature"
- "this task is too big"
- "break it into smaller pieces"
- "chunk t007"
- "I need this task in smaller steps"

Implicit triggers (from feature-implementer's Phase A intake):
- Task has `complexity: XL`
- Task touches >5 files in `files_to_modify + files_to_create` combined
- Task creates >3 new files (`files_to_create`)
- Task has >10 acceptance criteria
- Task description contains independent capabilities joined by "and" / "plus" (e.g., "Add registration AND login AND password reset")

Implicit triggers from feature-implementer at later phases:
- 300 LOC ceiling reached mid-task → split remaining work
- Test plan exceeds ~40 tests → likely over-scoped

## What it does NOT do

- Project-level decomposition (that's `master-architect` Phase 4)
- Re-design containers, ADRs, or architecture (would be backtrack to `master-architect` Phase 2)
- Write code (`feature-implementer`'s job)
- Re-prioritize the backlog (user decides task order outside the DAG)
- Combine tasks (only splits)

## Decomposition principles

Apply Phase 4 vertical-slice rules from master-architect:

1. **Vertical slices, not horizontal layers**: each sub-task ships end-to-end behavior (e.g., "Add user registration storage + service + endpoint" not "Add all user storage" + "Add all user services" + "Add all user endpoints")
2. **One acceptance criterion family per sub-task**: sub-task t007a addresses ac1+ac2 (related); sub-task t007b addresses ac3+ac4 (related but different).
3. **DAG with explicit dependencies**: sub-tasks have `depends_on` pointing at prior sub-tasks where genuine dependency exists. Avoid artificial sequencing.
4. **Each sub-task fits S or M complexity**: target <200 LOC code, <15 tests, ≤3 files touched.
5. **Executable independently**: a sub-task can be tested in isolation (with stubs for dependencies if needed).

See `decomposition-heuristics.md` for the patterns.

## Process

### Step 1: Read parent task

Load the task from `.architecture/tasks.yaml`. Read:
- Title and description
- All acceptance criteria
- All files (modify + create)
- All dependencies (these become the first sub-task's dependencies)
- Any QAS references
- Any ADR references

### Step 2: Identify natural splits

Look for splitting signals in the task:

**Capability splits** (most common):
- "Add registration AND login AND password reset" → 3 sub-tasks (one per capability)
- "Implement CRUD for X" → 4 sub-tasks (Create, Read, Update, Delete)

**Layer splits** (use carefully — verify vertical):
- Big endpoint task with new domain + new persistence + new API → 3 sub-tasks BUT each must produce some testable behavior
- Don't do "model + service + endpoint" as 3 sub-tasks; the model alone has no behavior. Combine into "minimal happy-path through all layers" first, then add capabilities.

**Path splits**:
- "Happy path + error handling + edge cases" → sometimes valid but usually means under-thought; prefer "minimum working then enhanced"

**QAS splits**:
- Functional behavior in one task + performance/security hardening in another

**Phase splits**:
- "Build it" then "instrument it" then "harden it" — only for genuinely separable work

### Step 3: Apply heuristics

See `decomposition-heuristics.md`. For each candidate split, ask:

- Does sub-task A produce behavior visible to user/system?
- Can sub-task A be tested without sub-task B existing?
- Is sub-task B genuinely blocked by A, or could they run parallel?
- Is each sub-task within S or M complexity?

If yes to all → valid split.

### Step 4: Construct sub-tasks

For each sub-task, fill out the template from `sub-task-template.md`. Required fields:

```yaml
- id: t007a                        # Original task's id + suffix letter
  parent: t007                     # Reference to parent
  order: 1                         # Order within siblings (1, 2, 3...)
  title: "Register endpoint: minimal happy path"
  description: |
    Implement POST /register with successful user creation only.
    Defer duplicate-detection and password-policy validation to t007b.
  complexity: M
  status: TODO
  files_to_modify:
    - src/api/router.py
  files_to_create:
    - src/users/service.py
    - src/users/repository.py
    - src/users/models.py
    - tests/unit/users/test_service.py
    - tests/integration/users/test_register_happy.py
  depends_on: [t001, t002]         # Inherited from parent's deps
  acceptance_criteria:
    - "pytest tests/unit/users/test_service.py::test_register_happy_path passes"
    - "pytest tests/integration/users/test_register_happy.py::test_post_register_returns_201 passes"
    - "curl -X POST /register with valid body returns 201"
  qas_refs: []
  adr_refs: [ADR-002, ADR-007]
```

### Step 5: Sequence DAG

For sub-tasks with genuine dependencies:

```yaml
- id: t007b
  parent: t007
  order: 2
  depends_on: [t007a, t001, t002]  # t007a is new dependency
  title: "Register endpoint: duplicate-email rejection"
  ...
```

Verify the DAG is acyclic. No circular deps among siblings.

### Step 6: Update tasks.yaml

```yaml
# Original task: mark SPLIT_INTO
- id: t007
  status: SPLIT_INTO
  split_into: [t007a, t007b, t007c]
  split_at: "2026-05-12T16:30:00Z"
  # Keep all original fields for reference

# Add new sub-tasks at the end of the list (or grouped after parent)
- id: t007a
  parent: t007
  ...
- id: t007b
  parent: t007
  ...
- id: t007c
  parent: t007
  ...
```

### Step 7: Notify and hand back

Output to user:

```
Split t007 into 3 sub-tasks:

  t007a (M): Register endpoint: minimal happy path
            depends_on: [t001, t002]
            Files: 5 (4 new, 1 modified)
            Est tests: ~8

  t007b (M): Register endpoint: duplicate-email rejection
            depends_on: [t007a]
            Files: 2 (modify only)
            Est tests: ~5

  t007c (S): Register endpoint: password policy enforcement
            depends_on: [t007a]
            Files: 2 (modify only)
            Est tests: ~6

Original t007 marked SPLIT_INTO. To start: "take the next task" or "implement t007a".
```

Then exit. feature-architect's work is done.

## Refusal cases

- **Task is already S complexity**: refuse, suggest just implementing it
- **Task is already M complexity**: warn but allow split if user insists (M tasks can occasionally benefit from split, e.g., to parallelize)
- **Task complexity is unclear**: ask user "is this 1 day, 3 days, or a week of work?" — calibrate
- **No natural split available** (truly atomic task): tell user the task can't be cleanly split; suggest revisiting Phase 2 architecture if the task is genuinely too big to fit one session

## Operational rules

1. Never split a task into MORE than 5 sub-tasks. If more needed, the parent task is mis-conceived — back to master-architect.
2. Never split into less than 2 sub-tasks. If only 1, no split needed.
3. Always write each sub-task to be S or M complexity.
4. Always maintain DAG acyclicity.
5. Always preserve QAS and ADR references on each sub-task as relevant.
6. Always update parent task status to SPLIT_INTO (not DONE, not ABANDONED).
7. Never modify acceptance criteria semantics — sub-tasks together must cover all parent's criteria.
8. Never touch code, only tasks.yaml.

## Output artifacts

- Updated `.architecture/tasks.yaml` (parent SPLIT_INTO, sub-tasks added)
- Optional: `.architecture/tasks/<parent-id>-split.md` documenting the rationale for the split (useful for retrospect)

## Companion skills

Invoked by feature-architect:

- Reads `master-architect/phases/4-task-decomposition.md` for the original Phase 4 rules
- Reads `master-architect/references/madr-format.md` if generating a split rationale ADR

Invokes:

- `feature-implementer` to actually do the work on each sub-task (after split)

## Compatibility

- Claude Code v2.1+
- Requires `master-architect` to have produced `.architecture/tasks.yaml`
- Requires `feature-implementer` to consume the resulting sub-tasks

## Layout

```
feature-architect/
├── SKILL.md                          # this file
├── README.md
├── decomposition-heuristics.md       # the patterns + how to apply them
└── sub-task-template.md              # tasks.yaml sub-task entry format
```
