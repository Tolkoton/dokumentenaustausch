# ADR Template

When master-architect generates an ADR (during Phase 2), use this structure. Save under `.architecture/adrs/<NNN>-<slug>.md` or inline in `phase-2-architecture.md`.

```markdown
# ADR-<NNN>: <Short decision title>

## Status

<DRAFT | PROPOSED | ACCEPTED | DEPRECATED | SUPERSEDED by ADR-<NNN>>

Date: YYYY-MM-DD

## Context

What is the problem? What constraints apply? What forces are in play?

Reference the Phase 1 QASes or constraints that drive this decision.

This section is 1-3 paragraphs. If you can't write the context, you don't understand the decision.

## Decision

We will <do specific thing>.

One sentence. Then a paragraph elaborating *what* the decision actually means concretely.

## Alternatives considered

For each plausible alternative:

### Alternative A: <name>

- What it would mean
- Why it was rejected (ideally: which QAS/constraint it violates)

### Alternative B: <name>

- ...

If no alternative was seriously considered, write that explicitly: "No alternative was considered because <reason>". This is sometimes valid (e.g., "We use Python because the team only knows Python") but should be conscious.

## Consequences

Both positive and negative.

### Positive

- ...

### Negative

- ... (these are the prices we agree to pay)

### Neutral / interesting

- ... (effects that aren't clearly +/− but matter)

## Implementation notes (optional)

If the decision has a clear how-to attached, brief bullets here.

## References (optional)

- Links to relevant docs, RFCs, papers, prior ADRs

---

When to write an ADR
=====================
Yes:
  - Choice between substantially different alternatives
  - Choice that's expensive to reverse (database engine, language, auth provider, deployment platform)
  - Choice that affects multiple containers
  - Choice that defines a contract others will rely on

No:
  - Within-ecosystem library choices (e.g., "use FastAPI" when Python web is given)
  - Naming conventions (Phase 3 concern, not Phase 2)
  - Implementation details
  - Trivially reversible decisions
```

## Numbering

Use zero-padded 3-digit numbers: `ADR-001`, `ADR-002`, ...

If an ADR is superseded by another, mark the original as `SUPERSEDED by ADR-<NNN>` and reference back from the new one. Never delete ADRs.

## Multiple-file vs inline

For Phase 2 documents with ≤5 ADRs, inline them in `phase-2-architecture.md`. For more, use a separate `.architecture/adrs/` folder with one file per ADR. The choice is a judgment call.
