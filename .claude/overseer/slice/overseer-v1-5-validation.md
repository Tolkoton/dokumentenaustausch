# Slice overseer-v1-5-validation — planning artifact

## Goal

V1.5 of the overseer added a planning-mode surface — the `/plan-slice <slug>` command and the `.claude/overseer/slice/<slug>.md` contract — meant to make pre-implementation planning artifact-based rather than chat-only. This slice validates whether v1.5 has TEETH: whether the planning conversation it drives produces real friction (overseer→user revisions that yield) rather than ceremony, and whether the resulting artifact survives external review.

The validation is meta — the planning conversation that produced THIS artifact is the test subject; this artifact is both the evidence and the verdict surface. Two distinct rigor surfaces are measured: (i) planning-conversation rigor (in-session evidence: artifact structure + Revisions trail) and (ii) artifact-quality rigor (external evidence: fresh-session cold-reader audit + failure-injection control). The slice passes only when BOTH gates pass.

## Out of scope (deliberate)

- Iterating on `.claude/skills/overseer/SKILL.md` or `.claude/settings.json` mid-session in response to validation findings. Observations get noted (e.g., the SKILL.md ↔ /plan-slice vocabulary gap surfaced in Phase 4); edits are a separate slice.
- Planning the real next slice (`resolver-perf`, the blocked successor to slice 4b) on this same pass. Cognitive contamination risk; resolver-perf gets its own /plan-slice cycle.
- Committing v1.5 to git before this validation passes (no premature `git add` of SKILL.md / settings.json / command changes).
- Drafting any ADR even if a decision smells ADR-worthy during the planning conversation — owner ratifies first; overseer does not unilaterally draft ADRs.

## Decisions (with WHY)

