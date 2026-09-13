# ADR 0008: Outreach Draft Generation — Mutable Drafts, Explicit Framing, Grounded via Recommendation

**Status:** accepted
**Date:** 2026-09-11

## Context

Phase B is the last piece from the meeting: generating the actual first-touch and follow-up
message drafts a rep sends, instead of writing every outreach message by hand. Scope:
- First cold email: max 7-8 lines, 1-2 lines credibility, 1-2 lines a proof point/analogous
  project, one CTA, no explicit problem/solution claim.
- Persona-tailored framing: outcome/cost-savings language for business-side contacts,
  technical/KPI language for engineering-side contacts — consuming A3's role classification.
- Second follow-up: informational/helpful, not "just following up," avoiding cold-email clichés
  and AI-generated tells.
- Human-in-the-loop: manual review before sending.

## Decisions

1. **`Draft` is mutable, not append-only** — unlike every other Phase A/C entity
   (`QualificationResult`, `RoleRelevanceResult`, `OutreachActivity`), which are event logs /
   judgments that already happened and should never be silently rewritten. A `Draft` is a
   work-in-progress document a human is actively editing before it becomes real customer-facing
   copy — closer in spirit to `RoleCategory`/`Product` (`UpdatedAtMixin`, editable in place) than
   to a judgment log. Confirmed with the user: the rep can tweak subject/body in a textarea and
   save edits to the same row, not just regenerate-or-accept a new one.

2. **Persona framing is an explicit `RoleCategory.framing_style` field** (`business`|`technical`),
   not inferred by the LLM at draft time — same "explicit guardrail, not inference" reasoning
   that produced `is_primary_target`/`is_disqualifying` everywhere else in this app. Snapshotted
   onto `RoleRelevanceResult.matched_category_framing_style` at classification time, exactly like
   `matched_category_name`/`is_primary_target` already are, so a later edit to a category's
   framing never rewrites past classification history. A contact with no role-relevance
   classification yet falls back to `business` — a valid, expected state (not every org will
   always classify before drafting), not a hard failure.

3. **Grounding reuses `Recommendation` (Phase A) instead of re-deriving credibility content.**
   `generate_draft` looks up the most recent `Recommendation` for the same (company, product) pair
   and, when one exists, feeds its `why_this_company`/`talking_points` into the prompt as the
   proof-point/analogous-project content — avoiding a second LLM call and a second "why this
   company" derivation, and guaranteeing the draft and any existing sales-prep notes stay
   consistent. When no `Recommendation` exists, the prompt explicitly instructs the LLM not to
   fabricate a case study or project — the same anti-hallucination pattern
   `recommendation_generator.py` already uses for empty contacts/signals.

4. **No job queue** — generating a draft is one Gemini call (same shape as `Recommendation`
   generation, which is also a plain synchronous endpoint, not a job), not a multi-step
   scrape-then-judge pipeline like Quick Check. A plain request/response endpoint matches the
   actual latency and avoids polling machinery for a single call.

5. **Email only this pass.** The meeting's structure/length spec (7-8 lines, subject line) is
   email-specific; LinkedIn message conventions weren't detailed the same way. `Draft.channel` and
   `DRAFT_CHANNELS` exist as a real field/tuple rather than being hardcoded inline, so adding
   LinkedIn later is "add a channel value and a prompt template," not a schema change.

6. **`OutreachActivity.draft_id` links a sent draft to the activity it produced** — nullable,
   same optional-FK-snapshot pattern as `Recommendation.contact_id`/
   `RoleRelevanceResult.matched_category_id`. Manual free-text logging (no draft involved) stays
   `None`. Logging with a `draft_id` defaults `template_variant` to the draft's `draft_type` when
   not explicitly given, and marks the draft `sent` — this is also what makes Phase C's
   `OutreachActivity.template_variant` (captured since Phase C, unused until now) start carrying
   real A/B data.

## Consequences

- A draft's `body`/`subject` are the actual customer-facing message a rep may hand-edit before
  sending — unlike `Recommendation`, which is explicitly internal-only prep material never shown
  to a prospect. These are deliberately different entities, not a shared one, so a display bug or
  edit to one can never leak into the other.
- Because grounding is best-effort (a `Recommendation` may not exist), draft quality for a
  never-recommended company/product pair depends more on the LLM's general reasoning from
  firmographics alone — expected and explicitly guarded against fabrication in the prompt, not a
  bug.
- A/B **reporting** (response-rate-per-variant) remains out of scope — `template_variant` data
  now genuinely accumulates from real drafts, but building an aggregate stats view is deferred to
  whenever that's explicitly prioritized, per `docs/roadmap.md`.
- LinkedIn drafting is a known gap, not an oversight — deferred until there's real guidance on its
  structure/length/register the way the meeting gave for email.
