# Sub-Task Template

Format for sub-task entries in `.architecture/tasks.yaml`. Adheres to master-architect's tasks.yaml schema with three additional fields: `parent`, `order`, and an optional `split_rationale`.

## Template

```yaml
- id: <parent-id><suffix>          # e.g., t007a, t007b
  parent: <parent-id>              # e.g., t007 (mandatory for sub-tasks)
  order: <integer>                 # order within siblings, 1-indexed (1, 2, 3, ...)
  title: "<descriptive title>"     # one line, action-oriented
  description: |
    <2-5 sentence description of what this sub-task does, what it inherits
    from parent, what it defers to siblings>
  complexity: <S | M>              # sub-tasks should be S or M
  status: TODO                     # always TODO at creation
  files_to_modify:
    - <path>
    - <path>
  files_to_create:
    - <path>
    - <path>
  depends_on:
    - <task-id>                    # parent's deps + new deps on siblings
  acceptance_criteria:
    - "<executable verification>"
    - "<executable verification>"
  qas_refs:
    - <QAS-id>                     # if any from parent apply
  adr_refs:
    - <ADR-id>                     # if any from parent apply
  technologies: []                 # optional explicit tech tags
  criticality: <normal | critical> # optional; inherited if parent had it
```

## Parent task modifications

When splitting, the parent task entry is updated:

```yaml
- id: t007
  status: SPLIT_INTO               # changed from TODO
  split_into:                       # new field listing sub-tasks
    - t007a
    - t007b
    - t007c
  split_at: "<ISO timestamp>"      # when the split happened
  split_rationale: |               # optional, why it was split
    Original task touched 7 files with 13 acceptance criteria across
    3 distinct capabilities (registration, login, password-reset).
    Decomposed into 3 capability-aligned sub-tasks per feature-architect's
    capability-split pattern.
  # All other parent fields preserved for reference:
  title: "..."
  description: "..."
  files_to_modify: [...]
  files_to_create: [...]
  acceptance_criteria: [...]
  depends_on: [...]
  ...
```

## Field-by-field guidance

### `id` format

Use parent ID + lowercase suffix letter: `t007` → `t007a`, `t007b`, `t007c`.

If parent has >5 sub-tasks (which means decomposition might be wrong, see anti-patterns in decomposition-heuristics.md), continue with `t007f`, `t007g`, etc.

If a sub-task itself is split (recursion): `t007a` → `t007a1`, `t007a2`, ... Avoid going beyond 2 levels.

### `parent` (mandatory for sub-tasks)

Always points to the immediate parent. For `t007a1`, parent is `t007a` (not `t007`).

This is what distinguishes a sub-task from a regular task — regular tasks don't have `parent`.

### `order`

Position within siblings. Used for display and to indicate intended sequence (does NOT replace `depends_on`).

If two sub-tasks can run in parallel, they have different `order` values but no `depends_on` between them. The order field is for human reading.

### `title`

Should include both what's being built AND scope context. Examples:

GOOD:
- "Register endpoint: minimal happy path"
- "Register endpoint: duplicate-email rejection"
- "Article CRUD: create operation"

BAD:
- "Sub-task 1" (no context)
- "Step 2" (not action-oriented)
- "Register" (insufficient — what about register?)

### `description`

2-5 sentences. Should explain:
1. What this sub-task does (its slice)
2. What it inherits from parent (assumptions about prior sub-tasks)
3. What it defers (handled by sibling sub-tasks)

Example:

```yaml
description: |
  Implements POST /register with the minimal happy path: accepts valid
  email and password ≥8 chars, persists user with hashed password, returns
  201 with new user_id.

  Defers to t007b: duplicate-email rejection.
  Defers to t007c: password policy enforcement (common-password list,
  breach check).
  Defers to t007d: brute-force defense and captcha (security hardening).
```

### `complexity`

Always `S` or `M`. If your sub-task is `L`, recurse: feature-architect should split it further. If you have a hard time fitting under M, the parent task might need to go back to master-architect for re-design.

### `files_to_modify` and `files_to_create`

List actual file paths. The split should distribute parent's files across sub-tasks. Some files appear in multiple sub-tasks (e.g., `test_service.py` is created in t007a and modified in t007b).

### `depends_on`

Three sources of dependencies:

1. **Inherited from parent**: if parent depends on t001 and t002, every sub-task does too
2. **Inter-sibling**: t007b depends on t007a (because t007b extends t007a's endpoint)
3. **Cross-task (rare for sub-tasks)**: usually unchanged from parent

```yaml
# Sub-task A: just inherits parent
- id: t007a
  parent: t007
  depends_on: [t001, t002]         # parent had [t001, t002]

# Sub-task B: inherits + depends on A
- id: t007b
  parent: t007
  depends_on: [t007a]              # depends on A; doesn't need t001/t002 since they're transitive via A

# Sub-task C: parallel to B
- id: t007c
  parent: t007
  depends_on: [t007a]              # depends on A but NOT on B
```

Validate the DAG is acyclic before saving.

### `acceptance_criteria`

Distribute parent's criteria across sub-tasks. Each sub-task should have at least 1, typically 2-4. Together, sub-tasks must cover all parent criteria.

```yaml
# Parent t007 had:
acceptance_criteria:
  - "pytest tests/unit/users/test_service.py passes"       # ac1
  - "pytest tests/integration/users/test_register_e2e.py passes"  # ac2
  - "register with duplicate email returns 409"           # ac3
  - "register with weak password returns 422"             # ac4
  - "ruff check src/users tests passes"                   # ac5
  - "mypy --strict src/users passes"                       # ac6

# Sub-tasks distribute:
t007a (happy path):
  acceptance_criteria:
    - "pytest tests/unit/users/test_service.py::test_register_happy passes"
    - "pytest tests/integration/users/test_register_e2e.py::test_post_register_returns_201 passes"
    # ac5, ac6 implicit (linting + mypy must pass)

t007b (duplicate detection):
  acceptance_criteria:
    - "register with duplicate email returns 409"
    - "pytest tests/unit/users/test_service.py::test_register_duplicate_raises passes"

t007c (password policy):
  acceptance_criteria:
    - "register with weak password returns 422"
    - "pytest tests/unit/users/test_service.py::test_register_weak_password_rejected passes"
```

Each criterion under sub-task should be executable independently (when that sub-task is being implemented).

### `qas_refs` and `adr_refs`

Distribute per relevance. Some QAS/ADR refs apply to all sub-tasks, others only specific ones.

```yaml
# Parent t007 referenced QAS-03 (brute-force) and ADR-007 (argon2 hashing)
t007a (happy path):
  qas_refs: []                     # QAS-03 doesn't apply to happy path
  adr_refs: [ADR-007]              # argon2 needed even in happy path

t007d (security hardening):
  qas_refs: [QAS-03]               # brute-force is this sub-task's responsibility
  adr_refs: [ADR-007]              # also relevant
```

### `technologies` (optional)

Explicit tech tags help feature-implementer's memory detection (Phase A). Add when the auto-detection might miss something:

```yaml
technologies:
  - python-fastapi
  - pydantic-v2
  - postgres
  - argon2
```

If omitted, auto-detection runs at Phase A.

### `criticality` (optional)

If parent has `criticality: critical`, decide per sub-task whether each inherits:

```yaml
# Parent t007 with criticality: critical
t007a (happy path):
  criticality: critical            # writes auth-relevant data → still critical

t007b (UI text change for error):
  criticality: normal              # not actually security-critical
```

If omitted, feature-implementer's mutation-policy auto-detection runs at Phase E.

## Complete example

Parent task:

```yaml
- id: t007
  title: "Add user registration with full validation and security"
  description: |
    Implement POST /register endpoint that creates a new User, hashing
    password via argon2, with duplicate-email rejection, weak-password
    policy (common-password list, breach check), brute-force defense
    via rate-limiting and captcha, and audit logging.
  complexity: XL
  status: TODO
  files_to_modify:
    - src/api/router.py
  files_to_create:
    - src/users/service.py
    - src/users/repository.py
    - src/users/models.py
    - src/security/rate_limit.py
    - src/security/captcha.py
    - tests/unit/users/test_service.py
    - tests/unit/security/test_rate_limit.py
    - tests/integration/users/test_register_e2e.py
    - tests/security/users/test_register_security.py
  depends_on: [t001, t002]
  acceptance_criteria:
    - "valid registration returns 201"
    - "duplicate email returns 409"
    - "weak password returns 422"
    - "brute-force attempts get rate-limited"
    - "captcha challenge after N failures"
    - "audit log entry on every registration attempt"
  qas_refs: [QAS-03]
  adr_refs: [ADR-002, ADR-007]
  criticality: critical
```

After feature-architect splits it:

```yaml
# Parent updated
- id: t007
  status: SPLIT_INTO
  split_into: [t007a, t007b, t007c, t007d, t007e]
  split_at: "2026-05-12T16:30:00Z"
  split_rationale: |
    XL task with 6 independent capabilities. Decomposed into 5 sub-tasks
    using capability + behavior-progression patterns. t007a establishes
    the slice; t007b-d add hardening; t007e adds observability.
  # ... original fields preserved ...

# Sub-tasks
- id: t007a
  parent: t007
  order: 1
  title: "Register: minimal happy path"
  description: |
    Implement POST /register accepting valid email + password ≥8 chars,
    persisting User with argon2 hash, returning 201 with user_id.
    Defers duplicate detection (t007b), password policy (t007c),
    brute-force defense (t007d), audit log (t007e).
  complexity: M
  status: TODO
  files_to_modify: [src/api/router.py]
  files_to_create:
    - src/users/service.py
    - src/users/repository.py
    - src/users/models.py
    - tests/unit/users/test_service.py
    - tests/integration/users/test_register_happy.py
  depends_on: [t001, t002]
  acceptance_criteria:
    - "valid registration returns 201"
  qas_refs: []
  adr_refs: [ADR-002, ADR-007]
  criticality: critical

- id: t007b
  parent: t007
  order: 2
  title: "Register: duplicate-email rejection"
  description: |
    Add duplicate-detection to register service. Returns 409 if email
    already exists. Builds on t007a.
  complexity: S
  status: TODO
  files_to_modify:
    - src/users/service.py
    - tests/unit/users/test_service.py
  files_to_create:
    - tests/integration/users/test_register_duplicate.py
  depends_on: [t007a]
  acceptance_criteria:
    - "duplicate email returns 409"
  qas_refs: []
  adr_refs: []
  criticality: critical

- id: t007c
  parent: t007
  order: 3
  title: "Register: password policy enforcement"
  description: |
    Reject weak passwords: minimum 8 chars (covered by Pydantic),
    not in common-password list, not in breached-password database.
    Returns 422 for weak passwords. Builds on t007a.
  complexity: M
  status: TODO
  files_to_modify:
    - src/users/service.py
    - tests/unit/users/test_service.py
  files_to_create:
    - src/security/password_policy.py
    - tests/unit/security/test_password_policy.py
    - tests/security/users/test_password_strength.py
  depends_on: [t007a]
  acceptance_criteria:
    - "weak password returns 422"
    - "common password rejected"
    - "breached password rejected"
  qas_refs: []
  adr_refs: []
  criticality: critical

- id: t007d
  parent: t007
  order: 4
  title: "Register: brute-force defense (rate limit + captcha)"
  description: |
    Add rate-limiting middleware (5 attempts per IP per 5 min) and
    captcha challenge after 3 failures. Builds on t007a; can run
    parallel to t007b, t007c.
  complexity: M
  status: TODO
  files_to_modify:
    - src/api/router.py
  files_to_create:
    - src/security/rate_limit.py
    - src/security/captcha.py
    - tests/unit/security/test_rate_limit.py
    - tests/unit/security/test_captcha.py
    - tests/security/users/test_register_brute_force.py
  depends_on: [t007a]
  acceptance_criteria:
    - "brute-force attempts get rate-limited"
    - "captcha challenge after 3 failures"
  qas_refs: [QAS-03]
  adr_refs: []
  criticality: critical

- id: t007e
  parent: t007
  order: 5
  title: "Register: audit log"
  description: |
    Emit audit-log entry on every registration attempt (success and
    failure). Builds on t007a; can run after t007b-d.
  complexity: S
  status: TODO
  files_to_modify:
    - src/users/service.py
  files_to_create:
    - src/audit/registration_log.py
    - tests/unit/audit/test_registration_log.py
  depends_on: [t007a]
  acceptance_criteria:
    - "audit log entry on every registration attempt"
  qas_refs: []
  adr_refs: []
  criticality: critical
```

This DAG allows t007b, t007c, t007d, t007e to run in parallel after t007a completes.

## Validation

Before writing to tasks.yaml, verify:

- [ ] All sub-task IDs are unique
- [ ] All sub-tasks have `parent` set to the original task's ID
- [ ] All sub-tasks have `order` set, increasing within siblings
- [ ] All sub-tasks have complexity `S` or `M`
- [ ] DAG has no cycles
- [ ] Every parent acceptance criterion maps to at least one sub-task's criteria
- [ ] Files distribution covers all parent files
- [ ] Original task marked `SPLIT_INTO` with `split_into` list
- [ ] Total sub-tasks count is 2-5 (not 1, not 6+)
