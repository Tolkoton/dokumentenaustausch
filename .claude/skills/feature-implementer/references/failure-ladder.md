# Failure Ladder

Escalation strategy when a test refuses to go GREEN. Used during Phase D.

Goal: structured, ratcheting escalation that gives every approach a fair shot before giving up. Avoids both "give up too early" and "infinite loop".

## The ladder

```
TIER 1: Simple fix (≤3 attempts)
TIER 2: Self-Refine (≤2 attempts)
TIER 3: CRITIC with execution traces (≥1 attempt, can extend)
TIER 4: KB algorithms (≤3 attempts)
EXTEND: continue current tier if making progress
ESCALATE: ask user when ladder exhausted + 3 zero-progress
```

## Progress definition (formal, repeated for emphasis)

**Progress** if any of:
1. Failing test count decreased (was 3 failing, now 2)
2. Failure mode changed substantively (different exception, different line, different error message — not "different log output")
3. Coverage delta increased (caught a new branch even if test still fails)
4. Failure area narrowed (assertion moved from outer scope to inner; or from "load fails" to "first assertion fails")

**Zero progress** if:
- Same exception, same line, same message after attempt
- "Different approach" without measurable change in failure
- Random fluctuation (test flaky) without root-causing the flakiness

Three consecutive zero-progress attempts at any tier → AUTOMATIC tier escalation. Do not extend on zero-progress.

## TIER 1: Simple fix

When to use: first attempt after RED. The test failed; you see the traceback; the fix looks obvious.

How:
1. Read full traceback (not just message — see file, line, function)
2. Form a minimal hypothesis: "the bug is X"
3. Fix X
4. Re-run

Examples of TIER 1 fixes:
- Typo in code (`reigster` → `register`)
- Missing import
- Wrong return value type (returning `dict` when test expects `User`)
- Off-by-one in slice/index
- Wrong assertion operator (`==` vs `is`)

Budget: 3 attempts. If after 3 the test is still red AND no progress → TIER 2.

## TIER 2: Self-Refine

When to use: simple fix exhausted but failure mode hasn't moved. The bug is in your thinking, not in a typo.

How:
1. Read your current implementation
2. Read the failing test (carefully — what is it actually asserting?)
3. Read design.md (does the impl match the design?)
4. Write a critique of what's wrong: "This impl assumes X but the test expects Y"
5. Regenerate the implementation function (or class method) from scratch, with the critique as context
6. Re-run

This is NOT "tweak a few lines". This is REPLACE the function body with a fresh attempt informed by what you learned.

Examples of TIER 2 fixes:
- Wrong algorithm choice (using a hashmap when ordered iteration needed)
- Missing edge case in conditional logic (forgot the None case)
- Mismatched abstraction (passing repository instead of session, or vice versa)
- State leak (using class attribute as instance attribute)

Budget: 2 attempts. If after 2 the failure mode hasn't moved → TIER 3.

## TIER 3: CRITIC with execution traces

When to use: Self-Refine didn't help. The bug is non-obvious from reading code; you need to SEE what the code is actually doing.

How:
1. Add temporary instrumentation in the failing path:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ...
   def register(email, password):
       logging.debug(f"register called: email={email!r}, password=<redacted>")
       ...
       logging.debug(f"before hash: {password!r}")
       hashed = hasher.hash(password)
       logging.debug(f"after hash: type={type(hashed)}, len={len(hashed)}")
       ...
   ```
2. Run failing test with `-s` flag: `pytest tests/.../test_X.py::test_T -s --tb=long`
3. Read the actual trace — values, types, control flow
4. Identify the discrepancy: "I thought X but actually Y"
5. Fix based on observed reality
6. Remove instrumentation
7. Re-run

This is debugging FROM EVIDENCE, not from assumption.

Delegate to `execution-feedback-debugging` skill — cue: _"apply CRITIC discipline with execution traces to find the root cause"_.

Examples of TIER 3 fixes:
- Type confusion at runtime (you thought it was `str`, it was `bytes`)
- Mock setup vs actual call mismatch (you mocked `repo.find_by_email` but code calls `repo.get_by_email`)
- Async/sync mismatch (forgot to await)
- Timezone issue (UTC vs naive datetime comparison)
- Pydantic validation order surprises
- Library version-specific behavior

Budget: 1+ attempts, can extend if making progress. If 3 consecutive zero-progress in TIER 3 → TIER 4.

## TIER 4: KB algorithms

When to use: TIER 3 found the symptom but not the cure, or the bug needs a fundamentally different approach.

How:
1. Read `~/.claude/skills/master-architect/algorithms.md` (the self-learning KB)
2. Select one of:
   - **Reflexion**: read `tasks/<id>/reflections.md` for all prior attempts. Synthesize: "I keep doing X; let me try not-X." Append the meta-reflection.
   - **Plan-and-Solve**: write an explicit plan. "To make this test pass, I need to: 1) X, 2) Y, 3) Z." Execute step by step, verifying each.
   - **ToT-mini**: brainstorm 3 different approaches. Pick best. If best doesn't work, try second.
   - **Self-Consistency**: write the function 3 different ways. Compare outputs. The agreement (or disagreement) is information.
   - **Constitutional**: list the rules the impl must satisfy (per design.md + Iron Laws). Check each rule against current impl. Find the violation.
3. Apply the chosen approach
4. Re-run

Examples of TIER 4 fixes:
- The function design itself is wrong (back to design.md mentally; consider Phase B revision)
- Two interacting bugs (Self-Refine fixed one, broke another)
- The test assumes behavior that contradicts another test elsewhere
- A library's documented behavior is wrong (rare but happens)

Budget: 3 attempts. If 3 zero-progress → ESCALATE.

## EXTEND

You can stay on the current tier as long as you're making progress (per formal definition).

After each attempt at any tier:
1. Compute progress vs previous attempt
2. If progress: STAY on this tier (max 3 more attempts within the tier even with progress)
3. If zero progress: track in `tasks/<id>/reflections.md`
4. 3 consecutive zero-progress → AUTO-escalate to next tier

There's no infinite extension. Each tier has a hard ceiling (3+2+1+3 = 9 nominal max, plus extension allowance brings it to ~15 attempts before total ESCALATE).

## ESCALATE

When ladder exhausted with no clear progress, hand to user:

```markdown
## Escalation: t007, test test_register_password_at_min_length

