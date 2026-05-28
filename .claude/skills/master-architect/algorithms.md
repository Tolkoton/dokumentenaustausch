# Self-Learning Algorithms Catalog

Reference for master-architect's DEEP track. Consulted when STAKES ASSESSMENT triggers escalation. **Do not consult on BASIC track** — defaults are good enough and faster.

Distilled from 2024-2026 research on self-improving agentic systems (Reflexion, Self-Refine, CRITIC, SWE-agent, ToT, Voyager, multi-agent debate, etc.).

## How to use this file

When master-architect determines DEEP track for a phase:
1. Read the **Generation algorithms** section, pick best match for the problem
2. Read the **Critique algorithms** section, pick best match
3. Read the **Refinement algorithms** section, pick best match
4. Announce all three choices to user with one-line reasoning each before proceeding

Default DEEP picks (when no clear better match exists): ToT for generate, red-team + debate for critique, Self-Refine for refinement.

---

## Generation algorithms

### Tree of Thoughts (ToT) — DEEP DEFAULT

**What**: Generate K candidate "trees" of design alternatives, each explored to depth D, prune internally on a value function, present the best path + one runner-up to the user.

**When**: Multiple plausibly-good designs exist; choice is hard; reversibility is low.

**When NOT**: Routine problems with strong existing precedent. Time-sensitive work. Simple data flows. Cost is 3-5× single-pass.

**Concrete protocol for architecture**:
- K = 3 trees (alternative architectural styles, e.g., layered vs hexagonal vs event-driven)
- D = 2 levels (style → key component decomposition)
- Pruning criterion: violates Phase 1 NFR or QAS
- Output: winner with explicit comparison table to runner-up

**Evidence**: Yao et al. 2023 (ToT for Game of 24). Marginal benefit on standard coding per 2025 SWE-bench analyses, but **valuable for architectural decisions** where you can't undo easily.

### Plan-and-Solve

**What**: First explicit plan ("here is the decomposition"), then solve each plan step.

**When**: Multi-step problem where the decomposition itself is the value. Phase 4 is a natural fit (task decomposition IS plan-and-solve).

**When NOT**: When the answer is one cohesive thing (single design vision), not a sequence.

**Concrete protocol**: Generate plan as Markdown checklist, validate plan with user, then expand each step.

**Evidence**: Wang et al. 2023. Strong on benchmarks where decomposition is the bottleneck.

### Self-Consistency (Vote-of-N)

**What**: Generate N candidate solutions independently, pick the most common pattern.

**When**: Problem has a "right" answer but model is uncertain. Useful for verification, less for creative design.

**When NOT**: Architecture rarely has a "right" answer. Better suited to discrete classifications (e.g., "which DB engine for these query patterns").

**Cost**: N× single-pass; N=5 is typical.

**Evidence**: Wang et al. 2022 (CoT-SC). Best when paired with checkable answers.

### Multi-Agent Generation (rarely used)

**What**: Multiple LLM personas (architect, security, performance, ops) each propose, then synthesize.

**When**: When you genuinely have conflicting concerns and need a steelman of each.

**When NOT**: Default avoid. 2025 research consistently shows single-agent + good prompting matches or beats it on coding-adjacent tasks. Cost is 4-6× single-pass.

**If used**: Limit to 3 personas max, time-box each, force synthesis pass.

---

## Critique algorithms

### Checklist-based self-critique — BASIC DEFAULT

**What**: Walk through `checklists/phase-N-critique.md`, mark each item PASS/FAIL/UNCERTAIN, write rationale for FAILs.

**When**: Every phase, always. Cheapest critique with strong yield.

**Concrete protocol**: Single pass; do not skip items even if obviously PASS — the discipline matters.

### Karpathy pre-action check — BASIC ADJUNCT

**What**: Pre-flight check against three failure modes: silent assumptions, over-complication, unrequested edits/scope creep.

**When**: Phase 1 (especially) and Phase 2. Less relevant for Phase 3-4 where scope is more constrained.

**Delegate to**: `karpathy-pre-action-check` skill if available.

**Evidence**: From Karpathy's "Software 2.0" practice + 2025 community wisdom on agent failure modes.

### Red-team persona — DEEP DEFAULT for critique

**What**: Reroll into adversarial mindset. Try to break the design: "given this architecture, design a failure scenario in <2 sentences" repeated K times.

**When**: Security-relevant, data-integrity-relevant, or reversibility-low designs.

**When NOT**: Internal-only tooling, prototypes, exploratory phases.

**Concrete protocol**:
- 5-10 adversarial scenarios across categories: misuse, partial failure, scale, evolution, malicious input
- Each scenario → "design survives Y/N + how"
- Failures → SCOPE-LOCAL or SCOPE-UPSTREAM flag

**Evidence**: Long-standing security practice; productive for AI-generated designs which underweight failure modes.

