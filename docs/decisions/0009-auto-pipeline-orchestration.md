# ADR 0009: One-Prompt Pipeline Orchestration

**Status:** accepted
**Date:** 2026-09-13

## Context

Every phase from the meeting existed as a working, independently-built module (`market_discovery`,
`qualification`, `role_relevance`, `draft`) — but a rep still had to manually trigger each one in
turn: Parse → Confirm → bulk-qualify button → Classify Roles per company → Generate Draft per
contact. This isn't the "type one prompt, the system does the rest" experience Abhas actually
described — it's the same automation gap A2.4 only partially closed (discovery→qualification, not
what comes after). This ADR covers the orchestrator that closes it the rest of the way.

## Decisions

1. **A new orchestrator, not a merge of the existing modules.** `orchestrator/service.py`
   (`_run_auto_pipeline` + `run_auto_pipeline_job`, job type `auto_pipeline`) calls
   `market_discovery`'s `_run_market_discovery`, `qualification`'s `_run_bulk_qualification`,
   `role_relevance`'s `run_role_relevance_check`, and `draft`'s `generate_draft` directly, in
   sequence. None of those modules' internal logic changed to support this (aside from extracting
   `_run_bulk_qualification` as a pure core, mirroring the existing
   `_run_adhoc_qualification`/`run_adhoc_qualification_job` split) — each stays independently
   callable exactly as before. This is the system's second genuine multi-step "agent" (after
   `discovery_agent/`): it decides what to run next based on each stage's actual outcome, while the
   simpler modules underneath correctly stay generator+service pairs, not agents themselves — they
   gain no new capability from being orchestrated.

2. **Skip, don't fail, on a missing prerequisite.** If an org has no active qualification criteria,
   no active role categories, or no product specified, the corresponding stage (and everything
   that depends on its output) reports `{"ran": false, "skipped_reason": "..."}` instead of raising
   and failing the whole job. A broad market-discovery prompt still produces real, useful discovered
   (and possibly qualified) companies even if a later, more specialized stage isn't configured yet
   — failing the entire run over one optional later stage would throw away work that already
   succeeded.

3. **A safety cap on the two Gemini-call-heavy later stages.**
   `settings.auto_pipeline_max_companies_to_draft` (default 5) limits how many *qualified*
   companies get carried into role-classification and drafting in one run. Discovery and
   qualification themselves are uncapped (bounded only by the existing `CANDIDATE_LIMIT` and
   whatever qualifies). This exists because this project's free-tier Gemini quota was hit
   twice already during earlier phases (misdiagnosed transient-overload errors that turned out to
   be daily quota exhaustion) — a single broad prompt discovering dozens of companies, each
   costing a qualification call, a role-classification call, and a draft call per primary contact,
   could exhaust the shared daily quota in one run and silently take down every other Gemini-backed
   feature for the rest of the day. The cap is a deliberate, documented, configurable safety valve,
   not an arbitrary limit — raise it once real usage patterns are known.

4. **Confirming parsed criteria stays a manual click.** Considered auto-confirming when the parse
   is confident (reusing the existing per-field confidence flags), but decided against it: the
   human explicitly wanted this one review point kept. Every stage after that click is automatic.

5. **Product resolution is deterministic, never guessed.** The confirm endpoint resolves a
   `product_id` when the org has exactly one product; with zero or more than one, it's left
   unresolved and the drafting stage reports itself skipped rather than the system guessing which
   product to pitch — same "explicit gate over inference" pattern used everywhere else in this
   codebase (`is_disqualifying`, `is_primary_target`, `framing_style`).

## Deferred (explicitly, not overlooked)

- **Domain-agnostic workflow generalization** (e.g. reconfiguring this for vendor management, not
  just sales) — raised directly, decided to build the sales pipeline correctly first and treat
  generalization as its own future phase (`docs/roadmap.md`'s Phase D), not something rushed into
  this pass. The org-configurable data (criteria/categories/products) already isn't hardcoded; the
  pipeline *shape* and entity names still are, and generalizing those properly is real, separate
  work.
- **Incorporating Abhas's own cold-email/LinkedIn templates once received.** The intended design,
  once templates exist: feed a template into the draft prompt as a style/structure *reference* the
  LLM adapts to the specific company/contact — not a rigid fill-in-the-blank (loses persona
  framing and grounding), and not ignored either (the whole point of asking for them). The LLM
  should take ideation from the template and from the actual company/contact/product data
  together, never over-relying on either alone, and the result should never read as AI-written or
  overclaim. Not implemented now — no templates exist yet to design and test against — but
  documented here so the intent survives to when they do.
- **Gemini-vs-deterministic-logic scope in general.** Clarified during this work: scraping and
  domain search already don't use an LLM at all (`WebsiteScraperProvider`, `SerperSearchProvider`
  are plain HTTP/search-API code). Where Gemini is used, it's already scoped narrowly — judging one
  criterion, matching one category, extracting structured fields from text — with Python computing
  every actionable outcome deterministically (`_compute_priority`, `overall_verdict`, `framing_style`
  gating). The one place the LLM genuinely *creates* rather than judges/extracts is draft/
  recommendation prose generation — exactly where the template-reference design above narrows that
  further once real templates exist.

## Consequences

- A rep now gets discovered, qualified, role-classified companies with drafted first-touch emails
  on primary-target contacts from a single "Confirm & Start Discovery" click, when criteria,
  categories, and a product are configured.
- The standalone `market_discovery`/`bulk_qualify` job types and their endpoints are unchanged and
  still useful — for re-running a stage manually, or catching companies beyond the cap.
- Progress reporting during the run is coarse (stage 1 of 4 .. 4 of 4), not per-item within a
  stage — the detailed breakdown is only visible once the job completes, in its result. Acceptable
  for a first pass; per-stage item-level progress could be added later without changing the job's
  external shape.
- The worker processes one job at a time; a large `auto_pipeline` run (many companies × several
  Gemini calls each) can occupy the worker for longer than the smaller jobs it replaces at the
  confirm step. Pre-existing single-worker architecture characteristic, not introduced by this
  change — a separate concern from this ADR's scope.
