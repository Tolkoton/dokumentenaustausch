# Intake Readiness Checklist (Phase A)

Apply at end of Phase A before transitioning to Phase B. For each item PASS / FAIL.

## Task spec

- [ ] Task source clear (tasks.yaml entry vs ad-hoc user request) and noted in PROGRESS.md
- [ ] If from tasks.yaml: task ID exists in file
- [ ] If ad-hoc: minimum spec inferable from user request (title, description, at least one file, at least one criterion)

## Dependencies

- [ ] All `depends_on` task IDs exist
- [ ] All `depends_on` are in status `DONE`
- [ ] No dependency is in `BLOCKED` or `ABANDONED`

## Size

- [ ] Task is not obviously >L (≤5 files, ≤3 new files, ≤10 acceptance criteria)
- [ ] If approaching the limits: warning issued to user, decision recorded
- [ ] If clearly >L: feature-architect invoked instead (Phase A halts)

## Files

- [ ] All `files_to_modify` exist on disk
- [ ] All `files_to_create` paths are inside Phase 3 layout
- [ ] No path violates Phase 3 dependency rules

## Acceptance criteria

- [ ] Every criterion is executable (test command, curl, file-exists, type-check)
- [ ] No criterion uses vague language ("works", "is clean", "complete")
- [ ] Each criterion is independently verifiable

## Context loaded

- [ ] Phase 1 artifact read (`.architecture/phase-1-system.md`)
- [ ] Phase 2 artifact read (`.architecture/phase-2-architecture.md`) — at minimum the container this task touches
- [ ] Phase 3 artifact read (`.architecture/phase-3-layout.md`) — at minimum the relevant sections
- [ ] Memory files loaded:
  - [ ] Per-tech: list of detected technologies in PROGRESS.md
  - [ ] Per-project `.architecture/MEMORY.md` if exists

## Existing code

- [ ] `files_to_modify` read in full
- [ ] Sibling modules skimmed for naming conventions
- [ ] Test fixtures in `conftest.py` noted (for Phase C reuse)
- [ ] Imports traced for tech detection

## Backtrack check

- [ ] No file referenced in task is missing AND not in `files_to_create` (would be Phase 3 inconsistency)
- [ ] No acceptance criterion references a non-existent QAS
- [ ] No task implies a container not in `components.yaml`

If any backtrack signal: STOP, write `BACKTRACK-from-task-<id>.md`, exit Phase A.

## Workspace

- [ ] `.architecture/tasks/<id>/` directory created
- [ ] `tasks/<id>/PROGRESS.md` initialized with Phase A timestamp and context summary

## Final pass

- [ ] No open question on task spec is unanswered (if any, surfaced to user; Phase A pauses)
- [ ] Decision recorded: PROCEED to Phase B / REFUSE (too small or wrong skill) / SPLIT (delegate to feature-architect) / BACKTRACK (delegate to master-architect)
