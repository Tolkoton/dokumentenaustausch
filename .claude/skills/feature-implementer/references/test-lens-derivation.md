# Test Lens Derivation

Algorithm for deriving test count logically from spec. Replaces "fixed N tests per function" with deterministic derivation.

Used during Phase C. Consult this file BEFORE writing test-plan.md.

## Core principle

Test count is NOT prescribed. It is **derived** from:
1. Type signature (what parameters and returns)
2. Specified errors (what can raise)
3. Branch structure (what conditional behavior)
4. Acceptance criteria (what behavior must work)
5. Security relevance (auto-detected)

Two functions with similar names can have very different test counts because their **specs** differ.

## The derivation algorithm

Apply in order. Each step adds tests. Then deduplicate.

### Step 1: Map acceptance criteria

For each acceptance criterion (`ac1`, `ac2`, ...) in tasks.yaml:
- → 1 test that directly verifies the criterion

Minimum: 1 test per criterion. The test name should reference the criterion ID in its docstring.

### Step 2: Mechanical type-driven tests

For each parameter in the function signature, walk this table:

| Type | Tests to add |
|------|--------------|
| `bool` | True, False (2 tests) |
| `int` | 0, negative_value, MAX_INT_or_realistic_max, expected_typical (3-4 tests; dedupe with happy path) |
| `int` with `Field(ge=N)` | N (boundary), N-1 (just-violating), much larger (1-2 tests for boundary) |
| `int` with `Field(le=N)` | N (boundary), N+1, much smaller (1-2 tests) |
| `int` with `Field(ge=N, le=M)` | N, M, N-1, M+1 (4 tests for boundary) |
| `float`/`Decimal` | 0, negative, very small, very large, precision-loss, NaN/Inf (3-5 tests) |
| `str` | empty, single-char, very-long (>10K), unicode-edge (emoji, RTL, NUL byte), whitespace-only, expected (3-5 tests) |
| `str` with `Field(min_length=N)` | exactly N (boundary), N-1 (just-short), single char if min=1 (1-3 tests) |
| `str` with `Field(max_length=N)` | exactly N (boundary), N+1, much longer (1-3 tests) |
| `str` with `Field(pattern=...)` | matches, doesn't match, edge case of regex (anchors, etc.) (2-3 tests) |
| `EmailStr` | valid, missing-@, missing-domain, IDN/unicode, very-long-local-part (3-5 tests) |
| `Optional[T]` | None case + every T case from above (T count + 1) |
| `list[T]` | empty, single-element, multiple, duplicates if order/uniqueness matters (2-4 tests) |
| `dict[K, V]` | empty, single-pair, K-collision attempts (if dict from external), V variants (2-4 tests) |
| `Decimal/Money` | 0, negative, very_large, precision_overflow, expected (3-5 tests) |
| `Enum` | each variant + one invalid string if Enum crosses boundary (variant_count + 1) |
| `Pydantic BaseModel` | valid_full, missing_required_field, extra_field (if extra=forbid), each type_violation_per_field (4+ tests) |
| `datetime` | UTC-aware, naive, with non-UTC TZ, DST boundary, year-2038, year-9999 (3-5 tests) |
| Custom NewType (e.g., `UserId = NewType("UserId", str)`) | same as underlying str, plus 1 test verifying typed at boundary |

For each return type element, repeat (return cases):
| Type | Tests to add |
| `Optional[T]` return | scenarios producing None vs Some(T) (2 tests) |
| `Union[A, B]` return | scenarios producing A vs B (>=2 tests) |
| `list[T]` return | empty list, single-element, multi-element returns (2-3 tests) |

**Caveat**: tests that already exist from Step 1 (acceptance criteria) often cover some type cases. Deduplicate in Step 7.

### Step 3: Errors and exceptions

For each error type listed in design.md `Errors raised` section:
- 1 test that triggers the error
- 1 test that verifies error's carried data (attributes, message)
- → 1-2 tests per error type

For each "happy path → wrong path" branching in description (e.g., "if duplicate: raise; else: save"):
- 1 test for happy
- 1 test for each error branch

### Step 4: Branch coverage (prospective)

Inspect design.md for conditional behavior. For each branch point:
- IF/ELSE: 2 tests (one per branch)
- ELIF: 1 test per elif clause + 1 for default
- TRY/EXCEPT: 1 test triggering each except clause + 1 for success path
- MATCH: 1 test per case + 1 for default if exhaustive

