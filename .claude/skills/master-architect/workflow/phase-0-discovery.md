# Phase 0 — Problem Discovery

**Goal**: gather enough context about the problem, users, constraints, and risks before Phase 1 system design. NOT problem validation — we assume the problem exists; we want clarity on its shape.

**Status**: optional. User can skip with `"skip discovery"`, `"I have a brief"`, `"start at phase 1"`. When skipped, `INDEX.md` marks Phase 0 `SKIPPED` and Phase 1 starts cold (you'll then ask Phase 1 questions as needed).

**Maps to**: pre-architecture discovery / `arch-elicit` from the Architecture knowledge base.

## What "approved Phase 0" looks like

A single Markdown file `phase-0-brief.md` with these sections:

1. **One-paragraph problem statement** — what is the user trying to solve, in plain English. Their words where possible.
2. **Greenfield or brownfield** — is this a new system or modification to existing? If brownfield, what exists today?
3. **Primary stakeholders sketch** — who's affected; 3-5 named roles (sharper definition comes in Phase 1).
4. **Hard constraints surfaced** — anything user mentioned as fixed (deadline, team, budget, regulation, infrastructure).
5. **Quality attribute hints** — anything user emphasized about how the system must perform (used as raw material for Phase 1 QASes).
6. **Domain glossary seeds** — 3-10 domain-specific terms the user used, with one-line definitions if they provided context.
7. **Known unknowns** — questions the user couldn't answer, flagged for follow-up.
8. **Early risks** — non-obvious things that could go wrong, surfaced through discovery.

Optional companion files:
- `phase-0-risks.md` — if ≥3 substantive risks identified, expand into a risk register (otherwise inline in section 8)
- `phase-0-glossary.md` — if ≥5 terms identified, expand into a proper glossary (otherwise inline in section 6)

Length: 100-300 lines for typical projects. This is not the design — it's the context.

## GENERATE step — pose questions

Phase 0 generation = ask the user questions. Use `references/elicitation-questions.md` as the master question set. Adapt based on:

- **Greenfield**: focus on problem definition, users, success metrics, hard constraints
- **Brownfield**: focus on current state, pain points, what's working, what's not, integration points
- **Project size**: hobby/small startup/team — adjust depth accordingly
- **User signals**: if user has volunteered specific concerns (e.g., "I'm worried about scale"), ask follow-ups there first

### Question budget

Don't ask everything. The `references/elicitation-questions.md` has 15-20 questions, but you don't need all. Budget:

- **Lightweight discovery**: 5-7 questions (user wants to move fast, problem is simple)
- **Standard discovery**: 8-12 questions (default)
- **Deep discovery**: 12-18 questions (user is fuzzy on the problem, or stakes are high)

Detect intent: if user provided a clear paragraph upfront with most of the answers, go lightweight; if they wrote "design me a thing for X", go standard.

### How to ask

**Batch questions**, don't drip them one at a time:

```
Before we start designing, I have 8 questions that will save us backtracking later.
Feel free to say "skip" or "I don't know" on any of them — those are valid answers
and just mark the unknown for later.

1. [...]
2. [...]
...
8. [...]
```

This respects user's time. If they give terse answers, you can ask follow-ups in batch 2 (max 3-5 questions). Never go past 3 batches without finalizing the brief.

### Sample question categories

Pull from `references/elicitation-questions.md`. Categories:

- Problem and value
- Stakeholders and users
- Functional shape (what does it DO, not how)
- Quality emphasis (what must be true non-functionally)
- Constraints (hard limits)
- Existing context (brownfield)
- Risks and worries
- Definition of done (Phase 1 hint)

## CRITIQUE step — check completeness

After user provides answers, write `phase-0-brief.md.DRAFT` and critique it against `checklists/discovery-critique.md`.

Critique here is structurally different from later phases — you're not finding design flaws (no design exists yet), you're finding **gaps in understanding**.

Each flaw is classified as:
- **SCOPE-LOCAL**: you can fix in the brief (e.g., rephrase ambiguous section, organize better)
- **SCOPE-EXTERNAL**: needs more user input (you have a gap, user must fill)

For each SCOPE-EXTERNAL flaw, generate a follow-up question.

## REFINE step — follow-up questions or rewrite

If you have SCOPE-LOCAL flaws only: rewrite brief, re-critique. If clean, proceed to approval.

If SCOPE-EXTERNAL flaws exist: batch follow-up questions (≤5), wait for user answers, integrate, re-critique. If still gaps after 2 rounds of follow-up, **accept the gaps** — write them in section 7 (Known unknowns) explicitly and move on.

Don't loop forever. Discovery has diminishing returns. After 3 rounds of Q&A, escalate to user: "I have the following 3 known unknowns left. Should we proceed to Phase 1 with these as open questions, or do you want another round of discovery?"

## APPROVAL step

Present `phase-0-brief.md.DRAFT` to user. User says:
- `approved` → rename to `phase-0-brief.md`, update INDEX.md, move to Phase 1
- `revise: <note>` → integrate feedback, re-critique
- `skip the rest, go to phase 1` → mark Phase 0 SKIPPED with brief saved as `phase-0-brief.md` (preserve the partial work)

## Handoff to Phase 1

Phase 0 APPROVED (or SKIPPED with partial brief) means Phase 1 starts with:
- The brief as the primary input
- Known unknowns as Phase 1's "Open questions" section to track
- Glossary seeds as the starting glossary
- Quality attribute hints as the starting point for QASes

Phase 1 will sharpen everything. The brief is raw clay; Phase 1 shapes it.

## What NEVER happens in Phase 0

- Architecture decisions
- Technology choices
- Style selection (monolith vs microservices, etc.)
- Component design
- Code

Anything that says HOW belongs in Phase 2+. If user pushes for HOW answers during Phase 0, defer politely: "Good question — that's a Phase 2 decision. Let me note it as a constraint or risk and we'll address it there."

## Skipping Phase 0

When user signals skip:
- Mark Phase 0 status as `SKIPPED` in INDEX.md
- Optionally write a minimal `phase-0-brief.md` from whatever context exists in the conversation (user's initial request, prior chat history)
- Note in PROGRESS.md: "Phase 0 skipped at user request; Phase 1 starting cold"
- Proceed to Phase 1, which will ask its own questions as needed

Skipping is a valid optimization for users who arrive with a written spec.

## Anti-patterns to avoid

- **Death by questions**: more than 12 questions in one batch. People give up.
- **Yes/no fishing**: questions that are answerable with "yes" or "no" don't surface much. Prefer open-ended.
- **Leading questions**: "Don't you think we should use microservices?" → never.
- **Premature solution probing**: "What database do you want?" → that's Phase 2.
- **Skipping CRITIQUE**: even Phase 0 critique step catches gaps. Don't auto-approve user's first answers.
