# Slice magic-link-ui — planning artifact

Planning conversation: 2026-05-26. Five phases, all ratified by owner.
Ledger: `.overseer/ledger.md` entry at this date.

## Goal

**Primary (the user-visible bug fix):** The Mandant at `/r/{token}`
currently sees the **raw wire format** of `_request_letter_<ISO>.txt` —
including `==BELEGMEISTER== request/v1`, `To:`/`Cc:`/`Subject:` header
lines, and `==BELEGMEISTER== fragen`/`end` sentinels — inside a `<pre>`
block (Phase 0 P6, verified at `src/belegmeister/web/templates/request.html:16`).
This slice replaces that raw render with a **parsed render**: parse the
letter via `belegmeister.request_format.parse_request_letter` (single
source of truth, codec-with-round-trip), and render the parsed fields:
`subject` in the page `<h1>`, `body` in a proportional
`<div class="whitespace-pre-wrap">`, and `questions: tuple[str, ...]` as
per-question text inputs named `answer_<0-based-index>`.

**Secondary (visual alignment follow-on):** Four concrete edits between
`web/templates/{request,invalid}.html` and `sb/templates/{form,result}.html`
— Tailwind CDN + slate palette + container shape are *already* aligned
(Phase 0 P4 corrected the brief's "predates Tailwind" framing); only
small surfacing details remain. See **Decisions § P1.1** for the four
items.

The two-part goal is *deliberately asymmetric*: primary is load-bearing
(the wire-format leak is a real bug); secondary is cosmetic follow-on
that ships in the same slice because the same files are touched.

## Premise verified (Phase 0)

This slice introduces no new external system. All load-bearing premises
were verified in-tree on 2026-05-26:

| # | Assumption | Evidence | Status |
|---|---|---|---|
| **P1** | `parse_request_letter` returns `RequestLetter(to, cc, subject, body, questions: tuple[str, ...])`; round-trip codec is the single source of truth | `src/belegmeister/request_format.py:80-92, 350-423` | ✅ |
| **P2** | SB uses Tailwind CDN + `slate-*` palette + `max-w-2xl mx-auto bg-white rounded-xl shadow p-8` container + button class `bg-slate-800 text-white px-5 py-2 rounded hover:bg-slate-700` | `sb/templates/form.html:7-10,109-112`, `sb/templates/result.html:7-10,28-30` | ✅ |
| **P3** | RT1 form-attribute pin test exists and will catch regressions | `tests/web/test_app_route.py:82-85` | ✅ |
| **P4** | "Slice 3 `request.html` predates 4b's Tailwind styling" framing | **Brief was wrong.** `request.html:7` already loads Tailwind, uses slate palette, uses same container. Gap is smaller than originally stated. | ⚠ corrected |
| **P5** | 4a did not touch `web/templates/request.html` | `git log` confirms last touch was `7cbf311 magic link ui - step` (pre-4a) | ✅ |
| **P6** | Today the Mandant sees a clean letter body | **Brief understated.** `request.html:16` renders `letter_text` **raw**, including all `==BELEGMEISTER==` markers. This is the primary user-visible bug this slice fixes. | ⚠ promoted to primary justification |
| **P7** | Parse-placement seam | Resolved by Decision C (parse in `resolve_request_view`; `RequestView` carries `letter: RequestLetter`). | ✅ |
| **P8** | New `RequestLetterMalformed` failure mode | Resolved by Decision D (`letter_malformed` added to canonical log_reason). | ✅ |
| **P9** | Per-question input contract wire-locks the submit-slice POST body | Resolved by Decisions E + P1.2 (`answer_<idx>` 0-based; submit-handler re-parses; no hidden inputs). | ✅ |

No spike artifact required — all premises were in-tree-verifiable. The
resolver-perf precedent (a slice planned on a falsified `$skip` premise)
does not apply here: this slice touches no DATEV/klardaten contract that
isn't already proven by the 4a+4b code path.

## Out of scope (deliberate)

From the brief + Phase 1 additions:

- POST `/r/{token}/submit` handler logic — submit-slice. This slice
  freezes the wire contract; submit-slice owns the handler.
- Multipart parsing / browser → klardaten upload — submit-slice.
- Email sending — separate slice.
- Typed answer slots per question (date, number, file) — would require
  `Question` model change; no current forcing function.
- SB-side changes (`sb/` templates, `cli/`, `sb/app.py`) — this slice
  touches `web/` only.
- Markdown rendering of the letter body — plain text only; lower attack
  surface; no new dep.
- `LetterSource` Protocol changes (`request_view.py:36-47`) — parse
  happens after `download_document_file`, no new I/O method needed.
- Token revocation / blacklist — stateless tokens by design; revocation
  is a future slice.
- `RequestLetter` dataclass changes — frozen as-is; the codec is the
  single source of truth for the wire format.
- Hidden `question_text_<N>` inputs in the form — submit-handler
  re-parses VGM (incremental cost zero); see **Decision E**.

## Decisions (with WHY)

### Goal-shape decisions

- **D-B: Primary justification is the parsed render (bug fix), not the
  visual alignment (cosmetic).** Chosen because Phase 0 P6 surfaced that
  the Mandant currently sees `==BELEGMEISTER==` markers in their letter
  view — a real, user-visible bug. Visual alignment becomes the secondary
  follow-on that ships in the same slice because the same files are
  touched.
  *Rejected:* "visual alignment as primary" — the cosmetic framing in the
  original brief understated the load-bearing change.

### Architecture / seam decisions

- **D-C: Parse happens in `resolve_request_view`; `RequestView` carries
  `letter: RequestLetter` instead of `letter_text: str`.** Chosen because
  letter-loading and letter-parsing are one conceptual layer; the route
  handler stays a humble object; parse failures fold into the existing
  "any failure → `RequestLinkInvalid` → generic 404" funnel.
  *Rejected:* parse in the route handler — splits letter-handling across
  two layers and forces the route to grow its own error-mapping branch.

- **D-D: `RequestLetterMalformed` maps to a new canonical
  `log_reason="letter_malformed"`, with
  `log_context={"vgm_id": vgm_id, "reason": exc.reason}` (codec short
  code, never file content).** The client still sees the generic 404
  (no information disclosure). The canonical `log_reason` set permanently
  expands from 8 to 9 values.
  *Rejected:* collapse parse errors into existing `letter_not_utf8` —
  silently merges two distinct failure modes; future debugging would lose
  the distinction.

- **D-E: Per-question text inputs use `name="answer_<0-based-index>"`.
  `<textarea name="response">` stays as free-text "notes", independent
  of structured answers. NO hidden `question_text_<N>` inputs.
  Submit-handler re-parses the letter from VGM at POST time and pairs
  answers positionally against the re-parsed `questions` tuple.**
  Chosen because: (1) less HTML surface; (2) automatically tracks
  letter edits (if the SB updates the letter between GET and POST, the
  re-parse pairs against current state, not a stale snapshot); (3)
  submit-handler is already fetching VGM for upload, incremental
  re-parse cost is zero. 0-based to match Python indexing and the SB
  form's `loop.index0` convention (`sb/templates/form.html:96`).
  *Rejected:* hidden `question_text_<N>=…` inputs that snapshot question
  text — adds HTML surface, fragile if letter is edited post-creation,
  and re-parse cost is already zero. YAGNI until submit-slice proves
  re-parse is material.

- **D-S8: `letter.to` and `letter.cc` are NEVER passed into the Jinja2
  template context for the Mandant page. The route handler filters
  `RequestView` down to `{subject, body, questions}` when rendering.
  `RequestView` itself still carries them — future email-slice consumes
  them as SMTP header values.** Chosen because two problems collapse
  into one architectural move:
  1. **Privacy:** Cc on the Mandant page would disclose internal
     recipients (partner secretary, accountant colleagues) to the
     Mandant. To: is the Mandant's own address — redundant.
  2. **XSS surface reduction:** can't XSS-inject what isn't rendered.
     Removes To/Cc from S3's escape-hatch concerns entirely.
  *Rejected:* "render all four (subject/body/to/cc) and trust autoescape
  + a future test" — relies on a future developer remembering "don't
  display To/Cc" rather than making it structurally impossible.
  **🔒 Actively rejected, rationale-locked — reopening requires overriding
  the privacy decision, not "we could revisit".**

### Wire-contract lock (binds submit-slice)

- **D-P1.2: The future `POST /r/{token}/submit` handler must accept this
  body shape, locked by the template this slice ships:**
  - `answer_0`, `answer_1`, …, `answer_N` — string fields, one per
    question by 0-based index, individually optional, all rendered
  - `response` — string, optional, free-text notes textarea
  - `files` — multipart, `multiple` (HTML attribute)

  The `<form action="/r/{token}/submit" method="POST" enctype="multipart/form-data">`
  opening tag is **untouched** (RT1 pin: `tests/web/test_app_route.py:82-85`).

  **`required` is deliberately NOT in the wire contract.** Whether at-least-one
  file is mandatory is a submit-handler business rule (possibly per-request
  flag from SB), not a template-slice decision.

### Visual / UX decisions

- **D-1 (placement): body → questions → files → response → submit.**
  Chosen because the mental model is *"here's what we're asking → answer
  the questions → upload the files → optional notes → send"*. Questions
  are content-continuation of the letter body; files are the primary
  deliverable; response (free-text) is meta.
  *Rejected:* questions before body (no — questions are derived FROM body);
  files before questions (inverts read-then-act); response between (groups
  by widget type, not by user flow).

- **D-2 (body rendering): `<div class="whitespace-pre-wrap break-words
  text-sm text-slate-700 bg-slate-50 border border-slate-200 rounded p-4">`
  — proportional font, same wrapping/border.** Chosen because the body
  is letter prose, not code. Monospace would imply technical content.
  SB form's body uses `font-mono` in the *editor* (alignment-while-typing
  matters); Mandant reader has no such need.
  *Rejected:* keep `<pre>` for monospace — only justification was
  matching SB editor, which is a category error (editor ≠ reader).

