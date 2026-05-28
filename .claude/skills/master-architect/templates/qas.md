# Quality Attribute Scenario (QAS) Template

QASes are the contract for non-functional requirements (NFRs). They appear in Phase 1 (system design) and are referenced through Phase 2-4. Each QAS must be **testable** — you should be able to write an experiment that shows whether the system satisfies it.

## Structure

A QAS has 6 parts:

| Part        | Description |
|-------------|-------------|
| Source      | Where does the stimulus come from? (user, external system, internal event, attacker, time-based) |
| Stimulus    | What happens? (event, request, failure, attack) |
| Environment | In what context? (normal load, peak load, degraded mode, startup, after failure) |
| Artifact    | What part of the system is affected? (a container, a flow, the whole system) |
| Response    | What does the system do? (allow the request, reject, log, alert, fail gracefully) |
| Measure     | How do we know it worked? (latency budget, throughput target, error rate, recovery time) |

## Template

```markdown
### QAS-<NN>: <Short name>

**Quality attribute:** <performance | availability | scalability | security | maintainability | usability | testability | observability | recoverability | ...>

| Part        | Specification                                              |
|-------------|------------------------------------------------------------|
| Source      | <e.g., authenticated user>                                 |
| Stimulus    | <e.g., issues a "search" request>                          |
| Environment | <e.g., normal operations, 100 concurrent users>            |
| Artifact    | <e.g., search container>                                   |
| Response    | <e.g., returns top-10 ranked results, sorted by relevance> |
| Measure     | <e.g., p99 latency ≤ 200ms; throughput ≥ 50 req/s>         |

**Rationale:** <one sentence why this matters>

**Owner (filled in Phase 2):** <container name>
```

## Examples

### QAS-01: Search latency under normal load

| Part        | Specification |
|-------------|---------------|
| Source      | Authenticated user |
| Stimulus    | Issues `GET /search?q=<terms>` |
| Environment | Normal operations: ≤100 concurrent users, dataset ≤10M documents |
| Artifact    | Search container |
| Response    | Returns top-10 ranked results |
| Measure     | p99 latency ≤ 300ms over a 5-minute window |

**Rationale:** Search is the primary user interaction; >300ms perceived as slow.

**Owner (Phase 2):** SearchService

### QAS-02: Recoverability after database restart

| Part        | Specification |
|-------------|---------------|
| Source      | Internal event (database failover) |
| Stimulus    | Primary database becomes unreachable |
| Environment | Normal traffic |
| Artifact    | API container, persistence layer |
| Response    | Failover to replica, retry queued writes |
| Measure     | Recovery to >95% capacity within 60 seconds; no data loss for committed writes |

**Rationale:** Database failover during business hours must not lose user data.

**Owner (Phase 2):** PersistenceAdapter + APIContainer (split responsibility)

### QAS-03: Authentication brute-force resistance

| Part        | Specification |
|-------------|---------------|
| Source      | Unauthenticated attacker |
| Stimulus    | Repeated login attempts with wrong password |
| Environment | Public internet, normal operations |
| Artifact    | Auth container |
| Response    | Rate-limit by IP and by username, lockout after N failures |
| Measure     | ≤5 attempts per minute per IP; ≤10 failed attempts per username per hour → 15-minute lockout |

**Rationale:** Most password attacks are online brute force; rate limiting is the primary defense.

**Owner (Phase 2):** AuthContainer (rate-limit logic), Gateway (IP-level enforcement)

## How many QASes?

Typical Phase 1 has 3-7 QASes. Fewer = under-specified. More = either over-engineered or the project genuinely has many quality dimensions (rare).

**Required coverage:**
- At least one performance QAS
- At least one availability OR reliability QAS
- At least one security QAS (or explicit justification "not security-critical")
- Cover any user-facing latency or throughput requirement explicitly

**Optional coverage:**
- Maintainability (e.g., "any module changes in <1 hour by a new developer with no prior context")
- Testability (e.g., "full test suite runs in <2 minutes")
- Observability (e.g., "any production error appears in dashboard within 30 seconds")
- Operability (e.g., "deploy takes <5 minutes from merge")

## Anti-patterns

- **Aspirational without measure**: "The system shall be fast." Not a QAS. What's "fast"?
- **Untestable**: "The system shall be maintainable." How do you test that? Rewrite: "A new dev can add a new entity type with <50 lines of code and <2 hours."
- **Solution disguised as requirement**: "The system shall use PostgreSQL." Not a QAS. That's a Phase 2 ADR.
- **Vendor-specific**: "Response time as per AWS SLAs." If you change cloud, you change the QAS — bad.
- **Aggregated**: "The system shall handle 1000 RPS with <100ms latency at 99.9% availability." Split this into 3 QASes; aggregated ones can't be tested independently.
