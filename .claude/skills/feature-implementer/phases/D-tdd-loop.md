# Phase D — TDD Loop

**Goal**: execute the test plan from Phase C one test at a time, in declared order, with strict RED → GREEN → REFACTOR discipline. Apply paranoid SRP. Track diff size. Use failure ladder when stuck.

**Inputs**: `tasks/<id>/test-plan.md`.

**Outputs**: actual code in `src/`, actual tests in `tests/`, `tasks/<id>/PROGRESS.md` updates, `tasks/<id>/reflections.md` after each failure.

## The loop (per test from test-plan.md)

For each test T in the planned order:

```
┌─────────────────────────────────────────────────────────┐
│ RED                                                      │
│  1. Write test T in the file path from test-plan        │
│  2. Run: pytest tests/path/test_X.py::T --tb=short      │
│  3. Verify it fails                                     │
│  4. Verify FAILURE REASON is correct (not import error, │
│     not syntax — the actual assertion we wanted)        │
│  5. If wrong-reason failure → fix the test, retry       │
└────────────────────┬────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────┐
│ GREEN                                                    │
│  1. Self-check: pytest output shows failing test         │
│  2. Write the MINIMUM production code to make T pass    │
│  3. Run: pytest tests/path/test_X.py::T                 │
│  4. If passes: run testmon-scoped suite to verify        │
│     no regression in adjacent tests                      │
│  5. If suite still green: GREEN achieved                │
│  6. If suite went red elsewhere: REGRESSION — fix       │
│     (counts as part of GREEN, not new RED)              │
└────────────────────┬────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────┐
│ REFACTOR                                                 │
│  1. Verify ALL tests currently green (`pytest -q`)      │
│  2. Inspect just-written code for SRP violations:       │
│     - Function >20 lines?                                │
│     - Cyclomatic complexity >8?                          │
│     - Mixed I/O + logic?                                 │
│     - Naming unclear?                                    │
│  3. If yes: refactor. Re-run tests. Must stay green.    │
│  4. Delegate to paranoid-srp-python if any flag         │
│  5. Update PROGRESS.md: test T done, lessons (if any)   │
└────────────────────┬────────────────────────────────────┘
                     ▼
                NEXT TEST
```

## RED step in detail

### Writing the test

Location: per `test-plan.md` (which followed Phase 3 layout for test colocation).

Style: arrange-act-assert, one logical assertion per test. Multiple assertions OK if they're verifying one behavior from multiple angles. Don't combine independent behaviors.

Use fixtures from `conftest.py` scoped to the test directory. If a fixture doesn't exist, create it (counts toward this task's diff, but acceptable). Document new fixtures in `conftest.py` adjacent to where they live.

### Verifying RED for the right reason