- **D-3 (Tailwind sharing): copy class vocabulary inline; both apps
  load `<script src="https://cdn.tailwindcss.com">` independently; no
  shared partial.** Chosen because the two surfaces will diverge by
  design (mobile-first Mandant, dense-form SB); coupling two surfaces
  with no third on the horizon is premature DRY.
  *Rejected:* shared Jinja2 `_base.html` partial — premature; a tweak to
  one surface becomes a risk to the other. Compiled Tailwind CSS — build
  step is out of proportion for a template slice.

- **D-4 (submit button state): live submit (clicking Senden hits
  `/r/{token}/submit` and 404s).** Locked with explicit deployment-order
  constraint: see **Open items § D-4 constraint**. Reasoning: `/r/` is
  localhost-only today; the only person clicking Send is the developer
  during smoke; a 404 on a developer-only surface is acceptable and
  documented at `web/app.py:11`. The constraint binds the future hosting
  slice.
  *Rejected:* `disabled` attribute on the button — honest UX, but unnecessary
  while `/r/` is non-public; introduces a state to revert in submit-slice.
  In-form "coming soon" notice — clutter; half-measure.

- **D-5 (intro paragraph): DROPPED.** Originally proposed as P1.1 (i) in
  Phase 1, dropped in Phase 2 because the h1 + the letter body together
  provide all context; an intro paragraph would be redundant content
  above a more detailed message. The SB form's intro paragraph adds
  *meta-information about the tool* (local-only, manual link sharing) —
  a Mandant intro paragraph has no equivalent meta-information.
  *Rejected:* keep with content like "Ihre Steuerkanzlei hat Sie um die
  folgenden Unterlagen gebeten" — redundant above the letter body.

