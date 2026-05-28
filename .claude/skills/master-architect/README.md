# master-architect skill (v2)

Iterative software architecture design through five sequential phases, with generate-critique-refine-approve loops at each level, designed to hand off cleanly to an agentic implementation skill (e.g., `feature-implementer`).

## What's new in v2

- **Phase 0 — Problem Discovery** (optional): asks user 5-12 clarifying questions before Phase 1, produces a project brief. Skip with `"I have a brief already"` or `"start at phase 1"`.
- **`references/` knowledge base**: 7 reference files distilling architecture knowledge (styles, anti-patterns, DDD, C4 syntax, Pydantic boundary pattern, MADR format, elicitation questions) inline in the skill. Master-architect consults these per phase per delegation.md. Replaces dependency on a separate Architecture skill suite.

## What it does

Master-architect orchestrates pre-implementation design through 5 progressively-concrete phases:

| Phase | Output | Maps to |
|-------|--------|---------|
| 0 — Problem Discovery (optional) | `phase-0-brief.md` (+ optional risks, glossary) | Pre-Phase-1 grounding |
| 1 — System Design | `phase-1-system.md` (vision, NFRs, QASes, journeys) | C4 Context |
| 2 — Architecture | `phase-2-architecture.md` (components, ADRs) | C4 Container |
| 3 — Code Layout | `phase-3-layout.md` (folders, naming, deps) | C4 Component |
| 4 — Task Decomposition | `phase-4-tasks.yaml` (DAG of vertical slices) | Implementation handoff |

Each phase runs the same loop:

```
GENERATE → CRITIQUE → REFINE → HUMAN APPROVAL → FINALIZE
              ↓
         (if upstream flaw found) → BACKTRACK to earlier phase
```

All artifacts live in `.architecture/`. The skill never writes outside that folder.

## Install

### Option A: project-local

```bash
mkdir -p .claude/skills
cp -r master-architect .claude/skills/
```

### Option B: user-level (available in every project)

```bash
mkdir -p ~/.claude/skills
cp -r master-architect ~/.claude/skills/
```

Verify:

```
> /skills
```

You should see `master-architect` in the list.

## Use

In any project where you want a design pass before implementation:

```
> Design a [thing] for me.
```

By default, this starts Phase 0 (discovery). To skip:

```
> Design a [thing] for me. I have a brief already, start with phase 1.
```

Or to resume:

```
> Continue the architecture work.
```

Or to jump to a specific phase:

```
> Run phase 3 for me. Layout is the only thing missing.
```

Master-architect will:
1. Read `.architecture/INDEX.md` (creating it if absent)
2. Determine entry mode (fresh / resume / explicit-phase / skip-discovery)
3. Run the loop for the current phase
4. Stop and ask for approval at the end of each phase
5. Move forward only on `approved`

## Companion skills (recommended)

Master-architect delegates content quality to other skills via description-match. None are required, but each improves output significantly. See `delegation.md` for the full map.

From the research bundles in this project:

- `karpathy-pre-action-check` — pre-flight check against silent assumptions and over-complication. Highest-value gate, applies in Phase 0-2.
- `paranoid-srp-python` — SRP discipline at component (Phase 2) and module (Phase 3) level.
- `tdd-enforcer-python` — testability as an architectural property.
- `pydantic-v2-conventions` — boundary-data discipline (Phase 2-3).
- `security-auditor` — adversarial review when phase touches user data, payments, or authn.
- `decisions-log-adr-lite` — ADR formatting (Phase 2).
- `srp-refactor` — layout heuristics (Phase 3).
- `plan-mode-and-task-decomposition` — vertical-slice decomposition (Phase 4).
- `progress-file-for-long-tasks` — multi-session continuity.
- `session-dreaming` — end-of-session lesson distillation.

If a companion skill isn't installed, master-architect falls back to inline checklists and references at lower fidelity. The fallback is automatic — no configuration needed.

## File layout

