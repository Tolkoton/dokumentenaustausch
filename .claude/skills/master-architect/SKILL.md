---
name: master-architect
description: Iterative software architecture design through five sequential phases (problem discovery → system design → architecture → code layout → task decomposition), each running a generate-critique-refine-approve loop with escalation to advanced algorithms when stakes are high. Use this skill WHENEVER the user asks to "design a system", "architect this", "plan the architecture", "design my project from scratch", "design the folder structure", "decompose this project", "split this into tasks", "review my architecture", "find flaws in my design", or anything resembling pre-implementation design work that needs handoff to an agentic developer. Also use when user says "run phase N", "continue architecture work", "resume architect", or "ask me discovery questions". DO NOT use for implementing features (that's feature-implementer's job) or ad-hoc Q&A about architectural concepts.
---

# Master Architect

Iterative pre-implementation design through five progressively-concrete phases. Each phase runs a generate-critique-refine-approve loop. Output is consumed by feature-implementation agents downstream.

**Version**: 2 (adds Phase 0 discovery and `references/` knowledge base).

## When to invoke

**Default trigger**: user wants pre-implementation design work for a non-trivial system. The skill detects entry mode from user phrasing:

- **Fresh start** (`"design X"`, `"architect Y from scratch"`) → run Phase 0 first, then Phase 1
- **Skip discovery** (`"I have a brief already"`, `"skip discovery"`, `"start with phase 1"`) → skip Phase 0, start at Phase 1
- **Resume** (`"continue architecture"`, `"resume architect"`) → read `.architecture/INDEX.md`, continue from first non-`APPROVED` phase
- **Explicit phase** (`"run phase 2"`, `"redo the layout"`) → jump to that phase; if prerequisite phases are not `APPROVED`, warn and ask

## State and storage

All artifacts live in `.architecture/` at the repo root. **Never** write outside this directory. **Never** modify files outside `.architecture/` during architecture work — implementation is a separate skill's job.

```
.architecture/
├── INDEX.md                            # Single source of truth for phase status
├── phase-0-brief.md                     # Problem discovery output (skippable)
├── phase-0-risks.md                     # Optional: early risks surfaced in discovery
├── phase-0-glossary.md                  # Optional: initial ubiquitous language seeds
├── phase-1-system.md.DRAFT            # While in flight
├── phase-1-system.md                    # Renamed on approve (no .DRAFT suffix)
├── phase-2-architecture.md
├── phase-3-layout.md
├── phase-4-tasks.yaml
├── PROGRESS.md                          # Multi-session continuity (cf. progress-file skill)
├── BACKTRACK-from-phase-N.md           # Created when lower phase finds critical flaw in higher
└── _superseded/
    ├── v1/                              # Archived previous versions
    │   ├── phase-1-system.md
    │   └── ...
    └── v2/
```

**File naming convention**: `<artifact>.md.DRAFT` while iterating; renamed to `<artifact>.md` on approval. This makes status visible from `ls` without reading INDEX.md.

## INDEX.md schema

Master-architect maintains this file. Read it before any action.

```markdown
# Architecture Index

| Phase | Status   | File                        | Approved at         |
|-------|----------|-----------------------------|---------------------|
| 0     | APPROVED | phase-0-brief.md            | 2026-05-12T13:00Z   |
| 1     | APPROVED | phase-1-system.md           | 2026-05-12T14:00Z   |
| 2     | DRAFT    | phase-2-architecture.md.DRAFT | —                 |
| 3     | PENDING  | —                           | —                   |
| 4     | PENDING  | —                           | —                   |

Current version: v2 (v1 superseded after Phase 2 found critical flaw in Phase 1 system boundaries)
```

`Status` values: `PENDING` (not started) | `DRAFT` (in flight) | `APPROVED` (human approved) | `SUPERSEDED` (invalidated by backtrack) | `SKIPPED` (Phase 0 only — user opted out).

## The loop (applied identically to each phase)

Every phase runs this state machine. See `workflow/phase-N-*.md` for phase-specific content.