### Phase 1 P1.1 — visual-alignment edits (revised from 5 items to 4)

Exactly these four edits to `web/templates/{request,invalid}.html`, and
nothing more:

- **(ii)** Add `disabled:opacity-50` to the submit button (mirrors
  `sb/templates/form.html:110`).
- **(iv)** Render body via parsed `letter.body` (not raw `letter_text`).
  Structurally part of D-B primary, but visually it is the biggest
  improvement.
- **(v)** Replace `<pre>` with `<div class="whitespace-pre-wrap ...">`
  per D-2.
- **(vi)** Header brand line — **🔒 explicitly NOT added.** Mandant page
  stays unbranded; should feel like it is from the accountant's office,
  not a third-party SaaS the Mandant does not recognize.
  *Actively rejected, rationale-locked.*

Dropped from the original five:

- **(i)** Intro paragraph — dropped per D-5.
- **(iii)** Back-anchor on `invalid.html` — dropped because the page is
  terminal; there is no honest target to link back to.

### Zero-questions case (P1.3)

- **D-P1.3: With `questions=()`, the entire question-section block is
  hidden — no orphan section heading, no empty container.** Page shows:
  body + `<textarea name="response">` + file input + submit. No
  "no questions to answer" empty-state placeholder.

### Smoke fixture pin

