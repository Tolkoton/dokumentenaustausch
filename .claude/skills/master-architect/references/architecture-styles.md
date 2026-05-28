# Architecture Styles Reference

Compressed reference for Phase 2 GENERATE step. Consult when choosing an architectural style.

## Style selection decision matrix

Inputs (from Phase 1 + Phase 0):
- **Team size** (people who code on this system)
- **Change rate** (how often the system's behavior changes meaningfully)
- **Scale** (peak load: requests/sec, data volume, user count)
- **Domain complexity** (one bounded context vs many)

| Team | Change | Scale | Complexity | Recommended style |
|------|--------|-------|------------|-------------------|
| 1-3  | any    | small | one        | **Modular monolith** (default) |
| 1-3  | low    | small | multi      | Modular monolith with strict bounded-context packages |
| 1-3  | any    | large | any        | Modular monolith first; extract a hot service only when measured |
| 4-10 | high   | medium-large | multi | Modular monolith → migrating toward service-per-context |
| 10+  | high   | large | multi      | Microservices, but only if team-per-service is achievable |
| any  | any    | any   | one        | NEVER microservices (one context = one service) |

**Default for solo developer or small team**: Modular monolith. Justify any other choice in an ADR.

## Common styles (concise)

### Modular monolith

- **What**: single deployable unit, internally organized as multiple bounded contexts with strict module boundaries
- **Strengths**: simple deploy, easy debugging, low ops overhead, refactor-friendly
- **Weaknesses**: can't scale teams independently per context; risk of accidental coupling without discipline
- **Discipline required**: enforce module boundaries with `import-linter` or equivalent
- **When**: ≤10 people, ≤3 bounded contexts, or any solo/small project

### Hexagonal (Ports & Adapters)

- **What**: domain core surrounded by ports (interfaces) and adapters (implementations); inversion of dependency direction so infrastructure depends on domain, not vice versa
- **Strengths**: testable (swap adapters in tests), framework-agnostic domain
- **Weaknesses**: more files; can feel over-engineered for small projects
- **When**: testability is high-value (TDD-heavy), domain logic is non-trivial, integrations with external systems will likely change
- **Combine with**: modular monolith (this is an *internal organization* style, compatible with single deployment)

### Layered

- **What**: classic presentation / application / domain / infrastructure layers; dependency flows top-down (presentation depends on app, app on domain, domain on infrastructure — though hexagonal inverts the last one)
- **Strengths**: familiar to most developers, easy to navigate, good default for CRUD apps
- **Weaknesses**: tendency toward anemic domain (logic leaks into application layer)
- **When**: traditional CRUD apps with clear UI/API surface

### Event-driven

- **What**: components communicate via events; loose coupling in time and space
- **Strengths**: scales to many producers and consumers, naturally supports audit log
- **Weaknesses**: harder debugging (no call stack across events), eventual consistency complications, event schema evolution is hard
- **When**: real audit-log requirement, many independent producers, async processing
- **AVOID for**: simple request-response CRUD with one bounded context

### CQRS (Command-Query Responsibility Segregation)

- **What**: separate models for writes (commands) and reads (queries), often with separate stores
- **Strengths**: read side optimized independently from write; supports complex reporting
- **Weaknesses**: write-read sync complexity, double the model code
- **When**: read patterns substantially differ from write patterns AND scale demands separation
- **AVOID for**: simple CRUD, single-store apps

### Event Sourcing

- **What**: store events (state changes) as the source of truth; reconstruct state by replaying events
- **Strengths**: complete audit log built-in, time-travel debugging, supports CQRS naturally
- **Weaknesses**: hard to evolve event schemas, projections are stateful and complex, often misunderstood
- **When**: regulatory audit requirement, complex temporal queries, the team has prior event-sourcing experience
- **AVOID for**: typical business apps, prototypes, teams without prior ES exposure

### Microservices

- **What**: many deployable services, each owning its data, communicating over network
- **Strengths**: scale teams independently, deploy services independently, language flexibility
- **Weaknesses**: distributed system problems (network, partial failure, consistency), ops complexity, cross-service refactoring is painful
- **When**: organization has ≥4 teams that need autonomy AND team has SRE/devops capacity
- **AVOID for**: solo, small team, prototype, single bounded context

### Serverless (function-as-a-service)

- **What**: stateless functions triggered by events, managed by cloud platform
- **Strengths**: zero ops on infrastructure, scales to zero, pay-per-use
- **Weaknesses**: cold starts, vendor lock-in, hard to test locally, limits on execution time
- **When**: bursty workloads, glue code between cloud services, prototypes
- **AVOID for**: long-running processes, predictable steady-state load

## Anti-patterns (REFUSE these)

- **Microservices for solo developer or 2-3 person team** — distributed monolith with extra steps. The communication tax bankrupts the small team.
- **Event sourcing for CRUD app** — solving a problem you don't have. Use a normal database with audit columns.
- **CQRS without scale demand** — you're paying double in code complexity to solve a problem that doesn't exist.
- **Hexagonal for trivial scripts** — over-engineered. A 200-line tool doesn't need ports.
- **Serverless for long-running batch** — fundamental fit mismatch.
- **Choosing style first, then forcing requirements to fit** — always derive from QASes, not from "what's cool".

## Hybrid is often correct

Most real systems are hybrid. Example: modular monolith (overall) + hexagonal (within each bounded context) + event-driven (for one specific cross-context concern like notifications). Don't pretend you have one style if you really have three.

## Document the choice

Every non-default style choice (anything other than modular monolith for small teams) deserves an ADR (Architecture Decision Record) per `references/madr-format.md`. The ADR must reference at least one QAS or constraint that forced the choice.

## Cite-backed sources

- Martin Fowler, *Patterns of Enterprise Application Architecture* (layered)
- Eric Evans, *Domain-Driven Design* (modular monolith with bounded contexts)
- Alistair Cockburn, "Hexagonal Architecture" (ports and adapters)
- Vaughn Vernon, *Implementing Domain-Driven Design* (CQRS, ES with caveats)
- Sam Newman, *Building Microservices* (microservices with extensive caveats on team size)
- Anthony Ferrara, ["Building Microservices? Don't"](https://blog.ircmaxell.com/) (anti-pattern: small-team microservices)
