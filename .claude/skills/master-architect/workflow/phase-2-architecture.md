# Phase 2 — Architecture

**Goal**: design HOW the system is structured at the component level. Components, boundaries, data flow, technology choices, ADRs.

**Maps to**: C4 Container level + Architecture Decision Records.

**Consumes**: `phase-1-system.md` (APPROVED).

## What "approved Phase 2" looks like

A single Markdown file `phase-2-architecture.md` with:

1. **Architectural style** — one named style (layered, hexagonal, event-driven, microservices, monolith-with-modules, etc.) with one-paragraph justification tied to a Phase 1 QAS.
2. **Container diagram (text or Mermaid)** — high-level components and their relationships. If Mermaid, include flowchart fallback for tools that don't render C4 syntax.
3. **Per-container responsibilities** — for each component: name, owns-what, exposes-what, depends-on-what, NFR ownership (which QASes it's responsible for satisfying).
4. **Data flow** — for each user journey from Phase 1, walk through which containers handle what step.
5. **Cross-cutting concerns** — how does the architecture handle: auth, logging, error handling, configuration, observability, persistence. One paragraph each.
6. **Technology choices** — for each container: language, framework, datastore, key libraries. Justify per choice (link to ADR if non-obvious).
7. **ADRs** — one ADR per non-trivial decision, in `phase-2-architecture.md` itself or as separate files under `.architecture/adrs/`. Use `templates/adr.md` format.
8. **Open questions** — Phase 3 blockers.

Plus optionally `components.yaml` (`templates/components.yaml` schema) for machine-readable component manifest.

## GENERATE step

### BASIC track

Map each Phase 1 section to architectural decisions:
- Stakeholders + journeys → external interfaces (UIs, APIs)
- Functional capabilities → containers that own them
- QASes → architectural style + cross-cutting concerns
- Constraints → technology choices

Propose 3 alternative architectural styles only when:
- Choice between styles is genuinely a 50/50 call given QASes, or
- User has expressed preference but it doesn't fit QASes (steelman both)

Otherwise pick the obvious style and write 1-paragraph justification.

### DEEP track

ToT (3 styles), compare on QAS satisfaction. Pruning criterion: violates >1 QAS, or violates a constraint from Phase 1.

Or, if the problem maps to a known pattern (event sourcing for audit, hexagonal for testability, microservices for team-scale), name the pattern and justify rather than re-derive.

## CRITIQUE step

Apply `checklists/architecture-critique.md`.

**Required delegations** (cue phrases for each):
- `paranoid-srp-python` — _"check each component for SRP violations and high cohesion"_
- `tdd-enforcer-python` — _"audit testability: each component must be testable in isolation"_
- `pydantic-v2-conventions` — _"verify cross-component data uses Pydantic models with strict/frozen"_

**Conditional delegations**:
- If system touches user data, payments, or authn → `security-auditor` — _"run security review on architecture"_
- If novelty_high → `karpathy-pre-action-check`

**Phase 2-specific failure modes**:
- **Containers that depend on everything** (god-component anti-pattern). If any container has >5 inbound dependencies, flag.
- **Implicit cross-cutting concerns**: section 5 says "logging is handled" but doesn't say where. That's not architecture, that's hope.
- **Missing ADRs for irreversible choices**: switching auth providers later is a major refactor. If you don't justify the choice, you'll forget why.
- **Tech choices that don't match team skills**: Phase 1 constraints likely mentioned the team. Architecture that requires hiring is a flaw, not a feature.
- **QAS not assigned to any container**: every QAS must have an owner. Performance QAS not owned by anyone = won't be satisfied.

## REFINE step

Classify each flaw:
- SCOPE-LOCAL: fix in `phase-2-architecture.md.DRAFT`
- SCOPE-UPSTREAM (Phase 1): typically when an architectural style cannot satisfy a Phase 1 QAS or constraint. Examples:
  - "QAS-3 says 99.99% uptime but team is one person → no architecture can satisfy this. Revise QAS or accept tradeoff."
  - "Phase 1 implied real-time but didn't specify; architecture treats it as batch → either Phase 1 needs revision or architecture changes."

For SCOPE-UPSTREAM, generate `BACKTRACK-from-phase-2.md` and stop.

## ADR generation

Trigger ADR for any of:
- Choice between two non-trivially different alternatives (e.g., sync vs async, monolith vs split)
- Choice that requires migration to undo (database engine, language, auth provider, deployment platform)
- Choice that affects multiple containers (cross-cutting decision)

Do NOT ADR:
- Library choices within an obvious ecosystem ("we'll use FastAPI" doesn't need an ADR if Python web is given)
- Naming conventions (Phase 3 concern)
- Code-level decisions

Delegate to `decisions-log-adr-lite` skill if available — cue: _"log this architectural decision as ADR"_.

## Hand-off to Phase 3

Phase 2 APPROVED means:
- Every container has explicit responsibilities and dependencies
- Every QAS has an owning container
- Every irreversible decision has an ADR
- Cross-cutting concerns are explicit, not implicit
- Technology choices are committed

## Templates

- `templates/adr.md` — ADR structure (Context, Decision, Status, Consequences)
- `templates/components.yaml` — machine-readable component manifest (optional)
- `templates/qas.md` — referenced from Phase 1, but Phase 2 must show each QAS's owner
