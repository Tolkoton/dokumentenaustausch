# Pydantic at Boundaries

Type-driven architecture pattern: Pydantic v2 lives at system boundaries, plain Python (`@dataclass(frozen=True)` or domain classes) lives in the domain core. The boundary classes validate; the domain classes assume valid input.

## The pattern

```
┌──────────────────────────────────────────────────────────────┐
│ Boundary layer (Pydantic models)                              │
│   - HTTP request/response DTOs                                │
│   - Config (pydantic-settings)                                │
│   - LLM structured output                                     │
│   - Persistence DTOs (when ORM/raw DB rows ≠ domain)          │
│   - Cross-process messages (events, queue payloads)           │
│   - File parse outputs (CSV, JSON, YAML inputs)               │
│                                                                │
│   Validation happens HERE. Strict mode. Frozen.                │
└────────────┬─────────────────────────────────────────────────┘
             │ mapper / from_boundary classmethod
             ▼
┌──────────────────────────────────────────────────────────────┐
│ Domain layer (plain Python)                                    │
│   - @dataclass(frozen=True) for value objects                  │
│   - Plain classes for entities (with behavior)                 │
│   - Assume valid input; no defensive validation                │
│   - No Pydantic imports here                                   │
│   - msgspec instead of Pydantic if hot path                    │
└──────────────────────────────────────────────────────────────┘
```

## Why this split

1. **Performance**: Pydantic validation costs ~1-10µs per field. In hot paths (per-request domain ops), this matters.
2. **Decoupling**: domain doesn't depend on Pydantic; framework changes don't ripple into domain.
3. **Testability**: domain tests don't need to construct Pydantic models; they use simple objects.
4. **Clarity**: validation is in one place (boundary). Domain code reads as business logic, not as validation.

## Boundary models (Pydantic v2)

Standard config for boundary models:

```python
from pydantic import BaseModel, ConfigDict, Field, EmailStr
from typing import Annotated, Literal
from datetime import datetime

class RegisterUserRequest(BaseModel):
    """HTTP request DTO."""
    model_config = ConfigDict(
        strict=True,        # No type coercion (str "5" won't become int 5)
        frozen=True,        # Immutable
        extra="forbid",     # Reject unknown fields
        str_strip_whitespace=True,
    )

    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=128)]
    display_name: Annotated[str, Field(min_length=1, max_length=80)]
```

## Discriminated unions for polymorphic boundary

When the boundary accepts a tagged union (event types, document types, etc.):

```python
from pydantic import BaseModel, Discriminator, Tag
from typing import Annotated, Literal, Union

class CreatedEvent(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)
    type: Literal["created"]
    user_id: str
    at: datetime

class DeletedEvent(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)
    type: Literal["deleted"]
    user_id: str
    at: datetime
    reason: str

UserEvent = Annotated[
    Union[CreatedEvent, DeletedEvent],
    Discriminator("type"),
]
```

Pydantic v2's discriminator gives O(1) dispatch and clear error messages when the tag doesn't match.

## Domain models (plain Python)

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import NewType

UserId = NewType("UserId", str)
Email = NewType("Email", str)

@dataclass(frozen=True)
class User:
    """Domain entity. Assumes valid input — no validation."""
    id: UserId
    email: Email
    display_name: str
    created_at: datetime

    def can_login(self) -> bool:
        # Business rule lives here
        return self.display_name != ""
```

For entities that mutate state through methods (rare; prefer immutable + replace):

```python
class Account:
    """Mutable entity. Methods enforce invariants."""
    def __init__(self, id: AccountId, balance: Money):
        self._id = id
        self._balance = balance

    @property
    def id(self) -> AccountId: return self._id

    @property
    def balance(self) -> Money: return self._balance

    def withdraw(self, amount: Money) -> None:
        if amount > self._balance:
            raise InsufficientFunds()
        self._balance -= amount
```

## Mappers

The translation between boundary and domain:

```python
# Inbound: Pydantic → domain
def request_to_user(req: RegisterUserRequest, user_id: UserId) -> User:
    return User(
        id=user_id,
        email=Email(req.email),
        display_name=req.display_name,
        created_at=datetime.now(timezone.utc),
    )

# Outbound: domain → Pydantic
class UserResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    email: str
    display_name: str

def user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
    )
```

## Where Pydantic earns its keep

| Boundary | Use Pydantic? |
|----------|---------------|
| HTTP request body | YES — validation is the boundary's job |
| HTTP response body | YES — schema documentation, serialization |
| Config (env vars, files) | YES — pydantic-settings is the standard |
| CLI args | YES — strict-typed; pair with click/typer |
| LLM structured output | YES — instructor / outlines integration |
| Queue messages | YES — schema versioning, validation on read |
| Database row → object | DEPENDS — use ORM (SQLModel has Pydantic), or hand-write mapper |
| Internal domain | NO — overhead without benefit |
| Hot path inner loop | NO — use msgspec or plain classes |

## NewType vs Pydantic for type narrowing

For internal type discipline (preventing "passed a user_id where account_id was expected"), use `NewType`:

```python
from typing import NewType
UserId = NewType("UserId", str)
AccountId = NewType("AccountId", str)

def transfer(from_account: AccountId, to_account: AccountId) -> None: ...

uid: UserId = UserId("u123")
transfer(uid, uid)  # mypy ERROR: expected AccountId, got UserId
```

`NewType` is free at runtime (it's just `str`), but mypy enforces the distinction. Pydantic validation at the boundary is what creates these typed values:

```python
class CreateAccountRequest(BaseModel):
    owner_id: Annotated[str, Field(pattern=r"^u[a-z0-9]+$")]

def handle(req: CreateAccountRequest):
    owner = UserId(req.owner_id)  # Boundary creates the typed value
    ...
```

## Illegal-states-unrepresentable

The goal of type-driven design: don't let bad states exist in the type system.

```python
# BAD: status and rejection_reason can be inconsistent
@dataclass
class Application:
    status: Literal["pending", "approved", "rejected"]
    rejection_reason: str | None  # only meaningful if status == "rejected"

# GOOD: variants enforce the relationship
@dataclass(frozen=True)
class PendingApplication: ...

@dataclass(frozen=True)
class ApprovedApplication:
    approved_at: datetime

@dataclass(frozen=True)
class RejectedApplication:
    rejected_at: datetime
    reason: str

Application = PendingApplication | ApprovedApplication | RejectedApplication
```

Combined with Pydantic discriminated unions at the boundary, this composes well.

## Anti-patterns

- **Pydantic in domain methods**: pollutes domain with framework, breaks the boundary pattern
- **Domain calling `model_validate`**: validation should happen once at the boundary, never re-validated downstream
- **Mixing Pydantic and dataclass in same module**: confuses the reader; pick a layer per module
- **Defensive validation in domain**: "what if `email` is None?" — boundary already ensured it isn't. Trust the boundary.
- **Pydantic for value objects in hot loops**: at 100K invocations/sec, Pydantic overhead becomes measurable

## msgspec for hot paths

If you have a hot loop where Pydantic shows up in profiles, msgspec is 10-100x faster:

```python
import msgspec

class Trade(msgspec.Struct, frozen=True):
    symbol: str
    price: Decimal
    quantity: int
    at: datetime
```

Use sparingly — Pydantic's ecosystem (FastAPI, instructor, etc.) is the default unless profiling forces msgspec.

## Sources

- Scott Wlaschin, *Domain Modeling Made Functional* (2018) — illegal-states-unrepresentable
- Pydantic v2 docs: docs.pydantic.dev
- Vaughn Vernon, *Implementing Domain-Driven Design* — boundary/domain separation
