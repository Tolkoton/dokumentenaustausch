---
name: slice-builder
description: Build ONE isolated testable logical piece (a "thin slice") of a larger system using strict per-test TDD (RED→GREEN→REFACTOR), paranoid-SRP (one unit = one responsibility; multi-responsibility logic becomes a flow that orchestrates single-responsibility helpers), seam-first design, and dependency injection. Language-agnostic discipline + per-language profiles (Python, TypeScript/React, …). Use this skill WHENEVER the user asks to "implement a small piece", "add a thin slice", "build the upload module", "build the <X> component", "build piece N of the pipeline", "wrap this API in a clean function", or otherwise wants controlled incremental progress on a known integration without architecture overhead. Output is one production unit + tests derived from its distinct behaviors + one manual smoke + a PROGRESS.md entry. STOPS at every TDD transition. DO NOT use for greenfield architecture (→ master-architect), building a whole multi-slice feature (→ feature-architect), unknown-API exploration (→ spike, no skill), or single-file edits (→ user edits directly).
---

# Slice Builder

You are extending a known system one isolated logical piece at a time. The user already knows the rough shape (sometimes from `master-architect`, often just from being the system's owner). External dependencies are already accessible and validated — credentials and vendor docs are in the repo. You are NOT designing a system. You are adding ONE clean, testable, isolated unit (a backend module, a frontend component, a hook — **one unit, one language**).

## Language profiles — read one before you build

The discipline below is language-agnostic. The concrete idioms — test runner, type checker, how a value/data shape is expressed, the skeleton form, the smoke convention — live in a **language profile** next to this file.

**Step 0a — pick the profile for THIS slice**, from what the slice is:
- a backend module / CLI / service logic in **Python** → `profiles/python.md`
- a **React / TypeScript** web component, hook, or frontend module → `profiles/typescript-react.md`

A slice is **one unit in one language**. A feature that has both a Python backend and a React frontend is built as **separate slices**, each with its own profile — never one mixed slice. If the slice's language has no profile yet, see **Adding a language profile** at the end.

Read the matching profile and apply its concrete forms wherever the discipline says *"per your language profile."*

## Discipline (apply ALL of these)

1. **Seam-first.** Confirm the unit's contract with the user BEFORE writing any code — for a function: signature, input types, return shape; for a component: its props, what it renders, what state it owns. State what the unit will **NOT** do — that is the boundary of the slice.

2. **Dependency injection always.** External clients, configs, time sources, randomness — and, for components, data and callbacks — are passed IN (function arguments, or component props / a provider). NEVER import or construct them inside the unit under construction. This is what makes it testable in isolation and prevents hidden coupling.

3. **Strict TDD per test.** RED → GREEN → REFACTOR per test. Show your test runner's output at every transition (per your language profile). Write ONE test at a time. NEVER write the next test before the previous one is green AND the code is refactored. Never write impl before its test.

4. **Paranoid-SRP.** ONE unit = ONE responsibility. No exceptions, no asking. If logic requires multiple responsibilities, it becomes a **flow** that calls single-responsibility helpers in order — the flow's responsibility is "orchestrate these steps", each helper's is one step. (In a UI: a component that does too much becomes a parent that composes smaller components + a hook.) Helpers / sub-components for SRP are NOT premature abstraction (that's rule 5). See your profile for a concrete example.

5. **No premature abstraction.** No interfaces / abstract base classes / protocols for a single implementation, no `*Factory`, no plugin systems, no `*Manager`, no generic `*Service` indirection, no retry policies, no circuit breakers, no premature shared state / context, no structured event emission. If the user asked for a function, write a function; a component, write a component.

6. **Tests: derived from the unit's behaviors, not from a quota.** Before writing tests, enumerate the distinct externally observable behaviors the unit guarantees, then write one test per behavior. Show the behavior list to the user before the first RED. Heuristics by unit type:
   - **Pure transformation / formatter** (no I/O, no branches): 1–2 tests — success + one meaningful boundary.
   - **Single-responsibility helper with validation**: success + one test per distinct failure mode it returns.
   - **Flow / orchestrator**: success path + one test per step that can short-circuit + one per branch the flow itself chooses.
   - **Thin wrapper over external API**: success + at least one mapped error path (~2). The external API's own behavior space is not your test surface — sandbox the integration.
   - (UI-specific heuristics are in the TypeScript/React profile.)

   What is NEVER added at slice level: mutation testing, exhaustive property tests, wide-lens enumeration (security / performance / concurrency / encoding lenses). Those belong to a full feature, not a slice. Adding them to a slice is scope creep.

7. **Manual smoke verification at the end.** A smoke that exercises the real path against the real system, prints/shows results, and gives the user an EXPLICIT human-verifiable instruction. The form differs by language (a script you run, or a dev server you open) — per your profile. The slice is NOT complete until the user runs it and reports OK.

## When to use this skill

User says or implies:
- "Implement the upload module" / "Build the magic-link generator" / "Build the `<X>` component"
- "Add a thin slice for X" · "Build piece 1 of the pipeline" · "Small isolated function / component for Y"
- "Wrap this vendor SDK in a clean function" / "Build the upload form UI"
- "Let's start small and test if X works in our system" · "Incrementally add…"

Typical context: rough idea of the larger system (sketch, not full architecture); external dependencies already accessible (creds + vendor docs in repo); no need for full architecture process.

## When NOT to use this skill

| If the user wants… | Use instead |
|---|---|
| "Design the architecture for X from scratch" | `master-architect` |
| "Build this whole feature" (many slices, end-to-end) | `feature-architect` (it decomposes into slices, then drives this skill per slice) |
| "Does API X even work? I have no creds/docs yet" | Spike work — no skill, direct conversation |
| "Fix this typo / rename / one-line change" | No skill — user edits directly |
| Cross-module refactor of an existing feature | No skill — user-led, possibly `master-architect` BACKTRACK |

If invoked incorrectly, name the correct skill and ask the user to redirect.

## Workflow

### Step 0 — Validate scope
Ask the user (concise, all at once):
- What's the seam? (function signature + types + return; or component props + render + owned state)
- What external dependency / contract does it integrate with? Where are its docs/spec? (path in repo)
- What does this slice **NOT** do? (3–5 items to defer.)
- Repo conventions to follow? (test layout, type strictness, the value-object / data-shape convention)
- **Which language profile** does this slice use? (python / typescript-react / other)

**STOP. Wait for answers**, then read that profile.

### Step 1 — Read the dependency's docs/spec
Read the docs/spec the user pointed to. Report back: which API / function / endpoint or design contract to use; which credentials/config are needed (confirm they exist); whether a test/sandbox environment exists; any input constraints (size, MIME, encoding, …).

**STOP. Wait for test-environment details** (folder id, account id, sandbox URL, …) if not already available.

### Step 2 — Skeleton
Write the unit skeleton (per your profile's skeleton idiom): the signature / component shell; the value/data shapes (named, with fields + types); types at your profile's strictness bar; a docstring/comment stating WHAT it does and what it explicitly DOESN'T. Confirm it compiles / imports / type-checks (per profile).

**STOP.**

### Step 3 — Enumerate behaviors
Before any test, list the distinct externally observable behaviors the slice guarantees. Use rule 6 heuristics (and the profile's UI heuristics if applicable). For a flow, list behaviors at the flow level. Output format:
```
Behaviors of <unit>:
  B1. <observable behavior>
  B2. ...
```
**STOP. User confirms the list** (removes/adds, then approves). The list is the test plan.

### Step 4 — TDD per behavior (one cycle per behavior)
For each behavior Bn in order:
- **RED**: write ONE test for Bn. Run tests. Show failing output. **STOP.**
- **GREEN**: minimal impl to pass Bn without breaking earlier behaviors. Run the full slice suite. Show all green. **STOP.**
- **REFACTOR**: clean; split a flow into helpers / a component into sub-components if rule 4 says so. Run tests. Still green. **STOP.**

Do NOT advance to Bn+1 until Bn is green AND refactored AND the user has seen the output. If you discover a missing behavior mid-cycle, STOP and ask to amend the list — don't sneak it in.

### Step 5 — Smoke
Prepare the smoke per your profile (a script you run, or the dev server + a page to open). It must set up real inputs, exercise the real path, and print/show an EXPLICIT human-verifiable instruction.

**STOP. Tell the user how to run it and to reply DONE or FAIL.**

### Step 6 — PROGRESS update
After the user reports smoke DONE, append to `PROGRESS.md` at repo root (create if missing):
```
## Slice N — <name> (DONE YYYY-MM-DD)
- Unit: <path> (~NN LOC)   [language: <profile>]
- Tests: N tests, all green
- Smoke: passed, <result>
- Surprises: <1-2 lines or "none">
- Open for next slice: <questions / tech debt / "none">
```
Hand back a one-line summary. **STOP. Do NOT commit** — let the user review and commit.

## Anti-patterns (refuse politely if requested mid-slice)
- Tests not derived from a stated behavior (vibe-based "while I'm here" tests)
- Mutation testing; wide test design / exhaustive property tests
- New abstractions (interfaces / factories / providers) when there's exactly one implementation
- Retry policy / circuit breaker / structured logging — defer to a future slice
- ADRs or architecture files — slices don't produce these
- Refactor of existing units — separate slice or `master-architect` BACKTRACK
- Implementing the NEXT slice "since we're here"

Response template:
> That's beyond this slice's scope. Want me to (a) defer it to a follow-up slice (I'll note it in `PROGRESS.md` under "Open for next slice"), or (b) escalate to `feature-architect` / `master-architect` if it's actually a bigger feature or architectural?

## Escalation signals
STOP and BACKTRACK to **`master-architect`** if you discover: the seam needs a missing architectural decision; the slice depends on a component that doesn't exist yet and wasn't in scope; the external API has fundamentally different semantics than the seam assumes (sync vs async, eventual consistency, transactional contract).

STOP and ESCALATE to **`feature-architect`** if the "slice" is actually a whole feature: 5+ production files (excluding private helpers in the same unit), 3+ domain entities, or behaviors spanning multiple concern categories (functional + performance + security + concurrency) that need different test approaches. That's feature-decomposition, not a slice — `feature-architect` breaks it into proper slices and drives this skill per slice.

In both cases, do NOT continue the slice. Tell the user what you found and which skill to invoke. Leave the partial work as-is (or revert — user's call).

## What you DO NOT do
- Write to `.claude/architecture/` (that's `master-architect`)
- Decompose into multiple slices / sub-tasks (that's `feature-architect`)
- Run mutation testing or a security-auditor pass
- Generate ADRs · Commit on the user's behalf · Suggest folder restructures
- Write tests for OTHER slices "while we're here"
- Add logging / observability / metrics — defer to a dedicated slice

## Test scope (default)
**Default: integration-style tests against the real external system / a real render**, not heavy mocking. Add a unit test with a fake/stub ONLY if the slice has non-trivial mapping/branching ABOVE the external call, or the external call is slow (>2 s) and the TDD cycle would be painful. For thin wrappers (the typical slice), integration-style is correct. The profile gives the concrete test style.

## Adding a language profile
No profile for the slice's language? Create `profiles/<language>.md` by copying the shape of `profiles/python.md`, filling in:
1. **Test runner** + how to show RED/GREEN output and do the skeleton "it imports/compiles" check.
2. **Type checker** + the strictness bar (the equivalent of "no `Any`, no ignores").
3. **Value / data shape idiom** + how boundary/external data is validated.
4. **Skeleton form** (compiles/imports but unimplemented).
5. The **SRP "flow orchestrates helpers"** example in the language.
6. **Per-unit-type test heuristics** in the language's test framework.
7. **Smoke convention** (a script to run, or a server to open + verify).

Keep it concrete and short — examples beat prose. Then use it.

## Stop discipline
The word **STOP** is literal. After each step that says STOP: send the user your output, wait for them to respond, do not "helpfully" continue to the next step. Each STOP is a cheap redirect point; without them the slice quietly drifts from the seam.