- **D-smoke-fixture: Smoke runs against VGM `#395357`** (same fixture as
  4a smoke; resolver path warm from recent use; continuity across slice
  closures aids future regression diagnosis). Three test questions are
  fixed strings with **no substring collisions with each other or with
  form chrome**: `"Question alpha"`, `"Question beta"`, `"Question gamma"`.
  *Rejected:* "Frage 1" / "Frage 2" — substring-collides with "Frage"
  in the SB form chrome and with each other's prefixes; would silently
  weaken S2-T2's byte-offset ordering assertion.

## Hardest seams (with test approach)

Ranked **S2 > S3 > S8 > S1 > S4 > S5** — false-confidence traps first,
smoke-bounded coverage middle, coverage-gap last.

### S2. Per-question positional pairing — *trap*

**The seam.** Each question must render exactly one
`<input name="answer_<idx>">` paired with its question text at position
`<idx>`. Three Jinja2 traps: (1) off-by-one with `loop.index` (1-based)
vs `loop.index0` (0-based); (2) duplicate `name="answer_0"` if the index
is hardcoded; (3) visible label "Frage 2" while posted field name is
`answer_0` — same row, off-by-one between label and POST contract.

**Why dangerous.** Submit-slice will rely on positional pairing against
re-parse (Decision D-E). If GET emits `name="answer_0"` for the second
question, the submit handler associates the answer with the wrong
question. Data corruption in production, zero test failures.

**Anti-pattern named.** *"Assert `'answer_0' in body and 'answer_1' in body`."*
Passes even if both names appear on the same row or if `answer_0` appears
twice.

**Test approach — two unit tests with non-overlapping fixtures:**

- **S2-T1: `test_per_question_inputs_have_distinct_indexed_names`.**
  Fixture `questions=("Question alpha","Question beta","Question gamma")`.
  Use `re.findall(r'name="(answer_\d+)"', body)`; assert the list is
  exactly `["answer_0","answer_1","answer_2"]` — ordered, no duplicates,
  no skips.
- **S2-T2: `test_per_question_inputs_ordered_with_question_text`.** Same
  fixture. Use byte-offset comparison:
  `body.index("Question alpha") < body.index('name="answer_0"') <
  body.index("Question beta") < body.index('name="answer_1"') <
  body.index("Question gamma") < body.index('name="answer_2"')`.
  Rules out swapped pairings (which would pass S2-T1).

**Fixture-design note.** S2-T2's byte-offset assertion is sound ONLY
because the three question strings have no substring collisions with
each other and no collision with form chrome (no "Frage" substring). A
future test author who replaces them with "Frage 1" / "Frage 2" silently
weakens the assertion — preserve the distinct-string convention.

### S3. Subject / body / question-text XSS on the new rendered surfaces — *trap*

**The seam.** Phase 0 D-C switches from rendering `letter_text` (raw
wire) to rendering parsed `letter.subject`, `letter.body`, and each
`q` in `letter.questions`. The existing
`test_RT3_xss_letter_text_is_html_escaped` pins escape on a variable
(`letter_text`) that **no longer exists in the template context**.

**Why dangerous.** A future refactor adding `{{ letter.subject | safe }}`
or `{% autoescape false %}` introduces an XSS vector that RT3 cannot
catch (its variable is dead). The slice would ship with apparent XSS
coverage that does not cover the new surface.

**Anti-pattern named.** *"RT3 still passes, so XSS is covered."* RT3
tests a dead variable.

**Test approach — three new tests + one deletion:**

- **S3-T1: `test_subject_html_escaped`.** Inject
  `letter.subject = '<script>alert("xss-subject")</script>'`; assert
  rendered HTML contains `&lt;script&gt;` (escaped) and does NOT contain
  raw `<script>alert("xss-subject")`.
