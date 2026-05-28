# Phase 1 — System Design Critique Checklist

Apply during CRITIQUE step of Phase 1. For each item: PASS / FAIL / UNCERTAIN. For each FAIL, classify SCOPE-LOCAL vs SCOPE-EXTERNAL (Phase 1 has no upstream).

## Vision and scope

- [ ] System vision is one paragraph, plain English, no jargon
- [ ] Vision states WHO uses the system and WHY (value, not features)
- [ ] Stakeholders section names ≥3 distinct stakeholder types
- [ ] Each stakeholder has a one-line description of role
- [ ] "Out of scope" section exists and has ≥3 specific items
- [ ] Scope and out-of-scope are mutually exclusive (no item appears as both edge case and out-of-scope)

## Functional capabilities

- [ ] Capabilities are described as user-visible outcomes, not implementation
- [ ] Capabilities list is between 5 and 30 items (outside this range = suspicious)
- [ ] No capability mentions a specific technology, library, or framework
- [ ] Each capability could be tested by a non-technical stakeholder

## Quality Attribute Scenarios

- [ ] At least 3 QASes are present
- [ ] Each QAS follows the QAS structure (source, stimulus, environment, artifact, response, measure)
- [ ] Each QAS has a measurable response metric (not "fast" but "≤200ms p99")
- [ ] QASes cover at least: performance, reliability, security (or explicit "not security-critical" justification)
- [ ] QASes are achievable given Phase 1 constraints (no "99.99% uptime by a solo developer" type contradictions)

## Constraints

- [ ] Hard constraints are distinguished from preferences ("must run on AWS" vs "prefer AWS")
- [ ] Team size and skills are mentioned (architecture depends on them)
- [ ] Budget/cost constraint is mentioned (even if "no hard budget", say so explicitly)
- [ ] Deadline constraint is mentioned (even if "no hard deadline", say so explicitly)
- [ ] Regulatory/compliance constraints are mentioned (or explicit "none apply")

## User journeys

- [ ] At least 3 user journeys exist
- [ ] Each journey is told from user's perspective ("user does X → sees Y")
- [ ] Journeys cover both happy path and 1-2 explicit failure cases
- [ ] No journey assumes a specific UI implementation (web vs mobile vs CLI is a Phase 2 decision unless constrained)
- [ ] Each journey can be traced to at least one functional capability

## Karpathy pre-action checks

These come from the `karpathy-pre-action-check` skill. Apply explicitly even if skill is not installed.

- [ ] **Silent assumptions**: every implicit assumption is surfaced. "The user will know their email" vs "the user provides their email" — be explicit.
- [ ] **Over-complication**: no requirement is more elaborate than the user asked for. If they wanted a CRUD app and you wrote 20 QASes, you're over-scoping.
- [ ] **Unrequested scope**: nothing in the system design wasn't asked for. If you added "analytics dashboard" because it seemed nice, remove or tag for user approval.

## Open questions

- [ ] All open questions are blocking (would change Phase 2 decisions)
- [ ] No open question is actually a Phase 1 decision in disguise (you're delegating to user what you should have decided)
- [ ] Each open question has at least one default answer proposed

## Final pass

- [ ] Document length is 200-600 lines (outside this range = either over-engineered or under-specified)
- [ ] Every section from `workflow/phase-1-system.md` is present
- [ ] No section says "TBD" without a corresponding open question
- [ ] If you handed this document to a different architect, they could plausibly produce a coherent Phase 2 from it
