# DDD Applied at Task Level

Phase 2 of master-architect did **system-wide** DDD: bounded contexts, context maps, container responsibilities. Feature-implementer's Phase B does **task-scope** DDD: this slice's domain model.

Same vocabulary (entities, value objects, aggregates), different scope.

## What's already decided (from upstream)

Don't re-decide:
- Which **bounded context** this task lives in (Phase 2 owns this)
- Cross-context **integration patterns** (Phase 2's context map)
- **Ubiquitous language** at bounded-context level (Phase 0 glossary + Phase 2 sharpening)
- **Container responsibilities** (Phase 2 ADRs)
- **Folder layout** of the bounded context (Phase 3)

If your Phase B work needs to revise any of the above → backtrack signal.

## What Phase B decides

Per task, design.md captures:

### 1. Entities introduced or modified

For each:

```markdown
### Entity: `User`

Status: NEW (this task creates it)

Identity:
  - `id: UserId` (`UserId = NewType("UserId", str)`, UUID v7 format per ADR-003)

Lifecycle:
  - Created by: register() (this task)
  - Updated by: update_profile() (future task t012)
  - Deleted by: delete_account() (future task t045)

Invariants (each becomes a potential test in Phase C):
  - email is normalized (lowercase, stripped) at creation
  - email is unique within the system
  - password_hash is argon2id per ADR-007
  - created_at is UTC

Behavior on the entity (vs in services):
  - User.can_authenticate(password) → bool (verifies hash)
  - User.update_email(new_email) → User (returns new instance, frozen)
  - User is frozen dataclass; mutations return new instances
```

### 2. Value objects introduced

For each:

```markdown
### Value object: `Email`

Status: NEW (this task)

Representation:
  - `Email = NewType("Email", str)` at type level
  - Construction via `Email.from_raw(s: str) -> Email`
  - Internal storage: normalized form (lowercase, stripped, no plus-suffix for Gmail)

Validation rules (each becomes a test):
  - Must match RFC 5322 (use `email_validator` library)
  - Domain part must have at least one dot
  - Length ≤320 chars (RFC limit)

Operations:
  - Email.normalize(s) → str (pure function)
  - Email equality is case-insensitive on raw form, case-sensitive on local part by RFC, but we normalize aggressively

Why VO not entity:
  - No identity beyond value
  - Two emails with same string ARE the same email

Anti-bool-trap:
  - Don't expose `is_gmail: bool`; use `provider: EmailProvider` enum if needed
```

### 3. Aggregates touched

For each aggregate this task interacts with:

```markdown
### Aggregate: `User` (root)

Transactional boundary:
  - One register() call = one transaction touching one User aggregate

External access:
  - Only via UserRepository (per Phase 2 hexagonal pattern)

Mutation rules:
  - User.update_email() returns new User (immutable)
  - UserRepository.save(user) persists state change atomically
```

### 4. Domain services (only if needed)

```markdown
### Domain service: `EmailUniquenessChecker`

Status: NEW (this task)

Why needed: checking uniqueness requires repository access; doesn't belong on Email VO.

Operation: `check(email: Email, repo: UserRepository) -> None` (raises DuplicateEmailError if duplicate)

Why service vs entity method:
  - User doesn't exist yet (we're checking before creation)
  - Email VO doesn't know about repository
  - Service is the right home
```

Often you DON'T need a new service. Most tasks add 0 services. If you have 2+ services per task, you're likely:
- Building anemic domain (push behavior to entities)
- Missing a value object opportunity

### 5. Domain events (only when explicitly used)

```markdown
### Domain event: `UserRegistered`

Status: NEW (this task)

Schema:
  - user_id: UserId
  - email: Email (hash only — privacy)
  - at: datetime (UTC)

When emitted: at end of successful register() before transaction commit

Subscribers:
  - audit_log (this task, sibling subscriber)
  - notification_service (future task t023 — welcome email)

Note: this task implements the event TYPE but does NOT implement subscribers. Just the emit.
```

If task doesn't justify a domain event (no decoupled reaction needed): don't add one. They're overhead.

### 6. Invariants list (consolidated)

After designing entities/VOs/services, list all invariants the task is responsible for:

```markdown
## Invariants this task must maintain

1. User.email is unique system-wide (Domain service check)
2. User.password_hash is never plaintext (Entity invariant)
3. User.id is UUID v7 format (Entity invariant)
4. Email is RFC 5322 valid (VO invariant)
5. Email is normalized in storage (VO invariant)
```

Every invariant → Phase C test (probably a Hypothesis property).

## What NOT to do in task-level DDD

### Don't redesign the bounded context

If Phase 2 says "Users" is a bounded context with concepts: User, Role, Permission — don't introduce a 4th concept "AdminPanel" without backtracking.

### Don't add aggregates speculatively

"We might need a UserGroup aggregate someday" → no. When you need it, design it then.

### Don't over-model VOs

`Money(Decimal, Currency)` is a VO. `FirstName(str)` is over-modeling unless you have invariants beyond "string". Use NewType for type discipline; use VO only when behavior or invariants justify.

### Don't conflate domain and DTO

```python
# BAD: same class used at boundary and in domain
class User(BaseModel):
    id: str
    email: str
    password: str  # plaintext from request — bad to mix in domain!

# GOOD: separate
class RegisterUserRequest(BaseModel):  # boundary
    email: EmailStr
    password: str

@dataclass(frozen=True)
class User:  # domain
    id: UserId
    email: Email
    password_hash: PasswordHash  # never plaintext
```

### Don't put framework concerns in domain

`class User(SQLAlchemyBase)` is putting persistence in domain. SQLAlchemy models live at the infrastructure boundary, separate from domain User. Hexagonal architecture from Phase 2 makes this explicit; respect it.

## Trade-off: pure DDD vs functional core

DDD with rich entities is one good answer. Functional core / imperative shell is another:

- **DDD style**: User has methods, encapsulates invariants
  ```python
  user = User(id=id, email=email, hash=hash)
  user = user.update_email(new_email)  # returns new User
  repo.save(user)
  ```

- **Functional style**: User is data; pure functions transform
  ```python
  user = User(id=id, email=email, hash=hash)
  user = update_email(user, new_email)  # pure function
  save(repo, user)
  ```

Both are fine. Pick one per bounded context and stick to it. Don't mix in a single task.

## Per-task DDD checklist

Before leaving Phase B, verify:

- [ ] Each NEW entity has identity, lifecycle, and invariants stated
- [ ] Each NEW value object has validation rules and is justified (vs NewType)
- [ ] Aggregates touched have explicit transactional boundary
- [ ] Domain services exist only when entities can't host the behavior
- [ ] Domain events exist only with subscribers planned (now or near future)
- [ ] Invariants list is consolidated and traceable to Phase C tests
- [ ] No framework imports leaked into domain layer
- [ ] No boundary types (Pydantic) used as domain types
- [ ] Each thing in design.md traces back to an acceptance criterion or invariant

If unsure on a decision: don't invent. Note as open question.

## When to invoke `ddd-cheatsheet.md` from master-architect

If you're unsure about: bounded context patterns, context map, aggregate sizing rules, strategic-vs-tactical DDD vocabulary → read `~/.claude/skills/master-architect/references/ddd-cheatsheet.md`.

That file has the full reference. This file is the task-application of it.
