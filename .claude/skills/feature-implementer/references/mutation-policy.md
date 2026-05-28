# Mutation Testing Policy

When and how to run mutmut during Phase E. Auto-detects "critical" tasks for strict mode.

## Why mutation testing

Tests can pass but be useless. Example: `assert result is not None` passes for any non-None return. Mutation testing changes the code (replaces operators, inverts conditions, etc.) and re-runs tests. Surviving mutants = tests that don't catch obvious bugs.

For financial / security / data-integrity code, mutation testing is the difference between "tests exist" and "tests verify".

## Two modes

### Critical mode (no timeout, threshold ≥80%)

For tasks handling:
- Authentication, authorization, sessions
- Financial calculations, money, currency, taxes
- Cryptography, hashing, signatures
- PII, GDPR/HIPAA, sensitive data
- Audit logs, compliance
- Data integrity (write paths, transactions)

Mutation score target: ≥80% on changed modules. Any surviving mutant must be reviewed and EITHER killed (write a missing test) OR explicitly accepted with one-line justification in `tasks/<id>/mutation-survivors.md`.

Acceptable acceptance reasons:
- "Equivalent mutant" (the change makes no semantic difference)
- "Defensive code path; not invoked under any realistic test scenario"
- "Test would require fault injection in third-party library; deferred to integration env"

NOT acceptable:
- "Hard to test"
- "Low risk"
- "Will fix later"

### Standard mode (2-min timeout, no hard threshold)

For tasks not matching critical signals:
- Internal utilities
- UI/UX adjustments
- Logging changes
- Refactoring (no behavior change)
- Documentation
- CI/build scripts

Run mutmut with 2-minute wall clock timeout. Capture whatever completes. Record mutation score as informational. Score <50% is a flag (suggests Phase D: write better tests) but not a hard fail.

## Critical mode auto-detection

ANY of these signals → critical mode:

### Signal 1: Task title or description keywords

Keywords (case-insensitive substring match):
- `auth` (authentication, authenticate, authorize, authorization, authn, authz)
- `password`, `credential`, `secret`, `token`, `session`, `cookie`
- `payment`, `charge`, `refund`, `invoice`, `transaction`, `billing`
- `money`, `currency`, `decimal`, `amount`, `price`, `cost`
- `tax`, `vat`, `gst`, `accounting`, `ledger`, `journal`
- `audit`, `log` (when context is audit log not debug log), `compliance`
- `pii`, `gdpr`, `hipaa`, `ccpa`, `personal`, `sensitive`
- `crypto`, `cipher`, `encrypt`, `decrypt`, `hash`, `signature`, `sign`, `verify`
- `permission`, `role`, `acl`, `rbac`, `policy`
- `migration` (when schema), `schema change`

### Signal 2: Files touched match path patterns

```
*/auth/*
*/security/*
*/billing/*
*/payments/*
*/accounts/*
*/audit/*
*/compliance/*
*/crypto/*
*/migrations/*
*/datev/*    # DATEV-specific
```

### Signal 3: Imports detected in changed files

```python
import Decimal
from decimal import Decimal
from money import Money  # or any Money library
import cryptography
import hashlib
import secrets
import jwt
import argon2
import bcrypt
import passlib
import nacl
```

### Signal 4: Phase 1 QAS reference

If `tasks/<id>/design.md` references a QAS in category:
- security
- integrity
- audit
- financial
- compliance
- recoverability (data preservation)

### Signal 5: Explicit task tag

In tasks.yaml:
```yaml
- id: t007
  criticality: critical
```

### Signal 6: Architectural ownership

If the task touches a container marked `critical: true` in `components.yaml` (Phase 2).

## Detection algorithm