- **D1 — Failure mode when (c′) lands zero material entries by Phase 5 end.** Chosen: write artifact normally + `VALIDATION_FAILED` banner at the top + ledger entry `PLANNING_INCOMPLETE`. Rejected: refuse to write artifact entirely (loses partial work — decisions/seams/exit-criterion that DID land become unrecoverable); ledger-only without banner (two sources of truth that disagree is worse than one source with a loud banner).
- **D2 — Whose pushback counts toward (c′).** Chosen: only overseer→user revisions. Rejected: also count user→overseer (that's normal collaboration like the v15→v1-5 rename, not the friction-test we're validating; bidirectional counting dilutes the bite measurement); any-direction material-only (abstracts away the load-bearing direction distinction).
- **D3 — Failure on (c′) blocks slice vs partial-record.** Chosen: partial-pass (record `PLANNING_INCOMPLETE`, allow slice to enter implementation with banner remaining on artifact). Rejected: hard-gate implementation on meta-validation (decision conflation per check #3 — meta-validation success is independent of implementation-readiness; could create starvation on hard slices); validation-result-informational-only (toothless; banner + ledger entry need visible consequences).
- **D4 — Revisions trail lifetime.** Chosen: trail survives in artifact forever (immutable history). Rejected: pruned at slice-DONE (destroys the audit artifact built; future-me trying to understand decision evolution loses the WHY chain); kept-but-marked-inactive (adds complexity without clear benefit).
- **D5 — `## Revisions during planning` section placement.** Chosen: bottom-of-structural-sections (after Open Items, before audit/watching sections). Rejected: top (crowds Goal/Decisions on first read; implementation-phase overseer should see decisions/seams first, not historical revisions); interleaved per-phase (scatters audit trail; harder to reconstruct holistically).
- **D6 — Quote fidelity in Revisions entries.** Chosen: verbatim with `[…]` for shortening, no paraphrasing. Rejected: paraphrase allowed (invites revisionism creep — future-me softens the original challenge text; auditability breaks).
- **E (E-ii) — Defended pushbacks visibility.** Chosen: add sibling section `## Defended pushbacks during planning` recording challenges that landed but didn't yield revision; does NOT count toward (c′); makes "user-unmoved" vs "overseer-toothless" distinguishable to auditors. Rejected: accept invisibility (loses audit info with independent value); amend (c′) to also count defended (dilutes harder-bar intent of measuring yielded friction).
- **F-G — Cold-reader spawn protocol.** Chosen: pin spawn prompt verbatim AND record actual prompt used (G-i + G-iii). Rejected: multiple-framing spawns G-ii (cost-benefit unfavorable vs failure-injection which provides framing-sensitivity signal cheaper); defend G-original (leaves the audit's single point of compromise — owner can subtly bias verdict via spawn framing, cold-reader-equivalent of leading a witness).
- **H1 — DISAGREE verdict routing.** Chosen: `DISAGREE_ADDRESSABLE` (owner ratifies amendments per SKILL.md §"What you do NOT do"; artifact amended; Gate 2 re-runs; day-counter resets to 7; anti-loop bound 3 iterations then terminate as `VALIDATION_DISPUTED`) and `DISAGREE_OWNER_JUDGMENT` (terminal, recorded as `VALIDATION_DISPUTED`, V1.6 data point). Rejected: leaving DISAGREE unrouted (creates undefined absorbing state — exactly what (g) was designed to prevent).
- **H2 — Downstream slice impact on post-hoc Gate 2 failure.** Chosen: implementation slice's `PROGRESS.md` entry receives `PARENT_PLANNING_FAILED` tag with hyperlink to this artifact; does not block implementation closure; visible in history; implementation-phase overseer treats tag as Open Item input. Rejected: silent (post-hoc failure leaves no trace in dependent slices); block downstream closure (over-couples meta-validation to implementation completion).
- **J (J-i) — Watching as fifth category.** Chosen: add `## Watching (standing concerns)` for items with observable positive triggers but no obligated negative timeframe. D-iv moved here as W-i. Rejected: J-ii force watching items to arbitrary negative bounds (check #6 trap — "why 12 months not 18, no principled answer"); J-iii erode trigger-condition spec retroactively (smuggle pattern — weakening the spec the Phase-5 open accepted).

## Hardest seams (with test approach)

- **Seam 1: Validator-as-subject (the meta-seam).** The overseer is the entity being validated AND the entity producing the evidence of validation. If overseer is sycophantic, every gate (Decisions quality, Seams concreteness, Revisions count) reads clean for the wrong reason. Anti-pattern named: **"validator-as-subject"** — entity being validated is also doing the validation. **Test: cold-reader audit + failure-injection control.** A fresh Claude Code session with no inherited context applies the 12-check audit to this artifact + SKILL.md, within 7 days of Gate 1 pass (by 2026-05-27). Failure-injection control: hand-construct one counterfactual artifact (`.claude/overseer/slice/overseer-v1-5-validation.counterfactual.md` per O-i) with deliberately shallow content (strawman alts, vague seams, padded Revisions); submit both real and counterfactual to cold-reader; if cold-reader can't distinguish them, the audit mechanism itself is broken. Spawn prompt pinned verbatim (see D F-G). Cold-reader's verdict is authoritative; in-session pre-checks lose on disagreement.

- **Seam 2: Rule-lawyering revisions inflate (c′).** Anti-pattern named: **"rule-lawyering material"** — entries satisfy the letter of "changes a decision/alternative/seam/exit criterion" while representing no substantive shift (e.g., typo fix to a rationale technically "changes a decision"). **Test: implementer-difference audit at slice closure.** Before artifact write, overseer re-reads each Revisions entry and asks "would the next slice's implementer or a future planner using this as template do anything differently because of the `<before>→<after>` shift?" Entries failing the test are retained (audit-honest; deletion would be revisionism) but tagged `(non-material per audit)` and do NOT count toward (c′)'s ≥1 gate. In-session audit is a pre-check; cold-reader (Seam 1) is authoritative — if cold-reader disagrees with in-session material tagging, cold-reader wins and (c′) re-evaluates per (g).

- **Seam 3: Strawman alternatives in Decisions.** Anti-pattern named: **"strawman alternative"** — alt B is an obviously-wrong option, surfaced only to satisfy the ≥2-alternatives quota; symptom is *categorical* rejection rationale ("rejected because obviously wrong") rather than *substantive* ("rejected because under condition X this approach has known failure mode Y"). **Test: substantive-tradeoff filter (in-session) + cold-reader plausibility test (external).** In-session: overseer pushes back on any decision whose rejected alternatives use categorical rather than substantive rationale (this seam empirically bit this session — D1-D4 scrutiny, then D5-D6 scrutiny, then J resolution). Cold-reader plausibility: reviewer reads each Decision's alternatives with the chosen option masked; if every rejected alt looks self-evidently absurd to a fresh reader, alts are strawmen.

## Exit criterion

**Gate 1 — In-session pass (necessary, not sufficient):**

- **(a) Artifact existence + 11 sections populated.** `.claude/overseer/slice/overseer-v1-5-validation.md` exists with all 11 sections (Goal, OOS, Decisions, Hardest seams, Exit criterion, Deferred, Open items, Revisions during planning, Defended pushbacks during planning, External audit results, Watching). Sharpened "non-empty" predicate: each section contains ≥1 declarative sentence specific to THIS slice with ≥1 concrete noun (slug name, decision label, seam name, deadline, file path). "TBD" / cross-reference stubs do NOT satisfy. Cold-reader-testable: fresh reader identifies the slice from any single section's content alone.
- **(b) Ledger entry at `.claude/overseer/ledger.md`.** Uses /plan-slice command vocabulary (`PLANNING_COMPLETE_PENDING_AUDIT` initially, transitioning per (f)/(g)). SKILL.md verdict vocabulary (PASS/BLOCK/ADR_REQUIRED/ESCALATE) applies to overseer-on-developer-turn invocations, NOT to /plan-slice closure. The vocabulary gap between the two surfaces is captured as D-i Deferred and O-v Open Item.
- **(c′) `## Revisions during planning` contains ≥1 entry surviving Seam 2's implementer-difference audit untagged as non-material.** Layering explicit: in-session audit is pre-check; cold-reader (Gate 2) is authoritative. Cold-reader disagreement flips entry tagging; if surviving count drops to 0, (c′) retroactively fails per (g).

**Gate 2 — Cold-reader (authoritative):**

- **(d) Cold-reader audit within 7 days of Gate 1 pass (by 2026-05-27).** Fresh Claude Code session with no inherited context. Spawn prompt MUST be verbatim:

  > Apply the overseer 12-check audit (.claude/skills/overseer/SKILL.md) to the planning artifact at .claude/overseer/slice/overseer-v1-5-validation.md. Report verdict and reasoning per SKILL.md output structure. No additional framing.

  Verbatim prompt used + verdict (`PASS` / `FAIL` / `DISAGREE_ON_SPECIFIC_ITEMS`-with-list) + ISO timestamp + session ID + ≤200-word reasoning summary recorded under `## External audit results`. Any deviation from canonical spawn prompt flags audit `INVALID-DUE-TO-FRAMING`; owner re-spawns with canonical prompt before verdict counts.
- **(e) Failure-injection control alongside (d).** Hand-construct counterfactual artifact at path per O-i with deliberately shallow content. Submit both real and counterfactual to cold-reader (same session OR separate, owner picks). Distinguishability result recorded alongside (d): "Counterfactual distinguishable: YES / NO" with ≤100-word reasoning.

**(f) State transitions — kills #1 false-DONE and #2 in-session/external conflation:**

- Gate 1 PASS alone → `PLANNING_COMPLETE_PENDING_AUDIT`. Artifact written, ledger recorded, slice ALLOWED into implementation but status is NOT terminal.
- Gate 1 + Gate 2 both PASS → `PLANNING_COMPLETE_VERIFIED`. Terminal success.
- Gate 1 PASS + Gate 2 FAIL → routes through (g).
- Gate 1 FAIL → `PLANNING_INCOMPLETE`, terminal. Slice does NOT enter implementation; re-plan required.

**(g) UNVERIFIED reconciliation — no absorbing states:**

- Gate 2 FAIL, owner accepts cold-reader → `VALIDATION_FAILED`, terminal partial. In-flight implementation continues with `PARENT_PLANNING_FAILED` tag per H2; cold-reader's criticisms become Open Items for next slice or V1.6 audit work.
- Gate 2 FAIL, owner rejects cold-reader → `VALIDATION_DISPUTED`, terminal. Both verdicts recorded with owner reasoning. V1.6 data point.
- Gate 2 returns `DISAGREE_ON_SPECIFIC_ITEMS`, owner classifies items as addressable in-artifact → `DISAGREE_ADDRESSABLE`. Owner ratifies amendments; artifact amended; Gate 2 re-runs on revised artifact; day-counter resets to 7. Anti-loop bound: 3 iterations, then owner terminates as `VALIDATION_DISPUTED`.
- Gate 2 returns `DISAGREE_ON_SPECIFIC_ITEMS`, owner classifies items as judgment-calls → `VALIDATION_DISPUTED`, terminal.
- Gate 2 never runs within 7 days → `VALIDATION_LAPSED` at day 8. ONE re-trigger allowed (resets 7-day timer); after exhausted, LAPSED is terminal. Owner decides re-trigger vs accept-lapsed.
- No transitions BACK to `PLANNING_COMPLETE_VERIFIED` except via fresh Gate 2 PASS.

## Deferred to later slices

- **D-i — SKILL.md verdict vocabulary ↔ /plan-slice command vocabulary unification.** Trigger: first real implementation slice closure where cold-reader auditor or future-me asks "which verdict vocabulary applies here?" or misinterprets one as the other. Negative bound: 3 implementation slices close cleanly without vocab-induced confusion → Drop (gap harmless in practice). Bounded: 3 slices OR 90 days, whichever first.
- **D-ii — `.claude/overseer/slice/_template.md` (6 sections) ↔ canonical /plan-slice output (11 sections, this artifact) reconciliation.** Trigger: owner uses `_template.md` manually (without /plan-slice) for a real slice AND resulting artifact fails cold-reader audit on count/structure mismatch. Negative bound: 60 days pass with `_template.md` unused for any real slice → Drop template as unused (different problem: the template isn't earning its place). Bounded: 60 days OR first manual-template use.
- **D-iii — Open Items as ADR-escape-hatch (general V1.5 weakness to monitor).** Trigger: 2 implementation slices surface Open Items entries that should have been ADR-worthy per SKILL.md #8 — pattern detected via cold-reader verdicts ("this should be an ADR draft, not an Open Item"). Negative bound: 5 implementation slices close with no such pattern → Drop (theoretical concern only). Bounded: 5 slices OR 90 days.

## Open items requiring human decision

- **O-i — Counterfactual artifact storage location (precondition for Seam 1 (e)).** Recommendation: `.claude/overseer/slice/overseer-v1-5-validation.counterfactual.md` — sibling file, version-controlled, easy to locate at Gate 2 audit time. Owner ratifies before Seam 1 (e) can run.
- **O-ii — Cold-reader audit initiation procedure.** Recommendation: manual — owner spawns new Claude Code session with canonical spawn prompt from (d). Could automate later (cron-like reminder); not for this slice.
- **O-iii — Anti-loop bound for `DISAGREE_ADDRESSABLE` iterations.** Set to 3 per H1. Owner ratifies 3 or counters with a different cap.
- **O-iv — V1.6 trigger conditions.** Without this, every "deferred to V1.6" reference is unbounded. Recommendation: V1.6 work formally starts when ANY of: (i) 5 V1.6-tagged items accumulate across Deferred/Watching without being Dropped; (ii) 30 days of v1.5 in real use elapse from this slice's `PLANNING_COMPLETE_VERIFIED` status; (iii) one severe weakness surfaces in a real implementation slice. "Severe" needs owner definition at ratification — flagged pre-ratify as check #6 (soft verdict on hard data) territory.
- **O-v — Template ↔ canonical-command section-count mismatch.** `.claude/overseer/slice/_template.md` has 6 sections (OOS + Deferred merged); this artifact has 11 (separated). Resolve in follow-up: either update template to match command, or relax artifact spec. Not blocking this validation. Owner decision (also captured as D-ii Deferred with trigger; O-v is the immediate ratification fork, D-ii is the time-bounded promotion).

## Revisions during planning

Format: **Phase N — challenge:** "<verbatim quote from overseer, `[…]` for cuts>" **→ revised:** "<before>" to "<after>" **→ reason:** <material reason>. All quotes verbatim per D6.

- **#1 Phase 1 — challenge:** *"(c) is Goodhartable by both of us; I can satisfy it by manufacturing a token challenge, you can satisfy it by a token revision; the metric measures process not output […] (c′) Auditable revision trail […] makes it falsifiable from the artifact alone — no need to trust either of our self-reports"* **→ revised:** exit criterion (c) from `"at least one Overseer pushback during Phases 2-5 caused me to revise an answer"` to `"Auditable revision trail — artifact MUST contain '## Revisions during planning' section with ≥1 entry of form Phase N — challenge: '<quote>' → revised: '<before>' to '<after>' → reason: <material reason>; zero entries by end of Phase 5 = validation fails on (c), recorded as such in the ledger"` **→ reason:** material — turned a process-only Goodhartable metric into a falsifiable artifact-side check; surface of the exit criterion changed.
  - **Implementer-difference audit:** PASS (material). A planner using before-version would build a looser artifact without dedicated Revisions section + entry format.

- **#2 Phase 2 — challenge:** *"D2 says only overseer→user revisions count […] friction without yield = invisible […] a stubborn user can absorb three sharp overseer challenges, defend each, and end Phase 5 with zero entries → validation fails on (c′) even though the overseer DID bite. The signal would say 'overseer toothless' when it actually was 'user unmoved.'"* **→ revised:** artifact structure from 7 sections to 8, adding `## Defended pushbacks during planning` (per E-ii) recording challenges that landed without yielding revision; entries don't count toward (c′) but make user-unmoved vs overseer-toothless distinguishable. **→ reason:** material — adds artifact section with distinct entry format and audit semantics.
  - **Implementer-difference audit:** PASS (material). Before-version would lose the ability to distinguish two failure modes.

- **#3 Phase 2 — challenge:** *"You named D1–D4 […] None about its structural placement and content rules. Two sub-decisions that bite: D5: Section placement […] D6: Quote fidelity […] verbatim is strict and auditable but […] paraphrased […] lets revisionism creep in"* **→ revised:** D5 (placement) decided as bottom-of-structural-sections (was undecided); D6 (quote fidelity) decided as verbatim with `[…]` for shortening, no paraphrase (was undecided). **→ reason:** material — placement affects implementation-phase overseer's first-read surface; verbatim vs paraphrase is the difference between auditable and "I think I remember."
  - **Implementer-difference audit:** PASS (material). Before-version could place Revisions at top (crowding decisions on first read) and/or paraphrase quotes (eroding auditability).

- **#4 Phase 4 — challenge (self-audit by user, pre-empting an implicit overseer challenge):** *"Catch upfront — material revision to (a): Phase 1 set 'all 7 sections non-empty.' Phase 2 added Revisions during planning (D5) and Defended pushbacks (E-ii). Phase 4 adds External audit results (bolt-on). Current count: 10 sections, not 7."* **→ revised:** (a) gate surface from `"all 7 sections non-empty"` to `"all 10 sections non-empty"` (subsequently `"all 11 sections non-empty"` after Revision #6). **→ reason:** material — gate surface changed by 3+ sections; without this catch, (a)'s predicate would have been silently wrong post-write.
  - **Implementer-difference audit:** PASS (material). Before-version of (a) would have allowed a 7-section artifact to claim Gate 1 pass while missing 3 required sections. **Provenance note:** revision originated from user self-audit, not directly from an overseer challenge in the immediately preceding turn. Counted because the user's "Catch upfront" framing pre-empted the implicit overseer challenge "the structure has drifted, name it" that would have fired in my Phase 4 response if user hadn't surfaced it first. Borderline-but-counted; flagging for cold-reader to verify the overseer→user provenance holds.

- **#5 Phase 4 — challenge:** *"Cold-reader spawn protocol is unspecified, and that's the audit's single point of compromise […] Fresh session ≠ neutral context. The initial prompt to that session IS context, and it's owner-controlled. Subtle framing […] will shift verdict probability before the model has read a single byte of the artifact […] cold-reader-equivalent of leading a witness"* AND *"State machine has two gaps […] H1: Hybrid verdict (DISAGREE_ON_SPECIFIC_ITEMS) lacks routing […] H2: Downstream implementation slice impact when Gate 2 fails post-hoc"* **→ revised:** (d) pinned spawn prompt verbatim with `INVALID-DUE-TO-FRAMING` fallback; (g) added `DISAGREE_ADDRESSABLE` (3-iteration cap → `VALIDATION_DISPUTED`) and `DISAGREE_OWNER_JUDGMENT` routes; H2 added `PARENT_PLANNING_FAILED` downstream tag. **→ reason:** material — closed an audit-integrity hole (spawn-prompt framing bias) + an undefined absorbing state (DISAGREE verdict) + an invisible downstream impact (post-hoc Gate-2 failure visibility).
  - **Implementer-difference audit:** PASS (material). Before-version had three concrete operational gaps: cold-readers biasable at spawn, DISAGREE verdicts unrouted, downstream slices blind to parent failure.

- **#6 Phase 5 — challenge:** *"D-iv violates the rule you accepted […] 'Indefinite' IS the unfalsifiable-negative pattern, dressed up […] D-iv has no negative timeframe […] (J-i) Add a fifth category: Watching. Standing concerns with positive triggers but no obligated negative. D-iv moves there. Honest categorization."* **→ revised:** taxonomy from 4 categories (OOS / Deferred / Open Items / Dropped) to 5 (added Watching); D-iv moved to W-i; (a) gate surface from 10 to 11 sections; X-vii removed from Dropped (was a labeling error referencing nonexistent "D3c"). **→ reason:** material — taxonomy change affects how future planners categorize items; without Watching, items either get force-fit to Deferred (with unfalsifiable negatives like D-iv was) or to Dropped (losing standing-watch signal); (a) gate surface also changed.
  - **Implementer-difference audit:** PASS (material). Before-version would either force watching items to invent arbitrary negative bounds (check #6 trap) or lose them entirely.

**Implementer-difference audit summary:** 6 entries reviewed at write-time, **6 surviving as material**, 0 tagged `(non-material per audit)`. (c′) gate passes with margin. Cold-reader audit (Seam 1) retains authority to flip any of these tags on Gate 2 review; if all 6 were to flip to non-material at Gate 2, (c′) would retroactively fail per (g).

## Defended pushbacks during planning

Format: **Phase N — challenge:** "<verbatim quote>" **→ defense:** "<rationale for not revising>" **→ reason:** <why this didn't yield a revision>.

Across Phases 1-5, every overseer pushback that landed substantively resulted in user revision. **Zero defended-pushback entries logged.** This is itself signal — either (a) overseer pushbacks landed substantively and user yielded honestly, or (b) overseer pushbacks were soft enough that no defense was needed (sycophancy risk). The cold-reader audit (Seam 1) is the external check that distinguishes (a) from (b): if Seam 3's substantive-tradeoff filter and Seam 1's failure-injection control both PASS at Gate 2, signal points to (a). If cold-reader flags any in-session pushback as insubstantial, signal flips toward (b) and this empty section becomes evidence of a soft conversation rather than a rigorous one. The emptiness is auditable, not papered over.

## External audit results

**Gate 2 (cold-reader audit) pending.** Expected by **2026-05-27** (Gate 1 close 2026-05-20 + 7 days). This section is reserved for:

- Verbatim spawn prompt actually used (compared to canonical in (d); any deviation flags `INVALID-DUE-TO-FRAMING`).
- Cold-reader verdict: `PASS` / `FAIL` / `DISAGREE_ON_SPECIFIC_ITEMS`-with-list.
- ISO timestamp + Claude Code session ID of the cold-reader run.
- ≤200-word reasoning summary from cold-reader.
- Failure-injection control result: "Counterfactual distinguishable: YES / NO" with ≤100-word reasoning.

**Current status as of artifact write (2026-05-20T15:33:55Z):** `PLANNING_COMPLETE_PENDING_AUDIT`.

## Watching (standing concerns)

Format: **W-N. Concern.** Watch for: <observable signal>. Action if trigger fires: <next step>. *No negative bound — dormant by design if signal never appears.*

- **W-i — Cold-reader audit cross-model behavior.** Watch for: cold-reader verdict on the same artifact diverging across model versions (e.g., Opus 4.7 PASS → Opus 5.x FAIL, or vice versa) by a margin that affects status. Action if trigger fires: re-evaluate whether the cold-reader audit mechanism is model-resilient or the artifact spec needs hardening (e.g., narrower predicate definitions, structural fingerprinting, multi-model quorum). No negative bound — divergence may never appear and that's acceptable. Distinct from Deferred (which obligates Drop on negative timeout); originally categorized as Deferred D-iv before Revision #6 corrected the category.