### CRITIC (with executable verifier)

**What**: Critique guided by external feedback (tests, type-checker, linter, simulation).

**When**: Phase 2-3 when you can write a small probe (`uv run python -c "..."`) to test architectural claims. Phase 4 acceptance criteria.

**When NOT**: Phase 1 (no executable yet). When verifier doesn't exist for the claim.

**Concrete protocol**: Identify claim → write minimal probe → run → fold result into critique.

**Evidence**: Gou et al. 2024. Strong when verifier is available; without one, falls back to checklist-critique.

### Multi-Agent Debate

**What**: Two LLM personas (proponent / opponent) debate the design over K rounds, judge synthesizes.

**When**: When two competing architectural visions exist and the choice is genuinely ambiguous.

**When NOT**: Default avoid. 2025 research (cited in chat 56d94901) shows it consistently underperforms single-agent reviewer on real codebases. Cost is high.

**If used**: Limit to 2 rounds. Use only after BASIC critique already passed.

### Reflexion (verbal RL between iterations)

**What**: After each refine cycle, model writes "what I missed last time and why" in a memory note, references it in next iteration.

**When**: When phase requires multiple refine cycles. Helps avoid same-flaw-different-spelling.

**When NOT**: Single-iteration phases.

**Concrete protocol**: After each REFINE → CRITIQUE loop, append 1-3 sentence Reflexion note to `.architecture/reflections.md`. Read on each subsequent iteration of same phase.

**Evidence**: Shinn et al. 2023. Subsumed by frontier models' default behavior but still useful as **explicit memory** across sessions.

---

## Refinement algorithms

### Targeted Patch — BASIC DEFAULT

**What**: For each flaw, identify minimum change that resolves it, apply, re-critique.

**When**: Most cases. Flaws are independent and localized.

**Concrete protocol**: CRITIC discipline: reproduce flaw → isolate cause → hypothesize fix → apply → verify fix didn't break elsewhere.

### Self-Refine (full regenerate of section) — DEEP DEFAULT

**What**: Don't patch — regenerate the entire problematic section with the critique as additional context.

**When**: Flaws are systemic (3+ related), or patching one creates another.

**When NOT**: Single-localized flaw. Wasteful and risks regression elsewhere.

**Concrete protocol**: Identify minimal cohesive section containing all related flaws, regenerate that section only (not whole document), re-critique full document.

**Evidence**: Madaan et al. 2023.

### Constitutional Revision

**What**: When refine produces solutions that violate stated principles, apply explicit principle-check loop.

**When**: User has explicit "Iron Laws" (e.g., from CLAUDE.md) and design tends to slide off them. Particularly useful when external skills provide principles (TDD, paranoid SRP, Pydantic conventions).

**When NOT**: When no clear principles exist to revise against.

**Concrete protocol**: After each refine, check each Iron Law explicitly. Failures → re-refine with explicit "must satisfy X" prompt.

**Evidence**: Bai et al. 2022 (Constitutional AI). Effective when principles are crisp.

---

## When NOT to escalate (BASIC track is correct)

The escalation gate biases toward BASIC. Use BASIC when ≥2 of these are true:
- Problem has clear precedent in user's experience or canonical literature
- Decision is reversible (can refactor without major rewrite)
- Blast radius is local (one module, one file, one bounded context)
- User has explicitly said "quick design", "rough sketch", or similar

Cost of unnecessary DEEP: 3-5× tokens, slower iteration, more variance, harder debugging.

Cost of unnecessary BASIC: occasionally need to backtrack. This is acceptable because backtrack is supported.

**When in doubt, start BASIC.** Backtrack is cheaper than over-engineered first-pass.

---

## What is deliberately NOT in this catalog

These were considered and excluded:

- **MCTS / LATS** — Monte Carlo Tree Search variants. Marginal benefit at heavy cost per 2025 research. Reserved for autonomous research agents, not single-developer architecture.
- **Graph of Thoughts** — More general than ToT but less interpretable. ToT is the practical sweet spot.
- **Voyager-style automatic skill creation** — Risky in production. Skills authored by humans + ADR-lite covers same ground safely.
- **Heavyweight memory infra (Letta, Mem0, Zep)** — Overkill. `PROGRESS.md` + `reflections.md` deliver 90% of value at 0% operational overhead.
- **AutoGen-style multi-agent orchestration** — Adds infrastructure burden without clear win for design work specifically. Skills-based delegation is enough.

---

## Updating this file

When DEEP track encounters a case where defaults underperformed:
- Append a one-paragraph "Lesson" note to `.architecture/reflections.md`
- Periodically (every 5-10 lessons) ask user to review and consider promoting a lesson into this file
- Do **not** auto-edit this file — it is curated knowledge, not a growing dump

This file should grow slowly and deliberately. If it doubles in size in a year, that is suspicious and means lessons are being added without curation.