```
master-architect/
├── SKILL.md                       # Main loop logic, phase machine, escalation gate
├── algorithms.md                  # KB of self-learning algorithms (Reflexion, ToT, etc.)
├── delegation.md                  # When to delegate to which external skill + references map
├── workflow/
│   ├── phase-0-discovery.md       # Problem Discovery phase guidance (NEW v2)
│   ├── phase-1-system.md          # System Design phase guidance
│   ├── phase-2-architecture.md    # Architecture phase guidance
│   ├── phase-3-layout.md          # Code Layout phase guidance
│   └── phase-4-decompose.md       # Task Decomposition phase guidance
├── checklists/
│   ├── discovery-critique.md      # Phase 0 critique items (NEW v2)
│   ├── system-critique.md         # Phase 1 critique items
│   ├── architecture-critique.md   # Phase 2 critique items
│   └── layout-critique.md         # Phase 3-4 critique items
├── references/                    # NEW v2: Knowledge base
│   ├── elicitation-questions.md   # 28 discovery questions for Phase 0
│   ├── architecture-styles.md     # Style decision matrix, tradeoffs
│   ├── anti-patterns.md           # What to refuse (microservices-for-solo, etc.)
│   ├── c4-mermaid-syntax.md       # C4 diagrams in Mermaid with fallback
│   ├── ddd-cheatsheet.md          # Bounded contexts, context maps, tactical DDD
│   ├── pydantic-boundaries.md     # Pydantic at boundaries, dataclass in domain
│   └── madr-format.md             # ADR formats with Zimmermann 5+2 criteria
└── templates/
    ├── adr.md                     # Architecture Decision Record format
    ├── qas.md                     # Quality Attribute Scenario format
    ├── components.yaml            # Machine-readable container manifest
    └── tasks.yaml                 # Phase 4 handoff schema
```

## Design decisions (transparent)

1. **Fixed default algorithms per phase, with escalation gate.** Not dynamic algorithm selection on every step. On the DEEP track, master-architect consults `algorithms.md` and picks deliberately.
2. **Interactive approval in chat.** Not file-based. Single-developer optimization.
3. **Sequential by default, explicit-phase invocation allowed.** `run phase 3` is supported but warns if prerequisites aren't APPROVED.
4. **Backtrack on SCOPE-UPSTREAM flaws, with human approval.** Lower-phase critique that finds upstream flaws triggers a backtrack proposal, not an automatic restart.
5. **Versioning on overwrite.** Re-running an APPROVED phase archives the previous version to `_superseded/v<n>/`.
6. **File-renamed status.** Files use `.DRAFT` suffix while in flight, lose it on approval.
7. **Critical flaw = scope-of-fix, not severity.** A "critical" flaw is one whose fix requires changing an earlier phase.
8. **Delegation by description-match, not direct invocation.** Master-architect speaks cue phrases; Claude Code's skill system triggers the delegate.
9. **Master-architect never writes code.** Architecture is design, implementation is implementation.
10. **Phase 0 is optional and structurally different.** Discovery is question-driven, not generation-driven. Always BASIC track. Always skippable.
11. **References are bundled, not external.** Architecture KB (styles, DDD, C4, etc.) ships with the skill — no dependency on a separate skill suite.

## What this skill is NOT

- **Not a code generator.** It produces design artifacts, not code.
- **Not a feature implementer.** Hand off to `feature-implementer` after Phase 4.
- **Not a Q&A skill.** For one-off questions about architecture concepts, answer them directly without this skill.
- **Not for tiny tasks.** A 50-line script doesn't need 5 phases. Master-architect should refuse to engage if the user's request is obviously small.
- **Not for refactoring an existing system.** Different problem; needs a different skill.

## Compatibility

- Claude Code v2.1+ (for skills system)
- Python 3.12+ (for any code emitted in examples; not enforced)
- Works in any project type, but examples and delegated skills assume Python

## Changelog

- **v2** (2026-05-12): Added Phase 0 (Problem Discovery) and `references/` knowledge base distilled from Architecture chat research. Replaces dependency on external Architecture skill suite.
- **v1**: Initial release with 4 phases, escalation gate, backtrack mechanism, delegation by description-match.
