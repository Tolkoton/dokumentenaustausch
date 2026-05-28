# Phase 3 — Code Layout

**Goal**: design the concrete folder/file layout, naming conventions, and module dependency rules. This is what Claude Code will see when navigating the codebase.

**Maps to**: C4 Component level + file-system organization.

**Consumes**: `phase-1-system.md`, `phase-2-architecture.md` (both APPROVED).

## What "approved Phase 3" looks like

A single Markdown file `phase-3-layout.md` with:

1. **Top-level tree** — full directory tree as if `tree -L 3` was run on the project. Each top-level dir gets one-line purpose comment.
2. **Per-container layout** — for each Phase 2 container, show its sub-tree (typically a Python package).
3. **Naming conventions** — file naming, module naming, class naming, function naming. Be specific (e.g., "test files: `test_<module>.py`", "abstract bases: `Base<Name>` not `<Name>Base`").
4. **Dependency rules** — what can import what. Use the "dependency direction" pattern (e.g., `domain` cannot import from `infrastructure`; `app` can import from both).
5. **Module-by-module spec** — for each notable module (not every file), one paragraph: what it owns, what it exposes, what it imports, what tests cover it.
6. **Cross-references to ADRs** — when layout reflects a Phase 2 decision, link to the ADR.
7. **Open questions** — Phase 4 blockers.

Optional accompaniments:
- A `tree.txt` file with the full tree (useful for shell `cat`-ing)
- Per-module `README.md` templates (skeleton, to be filled by implementer)

## GENERATE step

### BASIC track

For each Phase 2 container:
1. Map to a Python package (or equivalent for the chosen language)
2. Within the package, split by **role** not by **type**:
   - GOOD: `users/handlers.py`, `users/repository.py`, `users/models.py`, `users/service.py` (cohesive by feature)
   - BAD: `handlers/users.py`, `handlers/orders.py`, `repositories/users.py`, `repositories/orders.py` (scattered by type)
3. Identify shared kernel (utilities, base classes, types) and place in `<project>/shared/` or `<project>/core/`
4. Place tests mirroring source: `tests/<container>/test_<module>.py`

Default layout for a Python project (uv + src layout):

```
<project>/
├── pyproject.toml
├── src/
│   └── <package_name>/
│       ├── __init__.py
│       ├── core/                  # Shared kernel
│       ├── <container_1>/         # One folder per Phase 2 container
│       ├── <container_2>/
│       └── ...
├── tests/
│   ├── unit/
│   └── integration/
├── docs/
│   └── adrs/                      # ADRs from Phase 2
└── .architecture/                  # This entire skill's output
```

Delegate to `srp-refactor` skill if available — cue: _"use srp-refactor heuristics to design folder structure"_.

### DEEP track

Layout decisions are rarely DEEP-worthy. The escalation triggers usually fire for Phase 1 or 2. If Phase 3 is on DEEP track, it's typically because:
- Multi-language repo (need polyrepo or monorepo decision)
- Massive size (>50 containers, need sub-grouping strategy)
- Constraint from infrastructure (specific build tool that demands a layout)

In those cases, ToT over 3 layouts varying on: (1) flat-vs-nested, (2) by-feature-vs-by-layer, (3) src-layout-vs-flat. Compare on: navigation cost, dependency-rule-clarity, blast radius of refactors.

## CRITIQUE step

Apply `checklists/layout-critique.md`.

**Required delegations**:
- `paranoid-srp-python` — _"check the proposed folder structure for SRP at module level"_
- `pydantic-v2-conventions` — _"verify Pydantic models live where cross-component data crosses boundaries"_

**Phase 3-specific failure modes**:
- **Circular dependency potential**: module A imports from B, and B from A is possible per rules. Flag.
- **God module**: any module spec longer than 3 sentences is probably doing too much.
- **Mismatched names**: container in Phase 2 is `OrderService`, folder in Phase 3 is `purchasing/` — pick one and stick to it across phases.
- **No test colocation strategy**: tests folder structure not specified.
- **Hidden cross-cutting**: cross-cutting concerns from Phase 2 (auth, logging) have no obvious home folder.
- **Premature framework lock-in**: layout that only makes sense if you use FastAPI is fragile to framework swap.

## REFINE step

SCOPE-LOCAL: rearrange folders, rename, adjust dependency rules.

SCOPE-UPSTREAM (Phase 2):
- Layout cannot represent a container boundary from Phase 2 (boundary is too fuzzy or impossible to localize) → Phase 2 needs revision
- Dependency rules from Phase 3 contradict Phase 2 component dependencies → mismatch; usually Phase 2 was optimistic, fix there

SCOPE-UPSTREAM (Phase 1):
- Layout requires a feature that's not in Phase 1 scope (e.g., we need a `notifications/` folder but notifications aren't in Phase 1) → either Phase 1 expanded scope unintentionally, or we're over-engineering

## Hand-off to Phase 4

Phase 3 APPROVED means:
- Every folder has clear purpose
- Every Phase 2 container has explicit folder home
- Dependency rules are stated (and ideally enforceable by `import-linter` or similar)
- Naming conventions written down (Phase 4 tasks will reference these)
- Tests have a home, not "we'll figure it out"

Phase 4 will use the file paths from Phase 3 as the "vocabulary" for task descriptions ("create `src/users/service.py` with `class UserService` exposing `register(...)` and `authenticate(...)`").

## Templates

- No template file for the tree itself (project-specific)
- See `templates/components.yaml` to align folder names with component names
