# Phase 0 — Discovery Critique Checklist

Apply during CRITIQUE step of Phase 0. For each item: PASS / FAIL / UNCERTAIN. For each FAIL, classify SCOPE-LOCAL (fix in brief) vs SCOPE-EXTERNAL (need user input).

This checklist focuses on **completeness of context**, not on design quality (design doesn't exist yet).

## Problem statement

- [ ] One paragraph exists that a non-technical reader could understand
- [ ] Problem is described from a user's POV, not a solution's POV
- [ ] No solution leaks into the problem statement ("we need a microservices-based event-driven system" is solution, not problem)
- [ ] User's actual words are preserved where they were strong; paraphrases noted

## Greenfield / brownfield

- [ ] Explicitly stated which one
- [ ] If brownfield: current system summarized in 1-3 sentences
- [ ] If brownfield: pain points or reasons for change are noted

## Stakeholders

- [ ] At least 3 stakeholder roles named (or explicit "single-user system" stated)
- [ ] Each stakeholder has one-line role description
- [ ] No "user" without qualifier (every system has multiple stakeholder types — even a personal tool has the user, their future self, possibly tax authorities, support contacts...)

## Constraints

- [ ] Hard constraints distinguished from preferences
- [ ] At least one of: deadline / budget / team size is stated (even if "no hard constraint")
- [ ] Regulatory or compliance constraints addressed (even if "none apply")
- [ ] Infrastructure constraints addressed if applicable (cloud, on-prem, must-run-offline, etc.)
- [ ] Language/stack preferences addressed if user mentioned them

## Quality attribute hints

- [ ] User's emphasis on quality dimensions is captured ("must be fast", "must never lose data", "must scale to X users")
- [ ] At least one quality attribute hint exists (if absent, that's itself a SCOPE-EXTERNAL flaw — ask the user)
- [ ] No quality attribute hint is solution-shaped ("must use Redis" is not quality, that's a guess at solution)

## Domain glossary

- [ ] Domain-specific terms identified (≥3 if domain is specialized, may be 0 for generic tools)
- [ ] Each term has at least a one-line definition from user's perspective
- [ ] No "duh" terms (don't define "user" or "database" — focus on domain-specific vocabulary)

## Known unknowns

- [ ] Open questions are explicitly listed (not glossed over)
- [ ] Each open question is specific (not "what about scale?" but "what's the expected concurrent user count at year 1, year 2, year 3?")
- [ ] No false-confidence: things the user actually doesn't know are not pretend-answered

## Risks

- [ ] At least one risk identified (even if "the only real risk is X" — name it)
- [ ] Each risk has one-line description + (optional) one-line mitigation idea
- [ ] Risks are non-obvious (not "the code might have bugs"); they're things specific to this problem

## Completeness for Phase 1 readiness

- [ ] Stakeholder model is sharp enough to write Phase 1 stakeholders section
- [ ] Quality hints are sharp enough to draft 3+ QASes
- [ ] Constraints are sharp enough to make Phase 2 tech choices reasonably
- [ ] No critical gap that would force Phase 1 to fabricate context

If any of these last four is FAIL, that's SCOPE-EXTERNAL: ask follow-up question(s).

## Karpathy pre-action checks (adapted for discovery)

- [ ] **Silent assumptions**: nothing implicit in user's request is assumed without surfacing it. If user said "build me a CRM", does "CRM" mean what you think it means? Ask.
- [ ] **Scope inflation**: you're not gold-plating the brief with capabilities the user didn't ask for. If user said "task tracker", brief shouldn't list "AI-powered prioritization" unless user asked.
- [ ] **Premature concreteness**: no architectural choice has been smuggled into the problem statement.

## Process checks

- [ ] No more than 12 questions asked in any single batch
- [ ] If user gave a terse or unclear answer, you re-asked (didn't paper over)
- [ ] If user explicitly skipped a question, it's marked as a known unknown, not pretend-answered
- [ ] Total Q&A turns ≤ 3 batches (otherwise: escalate to user "should we accept remaining gaps and move on?")

## Final pass

- [ ] Document length is 100-300 lines (outside this range = either too thin or you're doing Phase 1's job)
- [ ] Every section from `workflow/phase-0-discovery.md` is present
- [ ] No section says "TBD" without a corresponding known unknown
- [ ] If you handed this document to Phase 1, Phase 1 could produce a coherent system design from it
