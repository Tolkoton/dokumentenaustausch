# Phase C — Test Design

**Goal**: derive a comprehensive test list LOGICALLY from the spec, not via fixed lens counts. Output is the queue for Phase D's TDD loop.

**Inputs**: Phase B's `design.md`.

**Outputs**: `.architecture/tasks/<id>/test-plan.md` with ordered test list, rationale per test, and category breakdown.

## Why "logical derivation" not "fixed counts"

Magic numbers (15 tests per task, 5 properties per function) fail two ways:
- Trivial functions get over-tested (40 tests for `add(a, b)`)
- Complex functions get under-tested (5 properties for an authentication flow)

Instead: **derive from the spec**. Type signature, acceptance criteria, explicit errors, branch structure, security relevance — each contributes specific tests. Count emerges; doesn't get set.

See `references/test-lens-derivation.md` for the full algorithm with worked examples.

## Step 1: Parse the spec

For each public function/class in `design.md`:

Extract:
- **Type signature**: every parameter, every return type, every annotation
- **Preconditions**: what design.md says must be true at entry
- **Postconditions**: what design.md says must be true at exit
- **Errors raised**: every explicit exception type
- **Side effects**: DB, file system, network, events
- **Cross-references**: which acceptance criteria this function satisfies

For each acceptance criterion:
- The criterion itself becomes at least one test (this is the easy part)
- Plus derived tests below

## Step 2: Mechanical test derivation from types

For each parameter, walk the type and enumerate test cases. From `references/test-lens-derivation.md`:

| Type element | Auto-tests |
|---|---|
| `int` | 0, negative, MAX_INT, expected value, type-coercion attempt |
| `str` | empty, whitespace-only, very long (>10K chars if no max), unicode-edge (emoji, RTL, NUL), expected |
| `bool` | True, False |
| `Optional[T]` | None case + each T case |
| `list[T]` | empty, single-element, multi, duplicates if order-sensitive |
| `dict[K, V]` | empty, single key, K collision, V variants |
| `Decimal/Money` | 0, negative, very large, dropped precision, expected |
| `Enum` | each variant + invalid string if at boundary |
| `Pydantic model` | valid, missing required, extra (if forbid), type-violations per field |
| `Annotated[str, Field(min_length=N)]` | exactly N, N-1 (boundary), N+1, much-larger |
| `EmailStr` | valid, malformed, no @, no domain, very long local part, IDN/unicode |
| `Datetime` | UTC, with TZ, without TZ, DST boundary, far-past, far-future, leap-second |
| Return `Optional[T]` | scenarios producing None vs Some(T) |
| Specified `raises X` | conditions triggering X + verify exception attributes |

