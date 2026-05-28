# Phase 2 — Architecture Critique Checklist

Apply during CRITIQUE step of Phase 2. For each item: PASS / FAIL / UNCERTAIN. For each FAIL, classify SCOPE-LOCAL or SCOPE-UPSTREAM (Phase 1).

## Architectural style

- [ ] An architectural style is named (not "we'll figure it out as we go")
- [ ] Style is justified by reference to at least one Phase 1 QAS
- [ ] Style is well-suited to team size and skills from Phase 1 constraints
- [ ] If "microservices" is chosen: team is ≥3 people AND has ops expertise (otherwise flag SCOPE-LOCAL: revisit)
- [ ] If "monolith" is chosen: this is acknowledged explicitly with rationale (not just default)

## Container model

- [ ] Each container has explicit name, responsibility, and exposed interface
- [ ] Each container has its dependencies listed (which other containers it talks to)
- [ ] No container has >5 inbound dependencies (god-component anti-pattern)
- [ ] No container depends on >5 others (god-client anti-pattern)
- [ ] Container count is reasonable (typically 3-12 for non-microservice systems; >12 = either microservices or over-decomposition)
- [ ] Each container maps to at least one Phase 1 functional capability
- [ ] Each Phase 1 functional capability maps to at least one container

## QAS ownership

- [ ] Every Phase 1 QAS has a named container owning its satisfaction
- [ ] If a QAS is system-wide (e.g., availability), the responsibility is clear (e.g., "load balancer + container A and B with redundancy")
- [ ] Performance QASes have explicit budgets per container if cross-container

## Data flow

- [ ] For each Phase 1 user journey, a data-flow walkthrough exists
- [ ] Data shapes at container boundaries are noted (link to or include Pydantic models)
- [ ] Async vs sync flow is explicit at each step

## Cross-cutting concerns

- [ ] **Authentication**: where it happens, which container owns it, how it propagates
- [ ] **Authorization**: distinct from authn, explicitly addressed
- [ ] **Logging**: format, destination, what's logged at boundaries
- [ ] **Error handling**: structured error types, propagation rules, user-facing vs internal errors
- [ ] **Configuration**: how config is loaded (Pydantic Settings recommended), where secrets live
- [ ] **Observability**: metrics, tracing, alerting — at minimum a stance
- [ ] **Persistence**: where state lives, transaction boundaries, consistency model

## Technology choices

- [ ] Each container has language/framework/DB stated
- [ ] Each non-obvious tech choice has an ADR
- [ ] Tech choices match Phase 1 constraints (e.g., team skills, budget)
- [ ] No technology is chosen "because it's the new hotness" without ADR-level justification
- [ ] Versioning of major dependencies is noted (e.g., "Python 3.12+, FastAPI 0.115+, Pydantic 2.x")

## ADRs

- [ ] Each ADR has: Context, Decision, Status, Consequences (positive AND negative)
- [ ] Each ADR is about an irreversible-or-expensive-to-reverse choice
- [ ] No ADR is about a trivial decision (e.g., naming)
- [ ] ADRs are referenced from the relevant container/decision in the main document

## SRP at component level (paranoid-srp delegation)

Delegate to `paranoid-srp-python` skill — these are the questions it should answer:

- [ ] Each container has a single reason to change
- [ ] No container has "and" in its responsibility description ("manages users AND sends notifications" = split)
- [ ] Containers don't share mutable state (only data via explicit interfaces)
- [ ] No container is a "manager" or "coordinator" without specific scope (vague names hide SRP violations)

## Testability (tdd-enforcer delegation)

Delegate to `tdd-enforcer-python` — these are the questions:

- [ ] Each container can be tested in isolation (dependencies can be mocked at interface)
- [ ] Cross-container integration tests have a clear strategy
- [ ] Heavy dependencies (DB, external APIs) are abstracted behind interfaces
- [ ] Architecture supports the test pyramid (unit > integration > e2e)
- [ ] No container requires "the whole system running" to test (red flag)

## Boundary data (pydantic-v2-conventions delegation)

Delegate to `pydantic-v2-conventions` — these are the questions:

- [ ] All cross-container data is Pydantic models (`BaseModel`)
- [ ] Models at boundaries use `strict=True` and `frozen=True` config
- [ ] Discriminated unions used where polymorphic events cross boundaries
- [ ] No raw dicts/tuples cross container boundaries

## Security (security-auditor delegation, if security-relevant)

- [ ] Authentication mechanism is named (OAuth2, JWT, session, etc.)
- [ ] Authorization model is named (RBAC, ABAC, ACL, etc.)
- [ ] Input validation strategy is explicit and at the right boundary (the earliest one — at the API edge)
- [ ] Secrets handling is explicit (env vars, vault, etc. — not hardcoded)
- [ ] Audit trail is mentioned for state changes (or explicit "not required")
- [ ] TLS/encryption-in-transit assumed and stated
- [ ] Encryption-at-rest stated if sensitive data
- [ ] No security control is "we'll add it later" (architectural debt)

## Karpathy pre-action checks (cross-cutting)

- [ ] **Silent assumptions**: every "obvious" choice is explicit. "It's a Python project" must appear in writing.
- [ ] **Over-complication**: no unrequested architectural pattern. If user didn't ask for event sourcing, you'd better have a hard QAS forcing it.
- [ ] **Unrequested scope**: no container exists that wasn't justified by Phase 1.

## Phase 1 consistency

These flags trigger SCOPE-UPSTREAM (backtrack to Phase 1):

- [ ] No QAS contradicts architecture style choice
- [ ] No Phase 1 constraint is violated by tech choice
- [ ] No Phase 1 capability is unimplementable in this architecture
- [ ] No "out of scope" item from Phase 1 has snuck back in as a container
- [ ] Team-size constraint is compatible with operational complexity of architecture

## Final pass

- [ ] Document length is 400-1200 lines (outside this range = either under- or over-specified)
- [ ] Every section from `workflow/phase-2-architecture.md` is present
- [ ] No section says "TBD" without a corresponding open question for Phase 3
- [ ] If you handed this document to a different architect, they could produce Phase 3 layout from it
