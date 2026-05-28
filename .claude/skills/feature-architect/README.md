# feature-architect

Single-task decomposer for Claude Code. Splits an oversized or fuzzy task into a DAG of vertical-slice sub-tasks that fit `feature-implementer`'s complexity ceiling.

Companion to `master-architect` (system-level decomposer; produces tasks.yaml originally) and `feature-implementer` (consumes the resulting sub-tasks).

## When to use

The skill triggers when:
- User says "split task t007", "decompose this feature", "break this into smaller pieces"
- `feature-implementer` encounters a task >L complexity in Phase A
- `feature-implementer` hits 300 LOC ceiling mid-task

It does NOT trigger for:
- Project-level decomposition (use `master-architect` Phase 4)
- Tasks already S/M complexity (just implement them)

## What it does

Per oversized task:

1. Reads parent task from `.architecture/tasks.yaml`
2. Identifies natural splits using one of 6 patterns:
   - Capability split (multiple capabilities → one per sub-task)
   - Behavior-progression (thin happy path → enhancements)
   - CRUD split (Create/Read/Update/Delete as separate sub-tasks)
   - Path-progression (happy/error/edge)
   - QAS-hardening (functional / performance / security)
   - Phase split (build / instrument / harden)
3. Constructs sub-tasks per `sub-task-template.md`
4. Constructs DAG with explicit dependencies
5. Updates `tasks.yaml`: parent marked `SPLIT_INTO`, sub-tasks added
6. Hands back to user with summary

## Installation

```bash
# Place at user-level (shared across projects)
cp -r feature-architect ~/.claude/skills/

# Or project-level (this codebase only)
cp -r feature-architect .claude/skills/
```

## Usage

```
> Split t007 into sub-tasks.
```

Or via `feature-implementer` auto-trigger when a task is too large.

Output:

```
Split t007 into 5 sub-tasks:

  t007a (M): Register: minimal happy path
            depends_on: [t001, t002]

  t007b (S): Register: duplicate-email rejection
            depends_on: [t007a]
            (can run parallel to t007c, t007d, t007e)

  t007c (M): Register: password policy enforcement
            depends_on: [t007a]

  t007d (M): Register: brute-force defense
            depends_on: [t007a]

  t007e (S): Register: audit log
            depends_on: [t007a]

Original t007 marked SPLIT_INTO.

Next: implement t007a first (it unblocks all others).
```

## Operational rules

1. Always produce 2-5 sub-tasks. Not 1 (no split needed), not 6+ (parent mis-conceived → master-architect).
2. Each sub-task must be S or M complexity. Never L.
3. DAG must be acyclic.
4. Every parent acceptance criterion must map to ≥1 sub-task.
5. Parent marked `SPLIT_INTO`, never `DONE` or `ABANDONED`.
6. Never touch code, only `tasks.yaml`.
7. Sub-task IDs use parent ID + suffix letter (t007 → t007a, t007b, ...).
8. Prefer vertical slices (end-to-end behavior) over horizontal layers.
9. Don't add artificial sequencing (only real dependencies in `depends_on`).
10. If a sub-task itself is still L, recurse: feature-architect splits it again.

## Layout

```
feature-architect/
├── SKILL.md                       # main skill file
├── README.md                      # this file
├── decomposition-heuristics.md    # 6 splitting patterns + when to use each
└── sub-task-template.md           # tasks.yaml sub-task entry format
```

## Companion skills

- `master-architect` — produces the original tasks.yaml; backtrack target if decomposition reveals deeper issues
- `feature-implementer` — consumes the resulting sub-tasks

## Compatibility

- Claude Code v2.1+
- Requires `master-architect` to have created `.architecture/tasks.yaml`
- Designed to work with `feature-implementer`

## Anti-patterns

See `decomposition-heuristics.md`. Briefly:
- **Layer splits**: model/service/endpoint as separate sub-tasks (no behavior in early ones)
- **Over-splitting**: 6+ sub-tasks for a task that could be 2
- **Artificial sequencing**: declaring depends_on where none exists
- **Sub-tasks of sub-tasks indefinitely**: 2 levels max usually; beyond that, parent was mis-designed

## Changelog

### v1.0 (2026-05-12)

- Initial release
- 6 decomposition patterns
- DAG-aware sub-task creation
- Parent task SPLIT_INTO status
- Recursive splitting supported (up to 2 levels)
