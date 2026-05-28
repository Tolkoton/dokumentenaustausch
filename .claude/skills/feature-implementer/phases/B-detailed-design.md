# Phase B — Detailed Design

**Goal**: think hard before coding. Apply tactical DDD at task scope: domain model for this slice, public surfaces, boundary types, dependency wiring. Run karpathy pre-action check against the design.

**Inputs**: Phase A context (architecture artifacts, memory, existing code).

**Outputs**: `.architecture/tasks/<id>/design.md` covering all decisions made BEFORE code is written.

This phase has NO code generation. Pure thinking and writing the plan.

## Why this phase exists

Master-architect's Phase 2 designed the **system** (containers, ADRs, components). It did NOT design the **internals** of this specific feature. That's what Phase B does.

Without Phase B: implementer dives into TDD, designs on the fly, ends up with anemic models, inconsistent error types, missing boundary validation. Test list is shallow because no model exists yet to derive properties from.

With Phase B: TDD becomes test-first execution of a thought-through design, not exploration.

## Step 1: Domain modeling for this slice

Identify the slice this task represents in the bounded context. Apply tactical DDD per `references/ddd-task-application.md`:

### 1.1 Entities

For each entity touched/created in this task:
- **Name**: ubiquitous-language term (consult Phase 0 glossary if present)
- **Identity**: how is it identified? UUID? composite key? natural key?
- **Lifecycle**: created when? deleted when? mutable or immutable?
- **Invariants**: what must always be true? List them. Each invariant is a candidate Hypothesis property in Phase C.

### 1.2 Value objects

For each "thing" that's defined by attributes not identity:
- **Name**
- **Attributes** with types
- **Validation rules** (which become boundary validation or constructor checks)
- **Operations**: what behavior belongs on it? (e.g., `Money.__add__`, `Email.normalize`)

Default representation:
- **At boundary** (HTTP, queue, file): Pydantic `BaseModel` with `strict=True, frozen=True, extra="forbid"`
- **In domain**: `@dataclass(frozen=True)` or plain immutable class with behavior

### 1.3 Aggregates

If the task touches transactional state across multiple entities, identify the aggregate root. Rules:
- Only the root is referenced from outside
- All state mutations go through root methods
- One transaction = one aggregate touch

Often a task does NOT introduce a new aggregate. That's fine — note "no new aggregate" explicitly.

### 1.4 Domain services

Logic that doesn't naturally belong on an entity or value object goes in a domain service. Examples: transferring between two accounts, validating a request against multiple aggregates.

Don't over-create services. If you have more services than entities, you're producing anemic domain — push behavior onto entities.

## Step 2: Public surface design

For each public function/class the task adds:

```markdown
### `register(email, password) -> UserId`

**Module**: `src/users/service.py`

**Signature**:
\`\`\`python
def register(
    email: EmailStr,
    password: Annotated[str, Field(min_length=8, max_length=128)],
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    repo: UserRepository,
) -> UserId:
\`\`\`

**Preconditions**:
- email is well-formed (Pydantic EmailStr already enforces)
- password ≥8 chars (Pydantic Field already enforces)

**Postconditions**:
- A new User exists in the repository with given email
- Password is hashed via argon2 per ADR-007
- User has fresh UserId (UUID v7)
- Returns the new UserId

**Errors raised**:
- `DuplicateEmailError`: email already registered
- `WeakPasswordError`: password meets length but fails policy (common passwords list, breached passwords)
- `RepositoryError`: persistence failure (re-raised after audit log entry)

**Side effects**:
- One DB INSERT
- One audit log entry (UserRegistered domain event)
- Zero external network calls
```

Repeat for each function/method.

## Step 3: Boundary types

Identify every "edge" this task crosses:

- **HTTP request body** → Pydantic model
- **HTTP response body** → Pydantic model
- **DB row** → either Pydantic model (if using SQLModel) or mapper to dataclass
- **Domain event published** → Pydantic model (schema versioned)
- **Configuration consumed** → Pydantic Settings model
- **CLI args** (if applicable) → Pydantic or Typer model

For each, draft the model skeleton inline in design.md:

```python
class RegisterUserRequest(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=128)]
    display_name: Annotated[str, Field(min_length=1, max_length=80)]

class UserResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    user_id: str
    email: str
    display_name: str
    created_at: datetime
```