- **S3-T2: `test_body_html_escaped`.** Same with `letter.body`.
- **S3-T3: `test_question_text_html_escaped`.** Same with a question in
  `letter.questions`.
- **DELETION:** `test_RT3_xss_letter_text_is_html_escaped` — deleted
  outright, NOT kept "for safety". Keeping it is the false-coverage trap.

### S8. Privacy-by-construction — To/Cc never reach template — *trap-prevention*

**The seam.** Decision D-S8 narrows the Jinja2 template context to
`{subject, body, questions}` at the route boundary. A future developer
who adds `{{ letter.to }}` or `{{ letter.cc }}` to the template (or who
passes `**asdict(view.letter)` to `TemplateResponse`) silently leaks
recipient metadata to the Mandant.

**Why dangerous.** Privacy regression with no exception, no visible
error, no test failure — until a Mandant notices "why does this page
show my accountant's partner's email?". The natural failure mode is
"developer wants subject but doesn't notice the convenient
`**asdict(letter)` smell".

**Anti-pattern named.** *"Trust that the next developer reads the
docstring."* Architectural protection requires a falsifying test, not
documentation.

**Test approach — one unit test:**

- **S8-T1: `test_to_and_cc_not_in_rendered_page`.** Inject
  `letter.to = "SENTINEL_TO_VALUE_xyz123"` and
  `letter.cc = "SENTINEL_CC_VALUE_abc789"`. Assert neither sentinel
  string appears anywhere in the rendered HTML body. Strongly
  falsifiable — if a future refactor passes To/Cc to the template, this
  test breaks immediately.

### S1. Real Tailwind rendering vs. class-name strings in HTML — *smoke-only*

**The seam.** TestClient returns HTML; assertions on class names pass
because the test wrote the string itself, not because Tailwind compiled
it to CSS rules. Class typos (`whitespace-pre-wrap` vs
`whitespace-prewrap`, `max-w-2xl` vs `max-w-2x`) pass unit assertions
and break layout silently.

**Why bounded, not a trap.** "Page looks wrong" is loud when you open
it. Smoke catches it; no false-confidence vector if smoke is bound
(Exit § Bucket 3).

**Anti-pattern named.** *"Class-name string assertion equals rendering
proof."* It does not. Tailwind CDN runs in the browser, never in pytest.

**Test approach.** No unit assertions on class strings beyond a tiny set
of structural anchors. Coverage comes from the **live smoke step in the
exit criterion**, with the bound write-up format (Exit § Bucket 3).
**Smoke-only by construction.**

### S4. Zero-questions hide-entirely — *small trap*

**The seam.** `{% if letter.questions %}` wrapper around the entire
question section is easy to break: a section heading sits outside the
loop and shows on empty input; or an empty `<fieldset>` wrapper renders
with zero children but visible borders.

**Anti-pattern named.** *"Assert `'answer_0' not in body` when questions
is empty."* Passes even if a half-empty container or orphan section
heading is visible.

**Test approach — one unit test:**

- **S4-T1: `test_question_section_hidden_when_no_questions`.** Pick one
  distinctive DOM marker unique to the question section (e.g., a
  wrapper `<section id="questions-block">`); assert that with
  `letter.questions=()`, the rendered body contains no occurrence of
  `"questions-block"` (the entire wrapper absent, not just the inputs).

### S5. Parse-error → `letter_malformed` log_reason — *coverage gap*

**The seam.** Decision D-D adds `letter_malformed` to the canonical
log_reason list. Client always sees a 404 regardless of reason, so a
route bug that collapses `letter_malformed` into `letter_not_utf8` —
or fails to catch `RequestLetterMalformed` at all — looks identical to
the client.

**Anti-pattern named.** *"Assert response is 404 on malformed letter."*
Passes even if the log_reason is wrong, missing, or the exception leaked
as a generic 500 before the route's try/except.

**Test approach — one unit test:**

- **S5-T1: `test_letter_malformed_logs_reason_and_returns_404`.** Use
  `caplog`. Inject a fake `LetterSource` that returns bytes which decode
  as UTF-8 but fail `parse_request_letter` (e.g., `b"not a valid wire format\n"`).
  Assert: (a) response status 404; (b) exactly one WARNING record from
  `belegmeister.web`; (c) that record's message contains
  `reason=letter_malformed`; (d) context includes `vgm_id` and the
  codec's `reason=` short code.