If design.md doesn't show branches yet, defer this step to Phase D — after each GREEN, check if there are uncovered branches and add tests.

### Step 5: Hypothesis properties

Identify TRUE invariants from these patterns:

| Pattern | Question to ask | Add property if YES |
|---------|----------------|---------------------|
| Round-trip | Is there an inverse operation? | `f_inv(f(x)) == x` |
| Idempotence | Is repeat application redundant? | `f(f(x)) == f(x)` |
| Commutativity | Does argument order not matter? | `f(a, b) == f(b, a)` |
| Associativity | Does grouping not matter? | `f(f(a, b), c) == f(a, f(b, c))` |
| Identity | Is there a neutral element? | `f(x, identity) == x` |
| Oracle | Is there a slow correct version to compare with? | `optimized(x) == reference(x)` |
| Metamorphic | Does transforming input relate to transforming output? | `f(T(x)) == T'(f(x))` |
| Monotonicity | Does ordered input → ordered output? | `x < y → f(x) <= f(y)` |
| Total | Does function terminate without exception for all valid input? | Use `@given` with type strategies |

For each YES → 1 Hypothesis property test.

**0 properties is valid**: if none of the patterns apply, don't fabricate. Don't write a Hypothesis test that's secretly an example test.

### Step 6: Integration tests

For each external dependency the function touches:
- 1 integration test using REAL or test-double of that dependency

Categories:
- Database → real DB (test-containers, transactional rollback)
- HTTP client → mock server (responses library, httpx_mock)
- File system → tmp_path fixture
- External service → service's testing mode (Stripe test keys, etc.)
- Time-dependent → freezegun or injected time function
- Random → seeded random or injected RNG

**Skip integration tests for**:
- Pure functions (no external deps)
- Functions wrapping libraries that are themselves well-tested

### Step 7: Security tests (if security-relevant)

Auto-detect via mutation-policy signals. If YES, add tests from this catalog:

| Domain | Tests |
|--------|-------|
| Input parsing | SQL injection attempts, command injection, log injection (CRLF in user input), header injection, XML/JSON deeply-nested, oversized input (DoS), encoding tricks |
| Authentication | brute-force resistance, account enumeration via timing, account enumeration via error messages, password reset token reuse, session fixation |
| Authorization | privilege escalation, IDOR (insecure direct object reference), RBAC bypass, ACL bypass |
| Sensitive data | not logged in plaintext, not stored in plaintext, not in response when not authorized, not in error message |
| Crypto | correct algorithm (not MD5 for security), correct mode (no ECB), proper IV/salt, key rotation possible |
| Rate limiting | normal load, just-below-limit, just-above-limit, distributed attempt |

Pick relevant tests for the specific function. Delegate to `security-auditor` for catalog if uncertain.

→ 3-5 security tests per security-relevant function.

### Step 8: Deduplication and ordering

Walk all derived tests, remove duplicates:
- Two tests both testing "empty email" → keep one (under the most appropriate category, usually boundary)
- A property that covers many examples → drops the equivalent example tests

Order tests in test-plan.md:
1. Happy path tests (simplest first — drives initial impl)
2. Boundary cases (refines impl)
3. Error cases (solidifies impl)
4. Properties (verifies invariants)
5. Integration tests (verifies wiring)
6. Security tests (verifies hardening)

## Worked examples

### Example 1: `add(a: int, b: int) -> int`

Design.md says:
```
def add(a: int, b: int) -> int:
    """Sum of a and b."""
```
No errors, no branches, no acceptance criteria beyond "computes sum".

Derivation:
- Step 1: Acceptance criteria mapping → 1 test ("test_add_returns_sum")
- Step 2: int params → tests for 0, negative, large; combine with above
  - Tests: add(0, 0), add(5, 3), add(-1, 1), add(MAX_INT, 0)
  - ~3-4 unique tests after dedup
- Step 3: No errors → 0
- Step 4: No branches → 0
- Step 5: Properties → commutativity, associativity, identity-zero → 3 properties
- Step 6: Pure function, no deps → 0
- Step 7: Not security-relevant → 0

**Total: 6-7 tests** (4 example + 3 properties)

### Example 2: `register(email: EmailStr, password: Annotated[str, Field(min_length=8, max_length=128)]) -> UserId`

