# Phase 1 — System Design

**Goal**: capture WHAT the system does and WHAT properties it must have, before any HOW. Output is the input to Phase 2 (Architecture).

**Maps to**: C4 Context level + Quality Attribute Scenarios.

## What "approved Phase 1" looks like

A single Markdown file `phase-1-system.md` with these sections in this order:

1. **One-paragraph system vision** — what it does, who uses it, why it exists. Plain English.
2. **Stakeholders** — who interacts with the system, in what role.
3. **System context** — what the system depends on (external systems, APIs, data sources), what depends on the system.
4. **Key user journeys** — 3-7 happy paths from a user's perspective, no implementation details.
5. **Functional capabilities** — bulleted list of what the system can do. Not how. Not which component does what.
6. **Quality Attribute Scenarios (QASes)** — 3-7 non-functional requirements in QAS format (see `templates/qas.md`).
7. **Constraints** — what is fixed by external forces (regulation, infrastructure, budget, team size, languages, deadlines).
8. **Out of scope** — what this system does NOT do. Often more important than what it does.
9. **Open questions** — anything master-architect couldn't decide alone. Each open question blocks Phase 2 on at least one decision.

Length: 200-600 lines for a typical project. Longer = decomposition opportunity (you may have multiple systems).

## GENERATE step

### BASIC track

Single-pass generation. Ask the user (or use existing context) for each section. If section already has clear input from the user, transcribe it concisely. If unclear, write the best-guess version and tag it `[ASSUMPTION: X — confirm?]` for the approval step to surface.

Propose 3 alternatives ONLY for sections where genuine architectural alternatives exist (typically: stakeholder model, scope boundary, technology platform if user mentioned).

### DEEP track

Consult `algorithms.md` → ToT (default). Build 3 candidate trees varying on:
- Tree 1: Optimize for time-to-market (narrow scope, lean stack)
- Tree 2: Optimize for long-term maintainability (broader scope, conservative stack)
- Tree 3: Optimize for one explicit constraint the user emphasized (e.g., cost, security, ops simplicity)

Each tree fills sections 1-8. Compare on QAS satisfaction. Present winner + runner-up to user. Sections 5-9 may share text across trees if they don't change.

## CRITIQUE step

Apply `checklists/system-critique.md`. Always delegate to `karpathy-pre-action-check` skill if available (cue: _"let me run the pre-action check on this system design"_).

Common Phase 1 failure modes to actively look for:

- **Solution-shaped requirements**: "Use Postgres for storage" is not a system requirement; "Support 10K transactions per second with ≤100ms p99 latency" is.
- **Missing QASes**: design with only functional capabilities cannot be evaluated. If <3 QASes, that's a flaw.
- **Implicit stakeholders**: the system is built for someone. If "user" is the only stakeholder named, dig deeper — there are usually 3-5 distinct ones.
- **Scope creep at this level**: section 5 (functional capabilities) over 30 bullet points is suspicious.
- **No "out of scope"**: every system has scope edges. If section 8 is empty, you didn't think hard enough.

## REFINE step

For each flaw, classify SCOPE-LOCAL or SCOPE-UPSTREAM.

Phase 1 has no upstream (it's the first phase), so flaws can only be:
- SCOPE-LOCAL: fix in `phase-1-system.md.DRAFT`
- **SCOPE-EXTERNAL**: requires new information from user (e.g., "what's the actual SLA target?"). Treat as a blocker — write open question, ask user, do not invent.

## Hand-off to Phase 2

Phase 1 APPROVED means:
- All sections filled (open questions resolved or explicitly deferred)
- All QASes specific enough to evaluate an architecture against
- All scope boundaries clear

If any of these is fuzzy, do not approve. Phase 2 will paint over the fuzziness, and Phase 3 will find the cracks, and you'll backtrack — wasting work.

## Templates

- See `templates/qas.md` for the QAS structure
- ADRs are not produced at Phase 1 (they're a Phase 2 artifact); architectural decisions don't yet exist
- A simple Markdown file is enough; no diagrams required at this phase (Phase 2 produces diagrams)