## Exit criterion

The slice is done when ALL four buckets are satisfied AND the closure
artifact is appended to `PROGRESS.md`.

### Bucket 1 — named tests green (enumerated, NOT "all tests pass")

**New tests added (10):**

| Test | Closes seam |
|---|---|
| `test_parsed_subject_renders_in_h1` | Primary goal |
| `test_parsed_body_renders_without_wire_markers` | Primary goal + Bucket 2 |
| `test_per_question_inputs_have_distinct_indexed_names` | S2-T1 |
| `test_per_question_inputs_ordered_with_question_text` | S2-T2 |
| `test_subject_html_escaped` | S3-T1 |
| `test_body_html_escaped` | S3-T2 |
| `test_question_text_html_escaped` | S3-T3 |
| `test_to_and_cc_not_in_rendered_page` | S8-T1 |
| `test_question_section_hidden_when_no_questions` | S4-T1 |
| `test_letter_malformed_logs_reason_and_returns_404` | S5-T1 |

**Tests modified (1 deletion + N mechanical renames):**

- `test_RT3_xss_letter_text_is_html_escaped` — **DELETED.** Replaced by
  S3-T1/T2/T3. Tests a variable that no longer exists in template
  context (D-C).
- RT1 form-attribute pin (`tests/web/test_app_route.py:82-85`) —
  **UNCHANGED.** Wire contract regression guard per D-P1.2.
- Any `tests/web/` test that constructs `RequestView(letter_text=...)` —
  mechanical rename to `RequestView(letter=...)` per D-C. **No test
  logic removed.**

### Bucket 2 — structural assertions (falsifiable primary-goal proof)

These are folded into Bucket 1 tests but called out separately because
they prove the user-visible behavior change:

1. **`assert "==BELEGMEISTER==" not in body`** when rendering a
   happy-path letter (any occurrence anywhere in rendered HTML).
   Inside `test_parsed_body_renders_without_wire_markers`.
2. **`assert "SENTINEL_TO_VALUE_xyz123" not in body and "SENTINEL_CC_VALUE_abc789" not in body`**
   when those values are injected into `letter.to`/`letter.cc`. Inside
   `test_to_and_cc_not_in_rendered_page` (S8-T1).

### Bucket 3 — smoke walkthrough (the only S1 coverage)

**Binding write-up format.** PROGRESS.md closure section MUST contain
all five line items below. *"Smoke verified ✓"* without per-step evidence
is the same false-confidence vector as dead RT3 — if the write-up cannot
be produced, the smoke didn't happen; record it as such rather than
waving it through.

Required line items:

1. **VGM id used:** `#395357` (numeric Dokumentnummer + resolved GUID
   for traceability). Pinned by D-smoke-fixture.
2. **Three question strings used (verbatim):** `"Question alpha"`,
   `"Question beta"`, `"Question gamma"`.
3. **Browser + version:** e.g., `"Firefox 122 on macOS"`.
4. **Mobile viewport dimensions:** e.g., `"Chrome DevTools, 375×667
   iPhone SE preset"`.
5. **Per-step pass/fail for smoke steps 1–7** (step 8 is explicitly
   not in smoke; covered by S5-T1).

**Smoke steps:**

1. Start both apps:
   - `uv run uvicorn belegmeister.sb.app:app --port 8731`
   - `uv run uvicorn belegmeister.web.app:app --port 8000`
2. Create a request via `/sb` against VGM `#395357` with the three
   distinctive questions. The SB create path is in-scope (continuity of
   the user journey); the ~45s resolver stall is a workflow nuisance,
   not a correctness issue.
3. Copy magic link from result page.
4. **Desktop browser**, visual assertions:
   - h1 displays the subject (not the raw wire format)
   - Body text appears as prose (proportional, wrapped, no
     `==BELEGMEISTER==` visible anywhere)
   - Three labeled text inputs visible, each labeled with the
     corresponding distinctive question string
   - "Notes" textarea present below questions
   - File picker visible
   - Submit button styled identically to SB form's "Anforderung
     erstellen" button (same `bg-slate-800`, hover state,
     `disabled:opacity-50`)
   - **To/Cc values absent from page** — view-source / Ctrl+F for the
     recipient address; must not be present
