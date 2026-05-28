# Design Quality Checklist (Phase B)

Apply at end of Phase B before transitioning to Phase C. For each item PASS / FAIL / UNCERTAIN. For each FAIL, classify SCOPE-LOCAL (fix design.md) vs SCOPE-UPSTREAM (backtrack).

## Domain model

- [ ] Every NEW entity has explicit identity, lifecycle, and invariant list
- [ ] Every NEW value object has validation rules stated
- [ ] Each VO is justified vs NewType (has invariants or behavior, not just a typed wrapper)
- [ ] No domain class doubles as boundary DTO (Pydantic models stay at boundary)
- [ ] Aggregates touched have explicit transactional boundary
- [ ] Domain services exist only when entities can't host the behavior
- [ ] Domain events exist only with subscribers planned

## Public surface

- [ ] Every new function/class has full signature documented (params, return type, all annotations)
- [ ] Every function has explicit preconditions and postconditions
- [ ] Every function lists exceptions it can raise
- [ ] Every function notes its side effects (DB writes, network calls, events)
- [ ] No "private API" leaks into design.md (private names start with `_`, are noted as internal)

## Boundary types

- [ ] Every inbound boundary has a Pydantic model defined
- [ ] Every outbound boundary has a Pydantic model defined
- [ ] All boundary models have `model_config = ConfigDict(strict=True, frozen=True, extra="forbid")` (or explicit deviation noted)
- [ ] No raw `dict`, `tuple`, or untyped data crosses container boundaries
- [ ] Discriminated unions used for polymorphic boundary data
- [ ] Each boundary model has at least one example in design.md

## Error types

- [ ] Every error type listed with: when raised, what it carries, HTTP mapping (if applicable), log level, user-facing message
- [ ] Error type hierarchy is consistent (e.g., all domain errors inherit from `DomainError`)
- [ ] No `Exception` or `RuntimeError` used as a domain error (too generic)
- [ ] No try/except `Exception:` planned in design.md (catches too broadly)

## Dependencies and injection

- [ ] Every dependency in the new code has source, lifetime, and test substitution strategy
- [ ] Constructor or parameter injection used (no module-level dependency lookups)
- [ ] Pure functions distinguished from stateful services in signatures

## Cross-references

- [ ] Every ADR that constrains this task is referenced
- [ ] Every QAS this task addresses is cross-linked
- [ ] Container ownership stated (which Phase 2 container this code lives in)
- [ ] Phase 3 dependency rules are respected (no forbidden imports planned)

## Karpathy pre-action checks

- [ ] **Silent assumptions**: every implicit assumption surfaced. (e.g., "function assumes the input is already validated by middleware" — explicit)
- [ ] **Over-complication**: nothing in design.md is unrequested. Each public function traces to acceptance criteria.
- [ ] **Unrequested scope**: no design element adds capability not in task spec

## Consistency with upstream

- [ ] Design respects Phase 1 system vision (no scope creep beyond Phase 1 capabilities)
- [ ] Design fits within Phase 2 container responsibilities (no responsibility leak)
- [ ] Design follows Phase 3 layout conventions (file paths, naming, module boundaries)
- [ ] No invariant in design.md contradicts Phase 1 QASes

## Backtrack signals (SCOPE-UPSTREAM)

These trigger backtrack to master-architect, not Phase D:

- [ ] Design requires file paths not in Phase 3 layout
- [ ] Design requires container not in Phase 2 components
- [ ] Design needs capability not in Phase 1 functional list
- [ ] Design needs cross-cutting concern not addressed in Phase 2
- [ ] Design implies architectural style decision not made in Phase 2

If any: STOP, write BACKTRACK file.

## Open questions

- [ ] All open questions surfaced explicitly
- [ ] No "I'll figure it out in TDD" deferred decisions
- [ ] Open questions blocked further design until user provides input

If any open question remains: pause, ask user. Don't invent answers.

## Final pass

- [ ] design.md document length is 100-400 lines (outside = either too thin or over-specified)
- [ ] design.md is concrete enough that Phase C can derive tests directly from it
- [ ] design.md cross-references all relevant ADRs and QASes
- [ ] design.md has no TODOs left
