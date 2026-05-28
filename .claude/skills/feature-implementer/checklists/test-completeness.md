# Test Completeness Checklist (Phase C)

Apply at end of Phase C before transitioning to Phase D. For each item PASS / FAIL.

## Coverage of spec

- [ ] Every acceptance criterion from tasks.yaml is mapped to ≥1 test
- [ ] Each acceptance criterion's test references the criterion ID in docstring
- [ ] No criterion left unmapped (would mean we ship without verifying it)

## Type-driven coverage

- [ ] Every parameter in every public function has at least one test exercising it
- [ ] Every `Annotated[T, Field(...)]` constraint has a boundary test:
  - [ ] Value exactly at the constraint (`min_length=N` → test with N chars)
  - [ ] Value just-violating (N-1 chars → expects ValidationError)
  - [ ] Value just-passing in other direction (N+1, if `max_length` also applies)
- [ ] Every `EmailStr` parameter has malformed-email tests (no @, no domain, IDN)
- [ ] Every `Optional[T]` has both None and Some(T) tests
- [ ] Every `Enum` parameter has tests for each variant + one invalid string (if Enum crosses boundary)
- [ ] Every `Decimal/Money` parameter has 0, negative, very large, precision-edge tests
- [ ] Every datetime has UTC, naive, with-TZ, DST edge tests as relevant

## Error coverage

- [ ] Every error type in design.md has a test that triggers it
- [ ] Every error type has a test verifying its carried data (attributes, message)
- [ ] Every TRY/EXCEPT planned in design.md has tests for each except branch
- [ ] No "catches Exception" without specific tests for each sub-exception type

## Branch coverage (prospective)

- [ ] Every IF/ELSE in design.md has tests for both branches
- [ ] Every ELIF has tests for the elif + the default
- [ ] Every MATCH case has a test + default test if exhaustive

## Properties (Hypothesis)

- [ ] Each candidate invariant from design.md evaluated against the 9 patterns (round-trip, idempotence, commutativity, associativity, identity, oracle, metamorphic, monotonicity, total)
- [ ] At least one property test if any invariant applies
- [ ] 0 property tests is acceptable if no invariant exists (don't fabricate)
- [ ] No "Hypothesis test" that's secretly an example test (single `@given` with trivial input)
- [ ] Property invariants are statable in one sentence

## Integration tests

- [ ] One integration test per external dependency the task touches
- [ ] Integration tests use real or test-double of the dependency (not mocks for what should be real)
- [ ] Database integration tests use proper fixtures (transactional rollback, testcontainers)
- [ ] No integration test for pure functions (waste)

## Security tests (if security-relevant)

- [ ] Security relevance auto-detected per `references/mutation-policy.md`
- [ ] If detected: security tests present
- [ ] If detected: catalog covers input injection, auth bypass, info disclosure, sensitive-data handling (as applicable)
- [ ] If detected: at least 3 security tests
- [ ] If not detected: explicitly noted "not security-relevant" with rationale

## Test categorization

- [ ] Each test has a category: happy / boundary / error / property / integration / security
- [ ] Counts per category recorded in test-plan.md summary table
- [ ] No category over-weighted (e.g., 80% happy path = under-tested errors)

## File placement

- [ ] Each test specifies its target file path
- [ ] Unit tests in `tests/unit/...`
- [ ] Integration tests in `tests/integration/...`
- [ ] Property tests in `tests/property/...`
- [ ] Security tests in `tests/security/...`
- [ ] All paths respect Phase 3 layout conventions

## Test ordering

- [ ] Tests ordered for TDD flow: happy → boundary → error → property → integration → security
- [ ] First test is the simplest happy path (drives initial impl)
- [ ] No test depends on a later test (each is independent)

## Deduplication

- [ ] No two tests covering identical behavior (e.g., "empty email" in two categories)
- [ ] If overlap: kept under most appropriate category, removed from others
- [ ] Property tests subsume the example tests they cover (e.g., commutativity property removes `test_add_2_3_equals_add_3_2`)

## Test plan format

- [ ] Each test has: name, type (unit/integration/property/security), file path, verifies (criterion/derivation source), edge or scenario
- [ ] Property tests have explicit invariant statement
- [ ] Security tests reference threat category (input injection, auth bypass, etc.)

## Sanity-check counts

For typical task:
- [ ] 3-25 unit tests (happy + boundary + error combined)
- [ ] 0-3 property tests
- [ ] 0-3 integration tests
- [ ] 0-5 security tests (only if security-relevant)
- [ ] Total: 5-40 tests

If outside this range: investigate. Too few → likely under-derivation. Too many → likely the task should be split.

## Cross-check with design.md

- [ ] Every public function in design.md has at least one happy test
- [ ] Every error in design.md has a test
- [ ] Every invariant in design.md has either a property test OR multiple example tests covering it
- [ ] Every boundary type has validation tests

## Final pass

- [ ] No "TODO: add test for X" left in test-plan.md
- [ ] No "if time permits" tests (either it's in plan, or it's not)
- [ ] Test plan is concrete enough to start RED-GREEN cycles immediately in Phase D