5. **Mobile-narrow viewport** (~375px width), visual assertions:
   - Container fits viewport; no horizontal scroll
   - Text inputs reach edge-to-edge of container
   - File picker tap target ≥ ~44px
6. **Invalid token:** modify one character in the URL token, reload →
   `invalid.html` displays:
   - Same slate palette / container shape as SB pages
   - No back-anchor (per Phase 2 (iii) drop)
   - No header brand line (per D-S8 / P1.1 (vi))
7. **Zero-questions case:** create another request via `/sb` with no
   questions, open magic link → confirm no question-section heading or
   empty container visible.
8. **NOT in smoke:** malformed letter — covered by S5-T1 (caplog).

If mid-build mobile responsiveness requires breaking changes beyond
class additions (e.g., restructuring form layout for touch targets),
**surface as a Phase 2 reopen, do not quietly drop step 5.**

### Bucket 4 — static checks

- `uv run ruff check .` — clean
- `uv run ruff format --check .` — clean
- `uv run mypy --strict src/ tests/ scripts/` — clean

### Closure artifact — what gets appended to PROGRESS.md

New section titled `## magic-link-ui — CODE COMPLETE` with:

- Date (2026-…)
- **Test count assertion (mandatory, with disappearance-or-explain rule):**
  - Before: `165` tests (from PROGRESS.md tail, current as of slice
    planning)
  - After: `174` tests (`165 + 10 new − 1 deleted = 174`)
  - Added (10): list by name from Bucket 1
  - Deleted (1): `test_RT3_xss_letter_text_is_html_escaped` — replaced
    by S3-T1/T2/T3 per D-C (dead-variable false-coverage)
  - Mechanical (per D-C): `RequestView` field rename in N `tests/web/`
    files; no test logic removed
  - **Anything outside these four categories is a silent disappearance
    — explain it inline or roll back.**
- Smoke verification with the five binding line items from Bucket 3
- Any surprises during implementation (per the 4b "Surprises" precedent)
- Files staged (final list per implementation)
- Suggested commit message (per CLAUDE.md autonomy policy — Claude
  stages, human commits)

## Deferred to later slices

### Deferred — forcing function pending

| Item | Why later, not now |
|---|---|
| **Submit-slice** (`POST /r/{token}/submit` handler, multipart parse, browser → klardaten upload, upload-progress UI, file preview) | Separate slice. Wire contract is locked here (D-P1.2); handler logic owns the receive/forward path. |
| **Email-slice** (SMTP send of magic-link URL using letter.to/cc as headers) | Requires SMTP configuration, deliverability decisions. Letter.to/cc are kept on `RequestView` precisely so this slice consumes them. |
| **Hosting / deployment slice** (public `/r/` host, real domain, TLS, healthcheck endpoint, `MAGIC_LINK_SECRET` provisioning across SB + hosted `/r/`) | Different slice character (no unit-RED for systemd/TLS). Has a hard ordering constraint vs submit-slice — see **Open items § D-4 constraint**. |
| **Typed answer slots per question** (date, number, file) | `Question` model change in `request_format.py`; no current forcing function (SB collects free-text questions; this slice renders free-text answers). |
| **Token revocation / blacklist** | Stateless tokens by design (`magic_link/token.py:18-21`). Requires a store + per-render check. |
| **Hidden `question_text_<N>` inputs** | Re-parse cost on submit is currently zero; revisit only if submit-slice measures otherwise. YAGNI. |
| **Compiled Tailwind CSS / shared partials between `sb/` and `web/`** | Premature DRY; two surfaces diverge by design. Revisit when a third surface appears. |
| **Headless browser tests / visual regression infra** (Playwright, Percy, Chromatic) | Own infrastructure slice (CI runners, browser pinning, flake management). Smoke handles S1 today. |
| **Browser support matrix beyond smoke** (Safari, Edge, older Android) | Defer to deployment-slice when a real-user support contract exists. |
| **Rate limiting on `/r/{token}`** | Structurally not needed (HMAC brute-force infeasible). Proxy-level concern; deployment-slice. |
| **Magic-link expiry display ("link expires on X")** | UX iteration; no user-feedback signal. Premature. |
| **Resubmit / re-edit flow** | One-shot by design ("intentionally non-idempotent — each run auditable"); future re-issue/supersede slice owns this. |
| **i18n / multi-language Mandant support** | Hardcoded German copy. Current target population is German-speaking; no forcing function. Anchor a future "we now have an international client" reopen here. |
| **Mandant session / draft state across navigation** | Server-rendered, stateless tokens, no client-side draft persistence. Mandant losing input on tab switch is a known shortfall. No user-feedback signal; UX iteration pending. Same category as magic-link expiry display. |

