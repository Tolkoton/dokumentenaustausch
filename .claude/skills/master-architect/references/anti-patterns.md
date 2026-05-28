# Architecture Anti-Patterns

Patterns master-architect should actively refuse during GENERATE step of Phase 2, or flag during CRITIQUE step. Each entry: what the anti-pattern looks like, why it's harmful, what to do instead.

## Microservices for solo / small team

**Signal**: team is 1-3 people, request mentions "microservices", "split into services", or "domain services" as separate deployments.

**Why harmful**: distributed system complexity (network failures, eventual consistency, observability across services, deployment orchestration) requires SRE capacity that 1-3 people don't have. Result is a "distributed monolith" with all the latency of microservices and none of the team-autonomy benefits.

**Instead**: modular monolith with `import-linter` enforced bounded contexts. When team grows past ~6 people and a specific bounded context becomes a bottleneck, extract that one. See `references/architecture-styles.md`.

**Acceptable exception**: extracting a single hot service from a monolith because measured contention forces it — but this is one service split off, not microservices from day 1.

## Event sourcing for ordinary CRUD

**Signal**: user mentions event sourcing without a regulatory audit requirement, OR the data model is fundamentally state-oriented (orders, users, accounts) without time-travel needs.

**Why harmful**: event schema evolution is permanent (you can never delete or change an event without complex migration), projections are stateful and brittle, the team's mental model has to fundamentally shift. Most teams aren't ready.

**Instead**: normal database with `created_at`, `updated_at`, optional `audit_log` table for write history. 95% of audit needs are met.

**Acceptable exception**: regulatory audit (financial, medical), genuine time-travel use case (debugging financial transactions), team has prior ES experience and a clear scope.

## CQRS without measured read/write divergence

**Signal**: user mentions CQRS or splitting "command" and "query" models without showing that read patterns substantially differ from write patterns at scale.

**Why harmful**: doubles model code, introduces consistency complexity, often premature.

**Instead**: normal model. If reads become a problem, add a read-side cache or read replica first.

**Acceptable exception**: read patterns are genuinely orthogonal (reporting dashboards from transactional data) AND scale forces separation.

## Hexagonal for tiny tools

**Signal**: project is <500 lines or a one-purpose script, but user wants "proper" architecture with ports and adapters.

**Why harmful**: 5x file count, 3x complexity, indirection that obscures rather than reveals.

**Instead**: layered or flat. A 200-line script is not a system.

**Acceptable exception**: starting small but plan to grow into a system, OR using hexagonal as a learning exercise (then it's about learning, not architecture).

## God container / god module

**Signal**: one Phase 2 container with responsibilities that span 3+ unrelated concerns ("manages users AND sends notifications AND handles payments"). One Phase 3 module file >500 lines doing several things.

**Why harmful**: violates SRP at the worst possible level. Becomes the source of bugs and the bottleneck for changes.

**Instead**: split. If the responsibilities are AND-able in description, they're separable in code.

## Anemic domain

**Signal**: domain models are bags of attributes with no behavior; all logic lives in "service" or "manager" classes.

**Why harmful**: misses the point of OO/domain modeling, makes domain rules hard to find (scattered across services), tests become brittle (testing services that test domain).

**Instead**: behavior on the entity that owns the state changes. Services orchestrate; entities decide.

**Tradeoff**: pure DDD-style rich domain isn't always right. Functional core/imperative shell is another good answer. The anti-pattern is *not thinking about it* and defaulting to anemic.

## Premature framework lock-in

**Signal**: Phase 3 layout only makes sense if you use FastAPI / Django / specific ORM. Domain logic imports framework classes.

**Why harmful**: framework swap (later, when forced) becomes a rewrite. Domain tests need framework to run.

**Instead**: domain doesn't import framework. Application layer adapts framework to domain. Hexagonal makes this explicit but you can do it informally.

## Distributed transactions

**Signal**: design requires "transaction across services" or "two-phase commit".

**Why harmful**: distributed transactions are notoriously fragile, slow, and often impossible in cloud. Most popular databases don't support them properly across boundaries.

**Instead**: keep transactional boundaries inside one service. For cross-service consistency: outbox pattern, sagas, or eventual consistency with reconciliation. Or: don't split the boundary (one service for one transactional invariant).

## Shared database across services

**Signal**: two "services" both directly access the same tables.

**Why harmful**: not really separate services, just separate deployments with hidden coupling. Schema changes break multiple services.

**Instead**: one service owns the data; others access via that service's API. If they need direct access, they're not really separate services — merge or split properly.

## Smart networking layer

**Signal**: design puts business logic in API gateway, service mesh, or message broker ("the bus decides routing", "the gateway enforces business rules").

**Why harmful**: business logic in infrastructure makes it hard to test, hard to evolve, often vendor-specific.

**Instead**: smart endpoints, dumb pipes. Network transports messages; services decide what to do.

## "We'll add it later" for cross-cutting

**Signal**: Phase 2 architecture mentions auth/logging/observability as "we'll add it later".

**Why harmful**: cross-cutting concerns retrofitted are 5-10x harder than designed-in. Auth especially.

**Instead**: every cross-cutting concern in Phase 2 has a stance, even if minimal: "auth is JWT verified at API gateway, propagated as user_id header to services" — that's a stance.

## Premature optimization for scale you don't have

**Signal**: design accommodates 10K users/sec when QAS says 100/sec. Solution introduces caching, sharding, queues for data volumes the system won't see for years.

**Why harmful**: complexity tax paid up front; flexibility lost for changes you'll actually need.

**Instead**: design for the QAS specified. Note explicit "scale path: if X happens, do Y" as a future-state note. Don't build for it yet.

## Resume-driven architecture

**Signal**: tech choices that don't match QASes or team skills, justified by "we want to learn it" or "it's the modern way".

**Why harmful**: takes engineering hours away from the actual problem; team productivity drops; new tech often has gotchas only learned the hard way.

**Instead**: learn new tech on side projects or low-stakes parts. Architecture is not a learning exercise for the user's project.

## Refusal protocol

When master-architect detects an anti-pattern in user's request:

1. Name it explicitly: "What you're describing is the [anti-pattern name] anti-pattern."
2. Explain harm in 1-2 sentences with reference to user's specific context (their team size, scale, etc.)
3. Propose the standard alternative
4. ASK before proceeding: "Do you want to override this recommendation? If so, please explain the reason — I'll add it as an ADR."

Override is allowed but must be explicit and documented.
