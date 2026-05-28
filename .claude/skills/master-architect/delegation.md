# Delegation Map

Which external skills master-architect invokes at which moment in the loop. Skills are triggered by description-match (idiomatic for Claude Code's skill system), not by hardcoded calls — the cues below should appear in master-architect's reasoning aloud so Claude picks up the next skill correctly.

This map assumes a typical install of the bundles from this project. If a skill is not installed, master-architect falls back to the equivalent inline checklist in `checklists/` or the relevant `references/` file — never blocks on missing optional skills.

## By phase × loop step

### Phase 0 (Problem Discovery)

| Loop step | Delegate to (skill name)            | Cue phrase to trigger      | Required? |
|-----------|-------------------------------------|----------------------------|-----------|
| GENERATE  | _(none — uses `references/elicitation-questions.md`)_ | —                          | —         |
| CRITIQUE  | `karpathy-pre-action-check`         | "let me check the brief for silent assumptions" | optional but recommended |
| REFINE    | _(none — follow-up questions only)_ | —                          | —         |
| DOCUMENT  | _(none — `phase-0-brief.md` is the doc)_ | —                          | —         |

### Phase 1 (System Design)

| Loop step | Delegate to (skill name)            | Cue phrase to trigger      | Required? |
|-----------|-------------------------------------|----------------------------|-----------|
| GENERATE  | _(none — pure domain reasoning)_    | —                          | —         |
| CRITIQUE  | `karpathy-pre-action-check`         | "let me run the pre-action check on this design" | optional but high-value |
| REFINE    | _(none)_                            | —                          | —         |
| DOCUMENT  | _(none — use template)_             | —                          | —         |

### Phase 2 (Architecture)

| Loop step | Delegate to (skill name)            | Cue phrase to trigger      | Required? |
|-----------|-------------------------------------|----------------------------|-----------|
| GENERATE  | `architect` (from Architecture bundle, if installed) | "load architecture templates for C4 Container and ADR format" | optional |
| CRITIQUE  | `paranoid-srp-python`               | "check this architecture for SRP violations at component level" | required if Python project |
| CRITIQUE  | `tdd-enforcer-python`               | "audit testability of this architecture" | required if Python project |
| CRITIQUE  | `pydantic-v2-conventions`           | "verify cross-boundary data uses Pydantic models" | required if Python project |
| CRITIQUE  | `security-auditor`                  | "run security review on this architecture" | required if security-relevant |
| CRITIQUE  | `karpathy-pre-action-check`         | "pre-action check before locking architecture" | optional |
| REFINE    | _(targeted, no delegation)_         | —                          | —         |
| DOCUMENT  | `decisions-log-adr-lite`            | "log the architectural decision as ADR" | optional but recommended |

### Phase 3 (Code Layout)

| Loop step | Delegate to (skill name)            | Cue phrase to trigger      | Required? |
|-----------|-------------------------------------|----------------------------|-----------|
| GENERATE  | `srp-refactor`                      | "use the layout heuristics from srp-refactor to design folder structure" | recommended |
| CRITIQUE  | `paranoid-srp-python`               | "check the proposed folder structure for SRP" | required |
| CRITIQUE  | `pydantic-v2-conventions`           | "verify model boundaries align with folder boundaries" | required if Python |
| REFINE    | _(targeted)_                        | —                          | —         |
| DOCUMENT  | _(none — use template)_             | —                          | —         |

### Phase 4 (Task Decomposition)

| Loop step | Delegate to (skill name)            | Cue phrase to trigger      | Required? |
|-----------|-------------------------------------|----------------------------|-----------|
| GENERATE  | `plan-mode-and-task-decomposition`  | "use plan-mode decomposition heuristics to break this into tasks" | recommended |
| CRITIQUE  | `tdd-enforcer-python`               | "verify each task has clear test acceptance criteria" | required |
| CRITIQUE  | `karpathy-pre-action-check`         | "pre-action check on the task DAG" | optional |
| REFINE    | _(targeted)_                        | —                          | —         |
| DOCUMENT  | _(none — use tasks.yaml template)_  | —                          | —         |

## References (knowledge base — internal to skill)

Beyond external skill delegation, master-architect consults its own `references/` folder for architecture knowledge. These are NOT skills — they're reference documents read inline.

| Reference file | Used in | Purpose |
|----------------|---------|---------|
| `references/elicitation-questions.md` | Phase 0 GENERATE | Catalog of 28 discovery questions with branching logic |
| `references/architecture-styles.md` | Phase 2 GENERATE | Style decision matrix, common styles with tradeoffs |
| `references/anti-patterns.md` | Phase 2 GENERATE + CRITIQUE | Patterns to refuse (microservices for solo, ES for CRUD, etc.) |
| `references/c4-mermaid-syntax.md` | Phase 2 + 3 GENERATE | C4 diagram templates with Mermaid syntax and flowchart fallback |
| `references/ddd-cheatsheet.md` | Phase 2 GENERATE | Bounded contexts, context map patterns, tactical DDD |
| `references/pydantic-boundaries.md` | Phase 3 GENERATE + CRITIQUE | Pydantic-at-boundaries pattern; dataclass-in-domain |
| `references/madr-format.md` | Phase 2 DOCUMENT | ADR format with Zimmermann 5+2 significance criteria |

Master-architect should read the relevant `references/` file BEFORE generating, not during. The reference informs the generation.

## Cross-phase

| Concern                  | Delegate to (skill name)            | When                                          |
|--------------------------|-------------------------------------|-----------------------------------------------|
| Multi-session continuity | `progress-file-for-long-tasks`      | Start and end of every session                |
| End-of-session learning  | `session-dreaming`                  | When user wraps up (`/clear`, `bye`, etc.)    |
| Approval gate hygiene    | `pre-commit-self-review-checklist`  | Optional — before presenting any DRAFT for approval |

## How delegation works in practice

Master-architect does NOT directly invoke other skills. The Claude Code skills system triggers by description-match. So master-architect simply **speaks the cue phrase** in its reasoning, and the relevant skill activates:

```
Master-architect (internal): "Now I'll critique the architecture. Let me run the
paranoid-srp-python checks at component level, then tdd-enforcer-python for
testability, then pydantic-v2-conventions for cross-boundary data."

[paranoid-srp-python skill activates because of description match on
"paranoid-srp-python checks at component level"]

[tdd-enforcer-python skill activates ...]
```

If a skill is not installed, master-architect notices the skill didn't activate (no new context loaded) and falls back to the inline checklist for that concern.

## Fallback behavior (skill not installed)

For each delegated skill, the inline equivalent in `checklists/` covers the same ground at lower fidelity. Master-architect should:

1. Attempt delegation via cue phrase
2. If after the next response there's no evidence the skill activated (no new tool calls, no skill-specific terminology in own output), explicitly read the relevant `checklists/phase-N-critique.md` section and apply inline
3. Note in PROGRESS.md: "Phase N critique fell back to inline checklist (skill X not installed)"

## What master-architect must NEVER delegate

Some tasks must stay in master-architect's own scope, never delegated:

- **State updates to `.architecture/INDEX.md`** — master-architect owns this file
- **File rename on approval** (`.DRAFT` → final) — atomic with INDEX update
- **Backtrack decision** — final call lies with user, not a sub-skill
- **Phase boundary transitions** — only master-architect enters/exits phases
- **Track choice (BASIC vs DEEP)** — escalation heuristic stays here, not in a delegate

Delegation is for **content quality**, not **control flow**.