### Actively rejected — rationale-locked 🔒

These are not "we'll do it later" — they are **"we have decided not to
do this, and reopening requires overriding the rationale, not
re-litigating from scratch."**

| Item | Rationale |
|---|---|
| **Header brand line on Mandant pages** 🔒 | Mandant should feel the page is from their accountant's office, not from a third-party SaaS the Mandant does not recognize. (P1.1 (vi).) |
| **`letter.to` / `letter.cc` rendered on Mandant page** 🔒 | Privacy (Cc would disclose internal recipients to the Mandant) + XSS-surface reduction by construction. RequestView keeps them for the email-slice's SMTP needs; the route handler filters at the boundary. (D-S8.) |
| **Intro paragraph on `request.html`** 🔒 | Redundant content above a more detailed letter body. The SB form's intro adds *meta-information about the tool*; a Mandant intro paragraph has no equivalent meta. (D-5.) |
| **Back-anchor on `invalid.html`** 🔒 | Terminal page; no honest target to link back to. An anchor pointing nowhere is worse than no anchor. (P1.1 (iii) drop.) |

### Recognized debt — no automated signal, comfort grows with neglect

| Item | Why this is its own category |
|---|---|
| **Accessibility audit** (ARIA labels, keyboard nav, screen reader testing) | The template adds new form elements without proper `<label for>` / `id=` pairing (SB form has the same gap — `sb/templates/form.html:32-33`, etc.). Every Mandant who cannot use the form is a user silently lost. There is no automated test that surfaces this gap, and the deferral is comfortable precisely because no one is complaining. Defer to an accessibility slice with WCAG-level scope and screen-reader testing; piecemeal ARIA additions in this slice would be a half-measure with false-coverage risk. *Future "let's fix a11y" reopens with anchoring to this entry, not fresh discovery.* |

## Open items requiring human decision

### D-4 constraint — deployment-order between submit-slice and hosting-slice

**Constraint:** Production hosting of `/r/` (the deployment/ops slice
flagged at PROGRESS.md tail) **MUST NOT ship before submit-slice.** If
the hosting slice is scheduled to ship first, the Senden button must be
set to `disabled` per D-4 alternative (b) **before** hosting goes public.

**Why this lives in the slice contract:** D-4 (live submit) is correct
under the current invariant "`/r/` is localhost-only." That invariant
breaks the moment hosting ships. Encoding the dependency here makes a
future "let's ship hosting next sprint" land against this constraint
instead of silently exposing a live-looking, 404'ing form to real
clients.

**Recommended handling:** when the hosting slice is planned, its first
Phase 0 check should be "is submit-slice already shipped?". If no,
either (a) gate hosting on submit-slice completion, or (b) gate hosting
on a `disabled`-button toggle in `web/templates/request.html` before
deploy.

### Submit-slice POST contract permanence

The wire contract locked by this slice (D-P1.2):

- `answer_0`, `answer_1`, …, `answer_N` — string fields, individually
  optional, all rendered, 0-based
- `response` — string, optional
- `files` — multipart, `multiple` (HTML attribute), `required`-ness
  **not** part of the contract

The submit-slice handler MUST accept this body shape. Changing it later
requires either (a) re-issuing this slice's template work, or (b) the
submit handler tolerating multiple body shapes — both are real cost
relative to "freeze it now while only one developer cares".

### `letter_malformed` enum permanence

`RequestLinkInvalid.log_reason` permanently expands from 8 to 9 values
(D-D). Future code touching `web/request_view.py` must respect:
`token_expired`, `token_bad_signature`, `token_malformed`,
`vgm_not_found`, `datev_error`, `letter_missing`, `download_failed`,
`letter_not_utf8`, **`letter_malformed`**.

The docstring at `web/request_view.py:49-76` must be updated to include
the new value.
