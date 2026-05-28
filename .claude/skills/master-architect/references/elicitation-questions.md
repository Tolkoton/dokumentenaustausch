# Elicitation Questions for Phase 0

Master-architect uses this set during Phase 0 GENERATE step. Don't ask all of them — adapt based on signals (see workflow/phase-0-discovery.md for question budget heuristic).

Questions are grouped by category. The marker `[g]` indicates greenfield-relevant, `[b]` brownfield-relevant, `[both]` applies to both.

## Problem and value (always ask 1-2)

1. `[both]` What problem are you trying to solve, in one or two sentences from the user's point of view? (Not "build a system that does X" — what does the user have trouble with today?)

2. `[both]` Why is this worth doing now? What changes if it works? What if you don't build it?

3. `[both]` Is there a non-software solution that could solve this? (Useful for scope-checking — if yes, what makes the software approach better?)

## Stakeholders and users (always ask 2-3)

4. `[both]` Who are the primary users — 2 to 4 specific personas or roles? For each, what do they care about most?

5. `[both]` Who else is affected (besides the primary users)? Think: administrators, customer-facing staff, integrators, auditors, future maintainers.

6. `[both]` Is there a difference between who pays for this and who uses it? (Customer vs user distinction often hides constraint signals.)

## Functional shape (always ask 2-3)

7. `[both]` What are the 3-5 most important things users do with the system? Describe in user terms ("user does X" / "user sees Y"), not system terms.

8. `[both]` What is explicitly NOT in scope? Things adjacent to the problem that you're choosing not to handle, at least initially.

9. `[both]` If I built only one feature first, which one would deliver the most value? (This is a Phase 4 hint — vertical slice priority.)

## Quality emphasis (always ask 2-3)

10. `[both]` What must absolutely never go wrong? (Reveals critical NFRs: data loss, downtime windows, security, privacy.)

11. `[both]` What latency/responsiveness expectations do users have? Concrete numbers if possible (e.g., "response in under 1 second", "batch overnight is fine").

12. `[both]` What scale do you expect on day 1, in year 1, in year 3? Approximate is fine. Users, requests, data volume, integrations.

## Constraints (always ask 2-3)

13. `[both]` What's the team building this? Headcount, skill mix (Python? JS? cloud?), part-time/full-time.

14. `[both]` Hard deadline or budget constraint? Date or amount or both, even if "no hard deadline" is the answer.

15. `[both]` Any infrastructure or platform constraints? (Must run on Y cloud, must be on-prem, must run offline, must support browser X.)

16. `[both]` Any regulatory or compliance constraints? GDPR, HIPAA, SOC2, PCI, financial reporting, etc.

17. `[both]` Are there preferences for technology that you'd like respected? (Pre-existing skills, organizational standards, ecosystem fit.)

## Existing context (brownfield)

18. `[b]` What exists today? One-paragraph description of the current system.

19. `[b]` What works well today that we should preserve?

20. `[b]` What doesn't work — specific pain points, not vague complaints. Examples in user terms.

21. `[b]` What integrations are non-negotiable (existing data sources, downstream consumers)?

22. `[b]` Are we replacing the current system or extending it? If replacing: cutover strategy preferences?

## Risks and worries (always ask 1-2)

23. `[both]` What keeps you up at night about this project? Specific worries, even if they seem irrational.

24. `[both]` Have you tried this before (or seen others try)? What went wrong?

25. `[both]` What's the most likely reason this project would fail in 6 months? (Premortem question.)

## Definition of done (Phase 1 hint)

26. `[both]` How would you know this project succeeded? Specific signals — adoption numbers, metric improvements, user feedback, time saved.

27. `[both]` What's the smallest version that would make a difference to a user? (Hint at MVP scope.)

## Domain language

28. `[both]` What domain terms do you and your stakeholders use that someone outside your domain might not understand? (Glossary seeds.)

## Branching logic

After initial answers, ask follow-ups based on:

- **If user says "real-time" or mentions latency under 100ms** → drill into specific QAS (what does real-time mean? what's the response budget? what's the failure mode if missed?)
- **If user mentions "secure"** → drill into threat model (who's the adversary? what data is sensitive? regulatory requirements?)
- **If user mentions "scale"** → numbers (current, projected, peak vs sustained)
- **If user mentions multiple integrations** → which are read-only, which write? Synchronous or async? What happens if they're down?
- **If user is fuzzy on users** → "imagine the very first user. Who are they? How did they find this thing? What were they trying to do?"
- **If user has no constraints answer** → "what would have to change about the world for this project to not be worth doing?" (often reveals hidden constraint)

## Question budgeting (recap from workflow)

- Lightweight: 5-7 questions (pick from sections "Problem and value", "Stakeholders", "Quality emphasis", "Constraints")
- Standard: 8-12 questions (add "Functional shape", maybe "Risks", maybe "Definition of done")
- Deep: 12-18 questions (most categories covered, plus targeted follow-ups)

Don't exceed 12 in one batch. If you need more, do batch 2 after user answers batch 1.

## What NEVER to ask in Phase 0

These belong in later phases:

- "What database should we use?" — Phase 2
- "Should this be microservices?" — Phase 2 (master-architect decides per anti-patterns.md)
- "What's the folder structure?" — Phase 3
- "How would we test this?" — Phase 2 (testability) / Phase 4 (specific tests)

If user asks these, defer politely and note in known unknowns.