Design.md specifies: raises DuplicateEmailError, WeakPasswordError. Touches DB. Security-relevant (auth).

Derivation:
- Step 1: ac1 (success), ac2 (duplicate raises), ac3 (e2e 201), ac4 (curl 201), ac5 (mypy), ac6 (lint)
  → 4 functional tests (ac5/ac6 not test-based)
- Step 2:
  - EmailStr: valid, missing-@, missing-domain, IDN, very-long → 4 tests
  - password length 8 (boundary), 7 (just-short), 128 (boundary), 129 (just-long) → 4 tests
  → 8 type-driven tests
- Step 3: DuplicateEmailError test, WeakPasswordError test (if password matches common list) → 2 tests
- Step 4: branches in design.md: duplicate check, weak password check, persistence success → already covered by Step 1 + 3
- Step 5: Properties:
  - register-then-authenticate is roundtrip-like → 1 property
  - registering twice with same email always raises → idempotence-like, already in Step 3
  → 1 property
- Step 6: DB integration test → 1 test
- Step 7: Security:
  - password not stored plaintext → 1 test
  - email injection (CRLF) → 1 test
  - timing-attack resistance → 1 test (or deferred to authenticate task)
  - brute-force defense → 1 test
  → 3-4 security tests

After dedup (e.g., "valid email + valid password" covered once, not separately): **~18-22 tests**

This matches what I estimated in chat. The number is *derived*, not chosen.

### Example 3: `parse_iso8601(s: str) -> datetime`

Design.md: parses ISO-8601 strings to UTC datetime. Raises `InvalidISO8601Error`.

Derivation:
- Step 1: ac1 (parses valid) → 1
- Step 2: str with various edge cases → empty, malformed, very-long, whitespace, unicode → ~4 tests
- Step 3: InvalidISO8601Error → 1 test
- Step 4: branches: success, failure → covered
- Step 5: ROUND-TRIP! `format_iso8601(parse_iso8601(s)) == normalize(s)` → 1 property. Also test "all valid ISO-8601 strings parse without error" via Hypothesis text strategy → 1 more
- Step 6: No external deps → 0
- Step 7: Not security-critical → 0

**Total: ~7-8 tests** (5 example + 2 properties)

### Example 4: `normalize_email(email: str) -> str`

Design.md: lowercases, strips whitespace, removes plus-suffix in Gmail.

Derivation:
- Step 1: ac1 (typical normalization) → 1
- Step 2: empty, only-whitespace, unicode, very-long → 3 tests
- Step 3: No errors specified → 0
- Step 4: Branches: gmail-vs-other → 2 tests
- Step 5: IDEMPOTENCE! `normalize(normalize(x)) == normalize(x)` → 1 property
- Step 6: No external deps → 0
- Step 7: Not security-critical → 0

**Total: ~6-7 tests** (5 example + 1 property)

## Reliability heuristic

The number of tests should roughly equal:

```
1 per acceptance criterion
+ ~2 per non-trivial parameter type
+ 1 per Annotated constraint boundary
+ 2 per error type
+ 1 per branch point
+ N per applicable invariant pattern (often 0-3)
+ 1 per external dependency
+ 3-5 if security-relevant
- duplicates
```

For a trivial function: 5-10 tests.
For a typical CRUD endpoint: 15-25 tests.
For a complex auth or financial function: 25-40 tests.

If your derivation gives <5 tests for any non-trivial function, you missed something. If >50, you're over-testing (or the function should be split — Phase B issue).

## When to break the rules

- **Prototype phase**: skip property/security tests, do core 5-10. Mark task `prototype: true`. Tighten later when promoted.
- **Critical fixes**: ADD more tests beyond derivation. Especially mutation testing should be near 100% on critical paths.
- **Pure refactor (behavior-preserving)**: existing tests suffice; only add if discovered uncovered branch.

## Anti-patterns

- **"Around 10 tests should be enough"**: arbitrary, ignores spec. Use the algorithm.
- **Skipping Step 2 for "simple" types**: `int` parameters can hide overflow, underflow, off-by-one. Always derive.
- **Forcing properties when none exist**: `def test_register_property(): assert register(email, password) is not None` is not a property test. It's an example test cosplaying.
- **Stopping at "happy path covered"**: error cases and boundaries are where bugs live.