Common wrong-reason failures (these don't count as valid RED):
- `ImportError`: test references a module/function not yet written. Expected at first test of a new module, but verify the import path is what you intend.
- `SyntaxError`: typo in the test. Fix and retry.
- `NameError`: test references undefined name. Fix.
- `pytest.skip(...)`: skipped tests don't count as RED. Remove the skip.
- `AttributeError` on test file load: the test wasn't actually exercised.

Valid RED failures:
- `AssertionError` with informative message
- The specific exception expected (when testing `pytest.raises`)
- Timeout (only for tests of timing properties)

If wrong-reason fails: this is a Phase D mini-bug, not a Phase C issue. Fix the test, re-run, ensure RED-for-right-reason before proceeding to GREEN.

### Skill self-check before GREEN

Before writing ANY production code, verify with `pytest --tb=no -q`:

- Output includes `failed` count ≥1 → ALLOW production code edit
- Output shows all green → REFUSE production code edit; "must have a failing test first"

This replaces the TDD Guard hook (user opted for self-check). The skill literally runs the command, parses output, decides.

## GREEN step in detail

### Minimum code

"Minimum" means the smallest change that turns this test green WITHOUT breaking any other test. Common over-shoots to avoid:
- Adding parameters the current test doesn't use
- Adding error handling not driven by a failing test
- Adding logging "for production"
- Adding type hints to internals beyond what's needed
- Pre-allocating helpers for future tests

These are all valid additions LATER (in future RED-GREEN cycles or in REFACTOR), but in this GREEN you do the minimum.

### Triangulation

If the minimum code is "return the hardcoded value", that's fine. The next test will force generalization. Triangulation is the TDD pattern of letting multiple tests force the implementation toward the general case.

Example for `add(a, b)`:
- Test 1: `add(2, 3) == 5` → minimum impl: `def add(a, b): return 5`
- Test 2: `add(1, 1) == 2` → forces generalization: `def add(a, b): return a + b`

You don't write `return a + b` first; tests force you there. This catches over-design.

### Testmon scope first, then full

After writing the minimum code:

```bash
pytest --testmon  # only tests impacted by this change
```

Should pass quickly (<5s typically). If passes:

```bash
pytest -q  # full suite (skip if obviously not impacted)
```

Should also pass. If it goes red elsewhere: that's regression. Fix BEFORE moving to REFACTOR. Don't accumulate red tests.

If you can't fix the regression in <10 minutes: this is a structural issue. Consider:
- Did Phase B miss a dependency?
- Did Phase C miss a test that would have caught this earlier?
- Is this a backtrack signal (Phase 3 dep rules violated)?

## REFACTOR step in detail

Enter REFACTOR only when all tests green.

### Paranoid SRP checks

Use thresholds from b34a5532 engineering discipline chat:

- Function body > 20-30 lines → consider extracting
- Cyclomatic complexity > 8 → must refactor (per ruff PLR0915, C901)
- Nesting depth > 3 → refactor
- Function does I/O AND logic → split
- Function takes > 5 parameters → consider object or split

Tools to run (configure in `pyproject.toml` if not already):
- `ruff check --select=C901,PLR0915,PLR0912,PLR0911` (complexity, statement count, branch count, return count)
- `xenon --max-absolute B --max-modules A --max-average A` (cyclomatic complexity grades)
- `complexipy <changed_files>` (cognitive complexity)
- `vulture <changed_files>` (dead code)

Delegate to `paranoid-srp-python` skill — cue: _"audit just-written code against paranoid SRP thresholds"_. Apply its recommendations.

### Refactoring rules

- Tests must stay green throughout. Run after each step.
- Refactor ONLY production code touched in this task. Don't refactor unrelated old code (scope creep).
- Refactor ONLY structure, not behavior. If a refactor changes behavior, you're not refactoring — write the test first.
- One refactor at a time. Extract method, then re-test. Then rename. Re-test. Then move. Re-test.

### When to stop refactoring

REFACTOR until:
- All thresholds satisfied
- Naming clarifies intent (function name says what, not how)
- No duplicated logic (DRY) within this task's scope
- No commented-out code, no TODOs without ticket

Don't over-refactor. Two cycles is usually enough for one test's worth of code.

## Diff size tracking

After each REFACTOR, check running diff:

```bash
git diff --stat HEAD
```

Sum the LOC changes. Track in `PROGRESS.md` after each test:

```markdown
## Diff size
- After test 1: 23 LOC
- After test 2: 41 LOC
- After test 3: 67 LOC
...
- After test 12: 287 LOC
- After test 13: 312 LOC ← over 300 LOC limit; must stop
```

**Hard ceiling 300 LOC** per `laser-change-discipline`. When the running total approaches 280-300:
- Finish current test's REFACTOR
- Stop adding new tests from test-plan.md
- Mark partial completion in PROGRESS.md
- Propose to user: "This task has reached 300-LOC ceiling. Need to split — invoke feature-architect on remaining test-plan items."

Don't blow through 300 with "just one more test". The ceiling is the discipline.

## Failure ladder (when GREEN won't come)

Per `references/failure-ladder.md` and SKILL.md summary. Quick recap:

```
TIER 1: Simple fix × 3
  - Read traceback
  - Fix obvious cause (typo, missing import, wrong return)
  - Re-run

TIER 2: Self-Refine × 2
  - Capture current failing state
  - Regenerate impl with "you missed X" critique injected
  - Re-run

TIER 3: CRITIC × 1+
  - Add print/log statements to capture state at failure point
  - Run code, capture trace
  - Debug from concrete data, not assumptions
  - Delegate: execution-feedback-debugging
  - Re-run

TIER 4: KB algorithms × 3
  - Consult master-architect/algorithms.md
  - Try Reflexion (write what you missed last time, use it next time)
  - Try alternative pattern (different approach to same problem)
  - Re-run

EXTEND if making progress per formal definition.

ESCALATE to user when ladder exhausted and 3 consecutive zero-progress attempts.
```

### Reflexion notes (mandatory)

After EACH failed attempt at any tier, append to `tasks/<id>/reflections.md`:

```markdown
## Attempt N (tier X)
- Tried: <one sentence>
- Result: <failure mode>
- Hypothesis: <what I think went wrong>
- Next try: <different approach>
```

Read accumulated reflections at the start of the NEXT attempt to avoid repeating yourself.

### Progress check (formal)

Before deciding "extend" or "escalate", apply formal definition:

PROGRESS if any of:
- Failing test count decreased (was 3, now 2)
- Failure mode changed (was `KeyError: 'x'` at line 42, now `AssertionError: expected 5 got 3` at line 50)
- Coverage delta increased (caught a new branch)
- Failure area narrowed (assertion moved from outer scope to inner)

ZERO PROGRESS if:
- Same exception, same line, same message after attempt
- "Different approach" without measurable change in failure

3 consecutive ZERO PROGRESS attempts at any tier → AUTO-escalate to next tier (don't extend on this tier).

## When to step outside the loop

Some situations warrant pausing the TDD loop:

- **Backtrack signal**: design.md says "use repository X" but X doesn't exist and creating it would require modifying Phase 3 layout. → BACKTRACK to master-architect per SKILL.md.
- **300 LOC ceiling**: stop, propose split.
- **User interrupts**: stop, record state in PROGRESS.md, await direction.
- **Major design flaw discovered**: stop, write what's wrong, ask user. Don't try to "fix it in flight".

## PROGRESS.md updates

After each completed test (RED → GREEN → REFACTOR cycle), append to `tasks/<id>/PROGRESS.md`:

```markdown
## Test 3: test_register_password_at_min_length
- Started: 2026-05-12T15:30:00Z
- RED at: 2026-05-12T15:32:00Z (correct reason: AssertionError "expected ValidationError")
- GREEN at: 2026-05-12T15:35:00Z (added Pydantic Annotated Field(min_length=8))
- REFACTOR: none needed (function still <10 lines)
- Diff total: 87 LOC
- Lessons: Pydantic Annotated[str, Field(min_length=N)] raises ValidationError not ValueError; updated error type in design.md
- Next: test 4 (password at max length)
```

This becomes valuable input to Phase F session-dreaming.

## Anti-patterns in Phase D

- **Writing test + impl together**: the cardinal TDD sin. Always RED first, separate commit-worthy state.
- **Skipping the self-check**: "I know there's a failing test" doesn't count. Run pytest, see it, then edit.
- **Allowing red tests to accumulate**: never have >1 red test deliberately. Each RED is for ONE test you're about to GREEN.
- **"I'll refactor later"**: REFACTOR is part of THIS cycle. Doing it later compounds technical debt.
- **Skipping reflection notes**: those notes are the difference between learning and repeating.
- **Skipping diff tracking**: 300 LOC ceiling exists because past 300, review quality collapses. Track diligently.
- **Continuing past 3 zero-progress attempts**: ladder is the discipline. Don't bargain with it.