For `add(a: int, b: int) -> int`:
- int param a: 0, negative, MAX_INT, expected → 4 cases
- int param b: same → 4 cases (but many overlap with a's variations)
- After dedup: ~5-6 unique scenarios

For `register(email: EmailStr, password: Annotated[str, Field(min_length=8, max_length=128)])`:
- email: valid, malformed, no @, no domain, very long, IDN → ~5 cases
- password: 8 chars, 7 chars (boundary), 128 chars, 129 chars (boundary), unicode chars → ~5 cases
- After dedup: ~10 cases

## Step 3: Branch coverage rule

Every distinct branch in the eventual implementation MUST have at least one test. In Phase C (no code yet), apply this prospectively from design.md:

For each conditional behavior:
- IF: test that triggers the IF branch
- ELSE: test that triggers the ELSE branch
- ELIF: test each elif
- TRY/EXCEPT: test that triggers each exception path
- MATCH: test each case + default

If design.md says "if duplicate email, raise DuplicateEmailError; else save", you owe:
- One test for "duplicate → raises"
- One test for "non-duplicate → saves"

This is independent of step 2's type-based tests.

## Step 4: Hypothesis properties (ONLY when invariant exists)

Property-based tests via Hypothesis. Delegate to `property-based-testing-with-hypothesis` skill — cue: _"select Hypothesis property patterns for the invariants in this design"_.

For each public function, identify TRUE invariants from the 6 canonical patterns:

1. **Round-trip**: `decode(encode(x)) == x` for serializers, parsers, codecs
2. **Idempotence**: `f(f(x)) == f(x)` for normalizers, deduplicators, "ensure_X" functions
3. **Commutativity**: `f(a, b) == f(b, a)` for set operations, math
4. **Associativity**: `f(f(a, b), c) == f(a, f(b, c))` for reducers, compositions
5. **Oracle**: `optimized(x) == reference(x)` when a slow correct version exists
6. **Metamorphic**: `f(transform(x)) == related_transform(f(x))` when transformations relate

For `add(a, b)`: commutativity yes, associativity yes, identity with 0 yes → 3 properties.

For `register(email, password)`: no obvious round-trip/idempotence/commutativity. Maybe:
- Property: "registering twice with same email always raises DuplicateEmailError on the second" (idempotence-like, but for error)
- Property: "register-then-authenticate always succeeds with correct credentials" (compositional invariant)
→ 1-2 properties.

For `parse_config(text) -> Config`: round-trip via `serialize(parse_config(text)) == text` (if normalization is deterministic) → 1 property.

**Rule: 0 properties is valid.** If the function has no genuine invariant, don't fabricate one. Forced properties test nothing useful and consume CI time.

## Step 5: Integration tests

One test per external dependency the function touches:

- DB? One integration test using real DB (with rollback fixture or transactional test)
- HTTP client? One integration test using mock server or VCR cassette
- File system? One integration test with `tmp_path` fixture
- External service (Stripe, S3, etc.)? One integration test using the service's testing mode/sandbox

For `register(email, password)`:
- DB: one integration test inserting and retrieving (with fixture rollback)
- Password hashing: zero (hashing is in-process, covered by unit tests of the hash function — usually no need to re-test)

## Step 6: Security tests (if security-relevant)

Auto-detect security relevance per `references/mutation-policy.md` signals (keywords, files touched, imports, QAS references). If detected, delegate to `security-auditor` for test catalog — cue: _"give me the security test catalog for this function"_.

Standard security test categories:
- Input injection (SQL, command, header, log)
- Authentication bypass attempts
- Authorization escalation
- Information disclosure (e.g., timing attacks for auth)
- Rate limiting / DoS resistance (if QAS demands)
- Data integrity / tampering
- Crypto correctness (if crypto used)

For `register(email, password)`:
- Email injection (header CRLF, log injection)
- Password storage (verify not plaintext, not reversible-hashed)
- Timing attack (login time should not vary with email existence; this is in `authenticate` not `register`, but flag for sibling task)
- Brute-force defense (rate-limit; sibling task)
- Common-password rejection (depending on policy)
→ 3-5 tests.

## Step 7: Deduplicate + order

Tests will overlap between categories. Example: the "empty password" test is both a boundary case AND a security case (potential weak credential). Dedupe by behavior, keep the strongest framing.

Order tests in test-plan.md by TDD flow:
1. First test: simplest happy path (drives initial impl)
2. Then: alternative happy paths
3. Then: boundary cases (edge values)
4. Then: error cases (each error class)
5. Then: properties (Hypothesis)
6. Then: integration tests
7. Last: security tests (often touch a different module/layer)

This order minimizes thrash — happy path establishes structure, boundaries refine, errors solidify, properties verify invariants, integration verifies wiring, security verifies hardening.

## Step 8: Test-plan.md format

```markdown
# Test plan for t007: <title>

## Source spec
- Public surfaces from design.md: `register`, `RegisterUserRequest`, `DuplicateEmailError`, ...
- Acceptance criteria from tasks.yaml: ac1, ac2, ac3, ac4, ac5, ac6
- Branch points anticipated: 4 (duplicate check, password validation, repo insert, audit log)
- Security relevance: YES (auth-related, password handling)

## Test list (ordered for TDD)

### Happy path (3 tests)

#### test_register_with_valid_credentials
- Type: unit (with stub repo)
- File: `tests/unit/users/test_service.py`
- Verifies: ac1 (returns 201 with valid body)
- Hypothesis property?: no

#### test_register_returns_unique_user_id
- ...

### Boundary cases (5 tests)

#### test_register_password_at_min_length
- Type: unit
- File: `tests/unit/users/test_service.py`
- Verifies: derived from `Annotated[str, Field(min_length=8)]`
- Edge: exactly 8 chars

#### test_register_password_at_max_length
- Edge: exactly 128 chars

...

### Error cases (4 tests)

#### test_register_duplicate_email_raises
- Type: unit (with stub repo)
- Verifies: ac2
- Triggers: `DuplicateEmailError`

...

### Hypothesis properties (1 property)

#### test_register_then_authenticate_round_trip
- Type: property-based (Hypothesis)
- File: `tests/property/users/test_register_property.py`
- Property: `for any valid (email, password): authenticate(register(email, password), password) returns the same user`

### Integration (2 tests)

#### test_register_persists_to_real_db
- Type: integration
- File: `tests/integration/users/test_register_persistence.py`
- Fixture: real Postgres via testcontainers

...

### Security (4 tests)

#### test_register_password_not_stored_plaintext
- Type: security
- File: `tests/security/users/test_register_security.py`

...

## Summary

| Category | Count |
|----------|-------|
| Happy path | 3 |
| Boundary | 5 |
| Error | 4 |
| Property | 1 |
| Integration | 2 |
| Security | 4 |
| **Total** | **19** |

## Coverage commitments
- All 6 acceptance criteria covered by happy/error tests
- All design.md branch points have a test triggering each branch
- All error types in design.md have a test that raises them
- Boundary tests cover every `Annotated[...]` constraint
```

## Critique step

Walk `checklists/test-completeness.md`. Validate:
- Every acceptance criterion mapped to ≥1 test
- Every error type has a test
- Every branch point has a test triggering each branch
- Every Annotated/Field constraint has a boundary test (=N, N-1, N+1)
- Every public function has at least one happy path test
- Every external dependency has an integration test
- Security relevance auto-detected → security tests present

If any FAIL: SCOPE-LOCAL (add tests to plan).

If acceptance criteria can't be tested executably: SCOPE-UPSTREAM (master-architect Phase 4 issue).

## Output: `tasks/<id>/test-plan.md` finalized

Proceed to Phase D once test-plan.md passes the checklist.

## Anti-patterns in Phase C

- **Fabricated properties**: writing a Hypothesis test that's really an example-based test in disguise. If you can't state the invariant in one sentence, you don't have a property.
- **Over-testing trivials**: don't write 10 tests for `add(a, b)`. Derive logically.
- **Under-testing complex**: don't write 5 tests for an auth flow. Derive logically.
- **Skipping properties**: if a genuine invariant exists, capturing it as a property catches mutation-test cases the example tests miss.
- **All-happy-path**: if your test plan is 80% happy path, you missed the error/boundary/security work.
- **Writing the tests in this phase**: only the PLAN. Code in Phase D. Phase C is plan-only.