```python
def is_critical(task) -> bool:
    # Signal 1: keywords
    text = (task.title + " " + task.description).lower()
    KEYWORDS = ["auth", "password", "payment", "money", "decimal", ...]
    if any(kw in text for kw in KEYWORDS):
        return True

    # Signal 2: paths
    PATH_PATTERNS = ["*/auth/*", "*/security/*", ...]
    for f in task.files_to_modify + task.files_to_create:
        if any(fnmatch(f, p) for p in PATH_PATTERNS):
            return True

    # Signal 3: imports (after Phase D — checks current code)
    SENSITIVE_IMPORTS = ["Decimal", "Money", "cryptography", "hashlib", "secrets", "jwt", "argon2"]
    for f in changed_files():
        for imp in parse_imports(f):
            if any(s in imp for s in SENSITIVE_IMPORTS):
                return True

    # Signal 4: QAS reference
    for qas in design_md.qases_referenced:
        if qas.category in ["security", "integrity", "audit", "financial", "compliance"]:
            return True

    # Signal 5: explicit tag
    if task.get("criticality") == "critical":
        return True

    # Signal 6: container marker
    container = task.container  # from design.md
    if components_yaml[container].get("critical"):
        return True

    return False
```

ANY signal → critical mode. Multiple signals don't intensify; one is enough.

## Configuration in pyproject.toml

```toml
[tool.mutmut]
paths_to_mutate = "src/"
backup = false
runner = "pytest -x -q"
tests_dir = "tests/"

[tool.mutmut.critical]
threshold = 80
timeout = 0  # no timeout

[tool.mutmut.standard]
threshold = 50
timeout = 120  # 2-minute wall clock
```

## Running

```bash
# Detect mode (skill does this internally)
mode = "critical" if is_critical(task) else "standard"

# Critical mode
mutmut run --paths-to-mutate="src/users/" -- pytest -x -q

# Standard mode
timeout 120 mutmut run --paths-to-mutate="src/users/" -- pytest -x -q

# Inspect results
mutmut results
mutmut show <mutant-id>  # see specific surviving mutant
```

Mutation report saved to `tasks/<id>/mutation-report.md`:

```markdown
# Mutation report — t007 — critical mode

Total mutants: 47
Killed: 44 (94%)
Survived: 3
Timeout: 0
Suspicious: 0
Mutation score: 94% (PASS, threshold 80%)

## Survivors

### Mutant #12: `src/users/service.py:34` — `>` → `>=`
Status: KILLED in attempt 2 (added boundary test `test_password_at_exactly_8_chars`)

### Mutant #19: `src/users/service.py:45` — `and` → `or`
Status: ACCEPTED — "Equivalent mutant in defensive null-check; both conditions empirically unreachable given Pydantic pre-validation"

### Mutant #41: `src/users/repository.py:22` — `1` → `2`
Status: KILLED in attempt 1 (added test for limit=1 specifically)
```

## When mutation testing is overkill (even in critical)

For tasks that are PURELY:
- New configuration files (no logic)
- Pure renames or moves (no behavior change)
- Adding dependencies / managing package files
- Documentation only

Skip mutation testing. Note in handoff.md: "Mutation testing skipped — no logic changes."

## When mutation testing reveals architectural debt

If you have lots of "equivalent mutants" piling up in `mutation-survivors.md`, that's a signal:
- Your code is doing defensive things that aren't reachable
- OR your tests are missing coverage of legitimate paths

In either case: Phase D should investigate. Often points back to design.md issues.

## Cost considerations

Mutation testing on large codebases is slow. Strategies to keep it tractable:
- Only mutate CHANGED modules (not whole `src/`)
- Use `--use-coverage` to skip mutants in uncovered lines (covered code is what gets mutated)
- Parallelize with `mutmut run -p 4`
- Cache results between runs (mutmut does this by default)

For a typical task touching 1-2 modules of 100-200 lines each, critical mode usually completes in 2-15 minutes. Standard mode (2-min timeout) typically gets 50-80% coverage.

## Anti-patterns

- **Skipping mutation testing in critical mode "just this once"**: never. Always.
- **Accepting survivors without justification**: every survivor in critical needs a one-line reason.
- **Mutating untouched code**: scope to changed paths only.
- **No mutation report**: leaves user with no way to verify what was tested.
- **Auto-accepting equivalent mutants**: skill should flag them; user/Claude reviews and accepts manually.
- **Pretending standard mode is critical**: if signals say critical, IT IS critical. No overrides without explicit user instruction.