```
┌─────────────────────────────────────────────────────────────┐
│ ENTER PHASE N                                                │
│   - Read .architecture/INDEX.md                              │
│   - Read inputs: phase-1..(N-1) approved artifacts           │
│   - Read workflow/phase-N-*.md for phase-specific guidance   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ STAKES ASSESSMENT (escalation gate)                          │
│   3 boolean signals:                                         │
│     - reversibility_low (hard to change after implemented)   │
│     - blast_radius_systemic (affects most of the codebase)   │
│     - novelty_high (no clear precedent in user's experience) │
│   If ≥2 true → DEEP track. Otherwise → BASIC track.          │
│   Announce track choice to user with one-line reasoning.     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ GENERATE                                                     │
│   BASIC: structured single-pass, propose 3 alternatives      │
│          with tradeoffs (see template)                       │
│   DEEP:  consult algorithms.md, default to ToT (3 candidate  │
│          trees, prune internally, present winner + runner-up)│
│   Write phase-N.md.DRAFT                                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ CRITIQUE                                                     │
│   Apply checklists/phase-N-critique.md                       │
│   Delegate to relevant skills (see delegation.md):           │
│     - karpathy-pre-action-check (always, for Phase 1-2)      │
│     - paranoid-srp-python (Phase 2-3)                        │
│     - tdd-enforcer-python (Phase 2-3, testability gate)      │
│     - security-auditor (Phase 2 if security-relevant)        │
│   BASIC: single-pass checklist review                        │
│   DEEP:  red-team persona, adversarial prompts               │
│   Classify each flaw: SCOPE-LOCAL or SCOPE-UPSTREAM          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
              ┌────────┴────────┐
              │ Any SCOPE-      │
              │ UPSTREAM flaws? │
              └────────┬────────┘
                       │
              ┌────yes─┴───no─────┐
              ▼                    ▼
┌──────────────────────────┐  ┌──────────────────────────────┐
│ BACKTRACK                │  │ REFINE                        │
│   Write BACKTRACK.md     │  │   For each SCOPE-LOCAL flaw:  │
│   describing each        │  │     reproduce → isolate →     │
│   upstream-scope flaw    │  │     hypothesize → fix → verify│
│   and which prior phase  │  │   Update phase-N.md.DRAFT     │
│   needs revision.        │  │   Re-run CRITIQUE.            │
│   Ask user to approve    │  │   Loop until no flaws.        │
│   backtrack.             │  └────────────┬──────────────────┘
└────────┬─────────────────┘               │
         │                                  ▼
         │                    ┌──────────────────────────────┐
         │                    │ HUMAN APPROVAL GATE           │
         │                    │   Present phase-N.md.DRAFT    │
         │                    │   Await:                      │
         │                    │     "approved"       → ENTER  │
         │                    │     "revise: <note>" → REFINE │
         │                    │     "reject"         → exit   │
         │                    └────────┬──────────────────────┘
         │                             │
         │                       on approved
         │                             ▼
         │                    ┌──────────────────────────────┐
         │                    │ FINALIZE                      │
         │                    │   Rename phase-N.md.DRAFT     │
         │                    │     → phase-N.md              │
         │                    │   Update INDEX.md             │
         │                    │     status → APPROVED         │
         │                    │     approved_at → now         │
         │                    │   Append to PROGRESS.md       │
         │                    │   Suggest Phase N+1 next      │
         │                    └────────────┬──────────────────┘
         │                                 │
on backtrack approved                      │
         │                                 │
         ▼                                 ▼
┌─────────────────────────────────────────────────────────────┐
│ ON BACKTRACK                                                 │
│   For each invalidated phase M..N-1:                         │
│     mv phase-M.md → _superseded/v<n>/phase-M.md              │
│     status → SUPERSEDED                                      │
│   Bump version in INDEX.md                                   │
│   Re-enter Phase M (lowest invalidated)                      │
└──────────────────────────────────────────────────────────────┘
```

## Escalation algorithms (high-stakes only)

When STAKES ASSESSMENT puts the phase on DEEP track, consult `algorithms.md` before generating/critiquing. Defaults:

- **Generate (DEEP)**: Tree of Thoughts (3 branches, internal pruning)
- **Critique (DEEP)**: red-team persona + multi-agent debate (architect vs adversary)
- **Refine (DEEP)**: Self-Refine (regenerate problematic section, not patch)

Override is allowed when the problem clearly maps to a more specific algorithm (e.g., correctness-critical algorithm → CRITIC with execution traces; security-critical → red-team with attack-tree). Always announce the choice and one-line reasoning to the user.

## Critical-flaw definition (for SCOPE-UPSTREAM detection)

A flaw is **SCOPE-UPSTREAM** when its fix requires modifying an artifact from a previous phase. A flaw is **SCOPE-LOCAL** when it can be addressed by editing the current phase's artifact alone.

Examples (Phase 3 → Phase 1):
- Layout requires a module that violates a quality attribute scenario from Phase 1 → UPSTREAM, fix Phase 1 first
- A folder name is unclear → LOCAL, rename in place

Examples (Phase 2 → Phase 1):
- Architecture cannot satisfy an NFR from Phase 1 → UPSTREAM, either revise Phase 1 NFR or backtrack
- A component boundary is fuzzy → LOCAL, refine boundary description

