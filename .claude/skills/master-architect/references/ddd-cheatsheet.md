# DDD Cheatsheet (Strategic + Tactical)

For Phase 2 when the system has ≥2 distinct sub-domains. For Phase 3 module-level decisions.

## Strategic DDD (Phase 2)

### Bounded Context

A **bounded context** is a boundary within which a model is consistent and a ubiquitous language is unambiguous. Inside a context, "Customer" means one thing; in another context, "Customer" may mean something different and that's fine.

Signals you have multiple bounded contexts:
- The same word means different things to different stakeholders (sales' "Customer" vs support's "Customer")
- Different teams own different parts and don't want their changes to break others
- Different release cycles are needed

For master-architect: each bounded context typically maps to one Phase 2 container (or one folder/package in Phase 3).

### Subdomain types

- **Core subdomain**: the part that creates competitive advantage. Spend most effort here. Custom built.
- **Supporting subdomain**: needed but not differentiating. Custom built or off-the-shelf with adaptation.
- **Generic subdomain**: same as everyone has (auth, billing, notifications). Buy or use off-the-shelf if at all possible.

For a tax-advisory platform example: tax-filing-logic = core, document-management = supporting, auth = generic.

### Context Map: 7 integration patterns

How bounded contexts relate. The pattern affects API design, schema evolution, and team coordination.

1. **Partnership**: two contexts must succeed or fail together; close coordination required. Use when teams have shared deadlines and shared goals. *Risky if teams are independent.*

2. **Shared Kernel**: small subset of models shared across two contexts. Effective when changes there are rare. Otherwise becomes a bottleneck. *Use sparingly.*

3. **Customer-Supplier**: upstream context delivers a "product" to the downstream context, but downstream needs are part of upstream's planning. Functional relationship between teams.

4. **Conformist**: downstream conforms to upstream's model (no influence). Use when upstream is large/popular and we have no leverage (e.g., integrating with a SaaS provider).

5. **Anti-Corruption Layer (ACL)**: downstream wraps upstream behind a translation layer to protect its own model. Use when upstream's model is messy/legacy and we don't want it polluting our domain.

6. **Open Host Service**: upstream defines a well-defined protocol that any downstream can use. Multiple consumers; the protocol is the contract.

7. **Published Language**: a well-documented, versioned schema language as the contract (e.g., REST OpenAPI, GraphQL schema, gRPC proto). The language is more important than any one consumer.

Pick the one that matches the real organizational dynamic. Don't force shared kernel between teams that move at different speeds.

### Ubiquitous Language

Each bounded context has its own ubiquitous language. Two rules:
1. Code uses the same words as domain experts
2. When the language is unclear, the model is unclear

For master-architect: Phase 0 produces glossary seeds. Phase 2 sharpens them within each bounded context. Phase 3 ensures code matches.

## Tactical DDD (Phase 3 module-level)

Used inside a bounded context to organize the code.

### Aggregate

A cluster of objects treated as one unit for transactional consistency. Has one **aggregate root** (the entry point); external code only touches the root.

Rules:
- Modify aggregate state only through the root
- Each transaction touches one aggregate
- References between aggregates are by ID, not direct object reference

Anti-pattern: large aggregates (everything is in one big aggregate). Prefer many small aggregates.

### Entity

An object with identity that persists over time. Two entities with the same attributes can be different things (because they have different IDs).

Examples: User, Order, Document.

### Value Object

An object identified by its attributes. Two value objects with the same attributes are equal.

Examples: Money($amount, $currency), Address, DateRange.

In Python: implement as `@dataclass(frozen=True)` for internal value objects, Pydantic `BaseModel` with `frozen=True` for boundary value objects.

### Domain Service

Logic that doesn't naturally belong to any entity or value object. Operates on multiple aggregates.

Example: `TransferService.transfer(from_account, to_account, amount)` doesn't fit on either Account.

Should be rare. If you have many domain services, your entities are anemic.

### Repository

Persistence abstraction for an aggregate. Lives at the boundary of the bounded context.

Interface defined in the domain layer, implementation in infrastructure layer. (Hexagonal architecture makes this explicit.)

### Domain Event

Something happened in the domain that domain experts care about. Past-tense names: `OrderPlaced`, `UserRegistered`, `TaxReturnFiled`.

Used for:
- Decoupling reactions ("when order placed, send confirmation email")
- Audit log (events are the audit)
- Cross-aggregate consistency (eventual consistency between aggregates)

Don't conflate with "events" in event-driven architecture (which are infrastructure messages). Domain events are *domain concepts*.

## DDD-lite for master-architect

Default scope:
- ✅ Bounded contexts (Phase 2 → containers)
- ✅ Ubiquitous language (Phase 0 glossary → Phase 2 per-context terms)
- ✅ Context map patterns (Phase 2 boundaries)
- ✅ Entities + value objects (Phase 3 modules)
- ✅ Aggregates (Phase 3, only when transactional boundaries matter)
- ✅ Repositories (Phase 3, when persistence exists)

Defer until needed:
- ⚠️ Domain events (only when decoupling demands it)
- ⚠️ Sagas (only for cross-aggregate, cross-service workflows)
- ⚠️ CQRS (only when read patterns differ from write at scale)
- ⚠️ Event sourcing (rarely; see anti-patterns.md)

## When to use DDD vs not

**Use DDD**: complex domain with non-trivial business rules, multiple stakeholders, ubiquitous language matters, long-term maintenance.

**Don't use DDD**: CRUD-only app with no real domain (think internal admin tool), throwaway script, single-bounded-context system where layered architecture suffices.

## Sources

- Eric Evans, *Domain-Driven Design: Tackling Complexity in the Heart of Software* (2003)
- Vaughn Vernon, *Implementing Domain-Driven Design* (2013) — more practical
- Eric Evans, *Domain-Driven Design Reference* — free PDF on Evans's site, the cheatsheet
- Khononov, *Learning Domain-Driven Design* (2021) — modernized