I've been unable to make this test pass after 12 attempts across 4 tiers.

### What the test wants
<copy test code>

### What's happening
<copy failure output>

### Attempts summary

**Tier 1 (3 attempts)**: tried fixing typos, return types. All zero progress on failure mode (`AssertionError: expected ValidationError but got TypeError`).

**Tier 2 (2 attempts)**: regenerated `register()` twice. First version tried Pydantic Field validation. Second tried manual validation. Same error after both.

**Tier 3 (3 attempts)**: added instrumentation. Discovered that `Annotated[str, Field(min_length=8)]` at function parameter doesn't trigger Pydantic validation (it's only validated when wrapped in BaseModel). Tried wrapping in BaseModel. Created new error (`AttributeError`).

**Tier 4 (4 attempts)**: Tried via Plan-and-Solve (write a BaseModel for params, validate, then unwrap), then Self-Consistency (compared 3 implementations). All fail with subtly different errors.

### Hypothesis
The test as written assumes `register(email, password)` triggers Pydantic validation. This only works if password is wrapped in a Pydantic model.

### Suggested resolutions
1. Change `register()` signature to take a `RegisterUserRequest` (BaseModel) instead of separate params — would invalidate ac1
2. Change the test to construct a `RegisterUserRequest` and call `register(req)` — would invalidate the test setup
3. Validate manually in the function body and raise `ValidationError` — would not match Pydantic's exception type
4. This is a Phase B design flaw — invoke master-architect from Phase 2

Which resolution would you like?
```

Then STOP. Wait for user. Don't pick a resolution unilaterally.

## Reflexion notes (mandatory at every tier)

After every attempt, append to `tasks/<id>/reflections.md`:

```markdown
## Attempt 7 (Tier 3, attempt 2)
- Tried: added logging to capture password type before hashing
- Result: discovered password reaches hasher as `str`, not `bytes` as I assumed
- Hypothesis: my impl was already correct on type; the test failure is at validation step before hashing
- Next try (Tier 3 attempt 3): trace validation step explicitly
- Progress: failure area narrowed from "function body" to "input validation"
```

These notes get read at:
- The next attempt (avoid repeating same approach)
- Phase F session-dreaming (lessons for future tasks)
- ESCALATE message (gives user clear picture)

## Anti-patterns

- **Skipping tiers**: TIER 4 before TIER 1 (jumping to KB algorithms on a typo) wastes tokens and Claude reasoning. Start simple.
- **Staying on TIER 1 forever**: "let me try one more typo fix" without progress is the most common failure. Auto-escalate on 3 zero-progress.
- **Skipping reflection notes**: each failure not noted is a future repeat.
- **Vague reflections**: "tried again, didn't work" teaches nothing. Be concrete: what, result, hypothesis, next.
- **Hidden zero-progress**: "the error message looks different" if the line and exception type are same is NOT progress. Be honest.
- **Premature escalation**: at Tier 1 attempt 2 you don't escalate to user. Walk the ladder.
- **Auto-resolving at escalate**: when reaching ESCALATE, OFFER resolutions; don't pick one. User decides.