When unsure, treat as UPSTREAM and ask user — false UPSTREAM costs one chat turn, false LOCAL costs a future backtrack.

## Phase contracts (what each phase consumes / produces)

| Phase | Consumes | Produces | Maps to |
|-------|----------|----------|---------|
| 0 — Problem Discovery (optional) | User intent + clarifying Q&A | `phase-0-brief.md` (+ optional `phase-0-risks.md`, `phase-0-glossary.md`) | Pre-Phase-1 grounding |
| 1 — System Design | Phase 0 brief (if exists), user intent | `phase-1-system.md` (vision, NFRs, QASes, user journeys) | C4 Context |
| 2 — Architecture | Phase 1 artifact + references/architecture-styles.md, ddd-cheatsheet.md, c4-mermaid-syntax.md | `phase-2-architecture.md` (components, boundaries, tech, data flow) + ADRs | C4 Container |
| 3 — Code Layout | Phase 1-2 artifacts + references/pydantic-boundaries.md | `phase-3-layout.md` (folder tree, naming, dep rules) | C4 Component |
| 4 — Task Decomposition | Phase 1-3 artifacts | `phase-4-tasks.yaml` (task DAG with acceptance criteria) | Implementation handoff |

See `workflow/phase-{0,1,2,3,4}-*.md` for phase-specific generation prompts, critique checklists, and templates.

See `delegation.md` for which external skills to invoke at which moment of the loop.

See `algorithms.md` for the catalog of self-learning algorithms used on DEEP track.

See `references/` for the architecture knowledge base (styles, decision matrices, DDD patterns, C4 syntax, Pydantic conventions, MADR format, elicitation questions). Consult per phase per delegation.md.

## Operational rules (NEVER violate)

1. **Never write outside `.architecture/`**. Architecture is design, not implementation.
2. **Never skip CRITIQUE phase**, even on BASIC track. The Karpathy pre-action check is the single highest-value gate.
3. **Never auto-approve**. Human approval is the only path from DRAFT → APPROVED.
4. **Never delete `_superseded/`**. It is the learning record.
5. **Never proceed to Phase N+1 if Phase N is DRAFT or SUPERSEDED**. Only APPROVED (or `SKIPPED` for Phase 0).
6. **Always update INDEX.md** atomically with file renames. INDEX.md must always reflect the filesystem.
7. **Always read PROGRESS.md** at session start if it exists — it captures context from prior sessions.
8. **Always announce track choice (BASIC vs DEEP)** before generating. The user must know when escalation triggered.
9. **Always classify flaws as SCOPE-LOCAL or SCOPE-UPSTREAM** during CRITIQUE. Skipping this skips the backtrack mechanism.
10. **Never start coding**. Hand off to feature-implementer via Phase 4 tasks.yaml.

## Phase 0 special rules

Phase 0 is structurally different from Phases 1-4: instead of producing a design artifact and critiquing it, it **gathers context from the user** through questions.

- **Phase 0 is OPTIONAL**. If user already has clarity on the problem (`"I have a brief already"`, `"skip discovery"`, `"start at phase 1"`), mark Phase 0 as `SKIPPED` in INDEX.md and proceed to Phase 1.
- **Phase 0 GENERATE = pose questions**. Use `references/elicitation-questions.md` for the question set. Adapt based on greenfield vs brownfield, project size, domain.
- **Phase 0 CRITIQUE = check completeness**. After user answers, check whether the brief has enough to start Phase 1. Flag gaps as SCOPE-EXTERNAL (need more user input).
- **Phase 0 REFINE = ask follow-up questions** for unclear or shallow answers.
- **Phase 0 APPROVE = user confirms** the brief captures the problem accurately.
- **Phase 0 has NO upstream** — flaws are always SCOPE-LOCAL or SCOPE-EXTERNAL.
- **Phase 0 does NOT use the escalation gate**. Always BASIC track (asking lots of questions is the default).

## Session continuity

Long architecture work spans sessions. At end of each session, append to `PROGRESS.md`:
- Current phase + status
- Open questions for user
- Decisions made and rationale (one-liners)
- Next concrete action

At session start, read `PROGRESS.md` before INDEX.md (it has the "why", INDEX has the "what").

Delegate to the `progress-file-for-long-tasks` skill if available — it has the canonical format.

## Handoff to implementation

Phase 4 produces `phase-4-tasks.yaml` in the schema documented in `templates/tasks.yaml`. This file is the **only** interface between architecture and implementation. After Phase 4 APPROVED, master-architect's job is done; further work goes to `feature-planner` / `feature-implementer` skills.

Do not start implementation. Do not write code. Do not run tests. Architecture's job is to make implementation easy — not to do it.