Delegate to `pydantic-v2-conventions` skill — cue: _"verify boundary models follow Pydantic v2 conventions"_.

## Step 4: Dependency wiring

How does this code get its dependencies?

- Hard-coded? (only for true constants)
- Constructor injection? (services that hold state)
- Function parameter? (preferred for stateless functions; see signature in step 2)
- Module-level imports? (only for truly stable utilities)

For each dependency in the task:
- Source (where it comes from — DI container, factory, app startup)
- Lifetime (singleton, per-request, per-call)
- Test substitution strategy (mock? stub? fake? real DB with rollback?)

Test substitution strategy directly informs Phase C: integration tests use real, unit tests use fakes/stubs.

## Step 5: Error type design

List every error this task can produce. For each:

```markdown
### `DuplicateEmailError`

**When raised**: `register()` called with email already in DB
**Type**: subclass of `UserError(DomainError)`
**Carries**: email that conflicted (for logging, not user response)
**HTTP mapping**: 409 Conflict
**User-facing message**: "Email already registered" (NOT "the email X already exists" — privacy)
**Log level**: INFO (not an exception condition; expected business outcome)
```

Common mistake: catching too broadly. Each domain error is its own class. Don't conflate "validation failed" with "duplicate" with "infrastructure broken".

## Step 6: Karpathy pre-action check

Delegate to `karpathy-pre-action-check` skill — cue: _"run the pre-action check on this design before I write any test"_.

Three checks:
1. **Silent assumptions**: every assumption made in design.md is explicit. "User will provide email" must appear as "function signature requires email parameter".
2. **Over-complication**: nothing in design.md was unrequested. If user asked for `register()`, don't design 3-factor auth.
3. **Unrequested scope**: every public function/class in design.md traces to an acceptance criterion in task spec.

If the check fails, fix design.md before proceeding.

## Step 7: Cross-references

Update `tasks/<id>/design.md` to explicitly cross-reference:

- ADRs that constrain this task (e.g., "Password hashing per ADR-007")
- QASes this task addresses (e.g., "Implements QAS-03 brute-force resistance via rate-limiting in adjacent task t012")
- Container ownership (e.g., "Lives in `user_service` container per Phase 2")
- Phase 3 dependency rules respected (e.g., "Does not import from infrastructure — repository accessed via interface")

This makes Phase E review cheaper (reviewer can verify against architecture).

## Step 8: Open questions

Anything you can't decide alone in this design? Examples:
- Edge case the user didn't specify (e.g., "should we trim whitespace in display_name?")
- Conflict between two ADRs the task references
- Missing context (e.g., "Phase 2 says use argon2 but doesn't specify time-cost parameter")

List them in design.md under `## Open questions`. STOP and ask user. Do not invent answers.

## Output: `tasks/<id>/design.md`

```markdown
# Design for t007: <title>

## Domain model
### Entities
### Value objects
### Aggregates (if any)
### Domain services (if any)

## Public surface
### Function A
### Function B
...

## Boundary types
### Inbound DTOs
### Outbound DTOs
### Persistence layer

## Dependencies
### What this task needs
### Test substitution strategy

## Error types
### Error A
### Error B
...

## Cross-references
### ADRs constraining
### QASes addressed
### Container ownership
### Phase 3 rules respected

## Open questions (if any)
```

## Critique step

Walk `checklists/design-quality.md`. For each item PASS/FAIL/UNCERTAIN. FAILs are SCOPE-LOCAL (edit design.md) or SCOPE-UPSTREAM (backtrack to master-architect).

If any open questions remain unanswered: STOP and ask user.

If design.md is solid, proceed to Phase C.

## Anti-patterns in Phase B

- **Designing tests too early**: that's Phase C. In B, design the *domain*, not the test list.
- **Inventing requirements**: only design what's traceable to task spec + acceptance criteria.
- **Over-modeling**: 5 value objects for "the user has a name and email" is over-modeling. Most projects have 2-3 entities, several value objects.
- **Anemic models**: if your entity has only attributes and no methods, you're missing where behavior should live.
- **Ignoring open questions**: writing "I'll figure it out in TDD" is asking for backtrack.
- **Skipping karpathy check**: cheap, high yield. Do it.
