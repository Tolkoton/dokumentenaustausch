# Decomposition Heuristics

Patterns for splitting an oversized task into vertical-slice sub-tasks. Used by feature-architect.

## The cardinal rule: vertical slices

A vertical slice ships behavior end-to-end. Layer-only sub-tasks ("first the model, then the service, then the endpoint") are an anti-pattern because:
- The model-only sub-task has no testable behavior
- Tests of one layer in isolation don't catch integration bugs
- Each layer-only sub-task touches many files for no user-visible value

Better: each sub-task is a "thin slice through the cake" — minimal model + minimal service + minimal endpoint, all working together for ONE behavior.

```
BAD (horizontal layer splits):
  t007a: All user models       ← no testable behavior
  t007b: All user services      ← can't be tested without 007a
  t007c: All user endpoints     ← can't be tested without 007b

GOOD (vertical slice splits):
  t007a: Register endpoint, happy path only (minimal model + service + endpoint)
  t007b: Add duplicate-email rejection (extends t007a)
  t007c: Add password policy (extends t007a)
```

## Common splitting patterns

### Pattern 1: Capability split

When the task description has multiple independent capabilities joined by "and":

```
Original: "Add user registration, login, and password reset endpoints"
Split:
  t007a: User registration (POST /register)
  t007b: User login (POST /login)
  t007c: Password reset (POST /password-reset/initiate + /complete)
```

Each sub-task is independently shippable. May share infrastructure (User entity exists after t007a), but each adds distinct user-facing value.

### Pattern 2: Behavior-progression split (thin-then-thick)

When a single endpoint has many features but ONE happy path:

```
Original: "Implement /register with email validation, duplicate detection,
         password policy, captcha, rate limiting, audit logging, welcome email"
Split:
  t007a: /register happy path with email validation (minimal)
  t007b: Add duplicate-email rejection
  t007c: Add password policy enforcement
  t007d: Add captcha and rate-limiting (security hardening)
  t007e: Add audit logging and welcome email (cross-cutting)
```

Each builds on the previous. t007a ships a working endpoint; later sub-tasks enhance it. Crucially, t007a's tests still pass after t007b-e are added (no regression).

### Pattern 3: CRUD split

When a task says "Implement CRUD for X":

```
Original: "Add CRUD operations for Article"
Split:
  t007a: Create Article (POST /articles)
  t007b: Read Article (GET /articles/<id>, GET /articles)
  t007c: Update Article (PUT/PATCH /articles/<id>)
  t007d: Delete Article (DELETE /articles/<id>)
```

Sometimes 007a + 007b combine into "Article persistence + read" because that's how minimum useful behavior emerges (you need read to verify creation). Use judgment.

### Pattern 4: Path-progression split (happy → error → edge)

When a task has many error cases or edge cases:

```
Original: "Implement /charge endpoint with all error handling"
Split:
  t007a: /charge happy path with valid card
  t007b: /charge error handling (insufficient funds, invalid card, network error)
  t007c: /charge edge cases (concurrent charges, idempotency, retries)
```

Use sparingly — usually means the original task was under-thought. Better to merge tightly if errors are simple.

### Pattern 5: QAS-hardening split

When functional behavior + non-functional behavior are both substantial:

```
Original: "Implement /search endpoint with <100ms latency, 1000 req/sec
         capacity, and full-text relevance ranking"
Split:
  t007a: /search functional correctness (relevance ranking)
  t007b: /search performance optimization (caching, index hints)
  t007c: /search load handling (rate limiting, queue, monitoring)
```

Each QAS dimension can be a separate sub-task. The functional one ships value; later QAS sub-tasks harden it.

### Pattern 6: Phase split (build → instrument → harden)

When a feature legitimately has multiple "rounds" of work:

```
Original: "Implement payment processing with full observability and recovery"
Split:
  t007a: Build payment processing (functional)
  t007b: Add observability (logging, metrics, tracing)
  t007c: Add recovery (idempotency, retries, dead-letter handling)
```

Most tasks DON'T split this way (observability and recovery should be in design from start). Use only when phases are genuinely independent.

## Splitting signals

Look for these in the task to identify the right pattern:

| Signal | Pattern likely useful |
|--------|----------------------|
| Multiple capabilities joined by "and" | Capability split (#1) |
| One endpoint, many feature toggles | Behavior-progression (#2) |
| "Implement CRUD for X" | CRUD split (#3) |
| ">5 error cases" or ">8 acceptance criteria" | Possibly path-progression (#4) but verify each path needs separate work |
| Multiple QAS dimensions, each substantial | QAS-hardening (#5) |
| Cross-cutting concerns separable | Phase split (#6) |
| Single capability, single QAS, single happy path | UNSPLITTABLE — task is appropriately sized |

## When NOT to split

- **Already S complexity**: ≤2 files, ≤5 tests, ≤100 LOC est. Just implement.
- **Already M complexity**: ≤4 files, ≤15 tests, ≤200 LOC est. Implement unless user has explicit reason to split (e.g., parallelize).
- **Single atomic capability**: e.g., "Add a single utility function" — split has no value
- **Splitting makes coupling worse**: if sub-task A and B have cyclic concerns (each needs the other's behavior), don't split

## DAG construction

For each sub-task, declare `depends_on`:

```yaml
- id: t007a
  parent: t007
  order: 1
  depends_on: [t001, t002]      # inherited from parent

- id: t007b
  parent: t007
  order: 2
  depends_on: [t007a]            # builds on a

- id: t007c
  parent: t007
  order: 3
  depends_on: [t007a]            # also builds on a (parallel to b)

- id: t007d
  parent: t007
  order: 4
  depends_on: [t007a, t007b, t007c]  # needs all of the above
```

Rules:
- Don't add artificial sequencing. If b and c don't actually need each other, declare them parallel.
- Don't create cycles. DAG must be acyclic.
- Each sub-task should inherit parent's `depends_on` unless dropping it makes sense (rare).

## Sub-task complexity calibration

Aim for:

| Complexity | LOC est | Files | Tests | Time est |
|-----------|---------|-------|-------|----------|
| S | <100 | 1-2 | 3-8 | <30 min |
| M | <200 | 2-4 | 8-15 | 30-90 min |
| L | <300 | 3-5 | 15-25 | 90+ min — should usually be split |

Sub-tasks SHOULD be S or M. If a sub-task is still L → recurse: feature-architect splits it further.

## Acceptance criteria distribution

Parent task has criteria ac1, ac2, ac3, ac4, ac5, ac6.

Distribute across sub-tasks:

```
t007a covers: ac1, ac3 (happy path criteria)
t007b covers: ac2 (duplicate detection criterion)
t007c covers: ac4 (password policy criterion)
t007d covers: ac5, ac6 (linting, type-check — covered when t007a-c done)
```

Rules:
- Every parent criterion must map to ≥1 sub-task
- A criterion can be split if it has compound parts (e.g., "register validates email AND rejects duplicates" → split criterion across two sub-tasks)
- Cross-cutting criteria (linting, type-check) can be implicit (covered by ALL sub-tasks completing their own slice)

## Files distribution

Parent task touches: [router.py, service.py, repository.py, models.py, test_service.py, test_register_e2e.py, test_register_security.py].

Each sub-task gets a subset:

```
t007a: router.py (modify), service.py (new), repository.py (new),
       models.py (new), test_service.py (new), test_register_happy.py (new)
       → 5 files (4 new, 1 modified). Within M complexity.

t007b: service.py (modify), test_service.py (modify),
       test_register_duplicate.py (new)
       → 3 files (1 new, 2 modified). S complexity.

t007c: service.py (modify), test_service.py (modify),
       test_register_password_policy.py (new)
       → 3 files (1 new, 2 modified). S complexity.

t007d: (security hardening — separate concerns)
       test_register_security.py (new), middleware/captcha.py (new),
       middleware/rate_limit.py (new)
       → 3 files (3 new). M complexity.
```

Each sub-task is independently runnable as a feature-implementer session.

## Edge cases

### Task imports new dependencies

If parent task introduces a new library (e.g., Stripe SDK), the first sub-task should add the dependency and have a "library can be imported" smoke test. Later sub-tasks use it.

### Task touches multiple containers

If parent crosses 2+ Phase 2 containers, EACH container should typically be its own sub-task, with an explicit interface task between them.

```
Original: "Add user-service that emits events to notification-service"
Split:
  t007a: user-service emits UserRegistered event (Container 1)
  t007b: notification-service subscribes to UserRegistered (Container 2)
  t007c: Wire UserRegistered event schema (interface, can be parallel)
```

The interface sub-task (t007c) documents the event schema and ensures both containers agree. Sometimes folded into t007a.

### Task is partially implemented

If a parent task is already in progress (e.g., feature-implementer hit 300 LOC ceiling), feature-architect splits the REMAINING work:

```
- id: t007
  status: PARTIAL
  partial_split_into: [t007-remaining-a, t007-remaining-b]
  # implementation so far covers ac1, ac2 (mark in PROGRESS.md)

- id: t007-remaining-a
  parent: t007
  order: 1
  depends_on: [t007]              # depends on the partial work
  description: "Complete t007 remaining: ac3, ac4"
  ...
```

This is awkward but represents reality. Better to split before hitting the ceiling.

## Anti-patterns

- **Layer splits**: model/service/endpoint as separate sub-tasks → no behavior in early ones
- **Over-splitting**: 6 sub-tasks for a task that could be 2 — overhead exceeds value
- **Under-splitting**: leaving still-L sub-tasks → defers the problem
- **Artificial sequencing**: declaring depends_on where no dependency exists → bottlenecks parallel work
- **Splitting acceptance criteria semantically wrong**: each criterion should map cleanly to one sub-task, not be spread thin
- **Forgetting the parent**: parent task must be marked SPLIT_INTO, never DONE
- **No DAG validation**: cycle in depends_on is a serious bug — verify acyclicity
- **Sub-tasks of sub-tasks indefinitely**: split a sub-task that's still L → fine. But if you're splitting THAT, the original was way too big — consider master-architect Phase 2 review
