# Roadmap

This is the single source of truth for the **feature-level** phase scheme this project follows —
distinct from [`docs/architecture.md`](architecture.md)'s numbered phases 0–7, which track
infra/module build-out (repo scaffolding, ingestion, enrichment, credits, etc.). This document
tracks the product workflow: company targeting → qualification → role targeting → tracker/cadence
→ outreach drafting. It didn't exist as a checked-in document until now — several ADRs and
`data-model.md` referenced "the roadmap" or "the approved plan" without one being in the repo;
this file is that document going forward, and those references have been updated to point here.

Source: a single detailed working session between Paarth Sahni and Abhas Jain
(`Meeting notes/Sales Funnel Automation Discussion - 2026_09_08...md`) that defined the actual
manual workflow being automated.

## Phase A — Company Targeting & Qualification

### A1 — Company Discovery Agent — **Done**
Turns a free-text market description into real, criteria-matched company candidates (gather →
LLM-extract → resolve pipeline), replacing raw search-link noise (Reddit threads, "best of"
listicles) that the naive first implementation produced. `discovery_agent/`,
[ADR 0004](decisions/0004-discovery-agent.md).

### A2.1 — Qualification Criteria Catalog — **Done**
Org-configurable catalog of qualification rules (not hardcoded to any one org's examples), each
with an explicit `is_disqualifying` flag. `qualification/` (`QualificationCriterion`).

### A2.2 — Qualification Judgment Core — **Done**
Judges a company against active criteria: the LLM reasons per-criterion
(`met`/`not_met`/`could_not_determine` + evidence-grounded reasoning), but the overall
qualified/not_qualified/could_not_determine verdict is computed **deterministically in Python**
from `is_disqualifying`, never inferred by the LLM. Append-only history (`QualificationResult`).
[ADR 0005](decisions/0005-qualification-scoring.md).

### A2.3 — Ad Hoc / Quick Check — **Done**
Type a company name or domain that may not exist in the system yet; resolves-or-creates the
`Company` and immediately runs the A2.2 judgment against it — for the "someone just mentioned
this company, is it worth pursuing right now" case Abhas described explicitly in the meeting.
`POST /qualification/check`.

### A2.4 — Qualification surfacing (list column, bulk action) — **Done**
Qualification-verdict column on the companies list (latest `QualificationResult` per company,
joined without N+1). A bulk "qualify these newly-discovered companies" action on the Market
Discovery results screen, run as a background job (same job-queue pattern as Market Discovery
itself) so a rep can go from one free-text prompt to judged companies without opening each one
individually — the "give it a prompt and it works on its own" automation this closes out Phase A
for. Scoped to companies *created* by that specific run, not ones reused from the compounding
index.

### A3 — Role-Relevance Classification — **Done**
Titles for the same function aren't standardized across companies (Abhas's example: "IT vendor"
at one company vs. "category procurement manager" at another) — so contacts are classified
against an org-configurable catalog of role categories by inferred function, not title
keyword-matching. The LLM matches each contact to the best-fitting category (or none); which
categories count as primary-target (surfaced first) is an explicit flag, and the resulting
priority (`primary`/`secondary`/`not_relevant`) is computed deterministically from that flag —
same "LLM judges narrowly, code decides the actionable outcome" pattern as A2.2. Append-only
history (`RoleRelevanceResult`), same reasoning as A2.2 (auditable, no silent overwrite on
re-classify). `role_relevance/`, [ADR 0006](decisions/0006-role-relevance-classification.md).

## Phase C — Tracker & Cadence Mechanics — **Done**

Abhas's manual tracker today: name, geography, designation, company, LinkedIn URL, per-channel
done-flags (email/LinkedIn), next-action date, free-text remarks — and keeping it updated is
explicitly what burns him out ("half of your enthusiasm goes down"). Automates the parts of this
that don't require Phase B (draft generation) to exist yet:
- **Auto-updating the tracker after a send/response** — logging an `OutreachActivity` (`sent` or
  `response_received`) via `POST /contacts/{id}/outreach-activities` derives
  `Contact.status`/`next_follow_up_at`/`next_follow_up_channel` automatically
  (`outreach/service.py::log_outreach_activity`), replacing manual re-entry for this common case.
  Manual override via `PATCH /contacts/{id}/tracking` stays available for anything this doesn't
  cover. `OutreachActivity` itself is append-only, same pattern as `QualificationResult`/
  `RoleRelevanceResult`.
- **Send-window scheduling**: Monday–Wednesday (Thursday only if urgent), never Friday/weekend,
  landing at 11:00 in the contact's own timezone when set (`Contact.timezone`, nullable — falls
  back to `settings.default_timezone`) — pure, exhaustively unit-tested logic in
  `outreach/cadence.py::next_send_window_slot`, deterministic date math with no LLM involved.
- **Proactive next-action reminders**: the existing `GET /contacts/follow-ups` "due" list now
  surfaces as a live count badge on the sidebar's Follow-ups nav item, not just a page a rep has to
  remember to open.
- **A/B data capture**: `OutreachActivity.template_variant` (free-text) is captured on every logged
  send now, so nothing is lost once Phase B exists to generate real variants. Aggregate
  response-rate-per-variant reporting is deliberately deferred until then — see A/B testing below.

`outreach/` module, [ADR 0007](decisions/0007-tracker-cadence.md).

## Phase B — Outreach Draft Generation — **Done (email only)**

Generates the actual first-touch/follow-up message a rep sends, instead of writing every outreach
message by hand:
- First cold email: max 7–8 lines, enforced via explicit prompt structure — 1–2 lines credibility,
  1–2 lines a proof point/analogous project (grounded in an existing `ai_recommendation`
  `Recommendation` for that company+product when one exists; an explicit anti-hallucination
  instruction when it doesn't), one closing CTA, no explicit problem/solution claim.
- Persona-tailored framing: an explicit `RoleCategory.framing_style` (`business`|`technical`) —
  A3's role classification now snapshots this at judgment time, same as `matched_category_name`,
  and the draft prompt writes in whichever register was set, rather than the LLM inferring a
  register itself. A contact with no classification yet falls back to `business` — not a hard
  failure, since not every org will always classify before drafting.
- Second follow-up: a separate prompt template, explicit instruction to be informational/useful on
  its own (not "just following up") and to avoid known AI-outreach tells.
- Human-in-the-loop: a generated `Draft` is mutable — a rep edits subject/body in place before
  clicking "Log as Sent", which persists any pending edit, links the resulting `OutreachActivity`
  back to the draft (`OutreachActivity.draft_id`), and flips the draft to `sent`.

**LinkedIn drafting is deferred** — the meeting's structure/length spec is email-specific; `Draft`
already has a `channel` field, so extending it later doesn't require new schema, just another
prompt template.

`draft/` module, [ADR 0008](decisions/0008-outreach-draft-generation.md).

### A/B template testing — **Data capture flowing, reporting still deferred**
Explicitly requested ("Maybe we do an AB test") and listed as an action item in the meeting's own
summary. `OutreachActivity.template_variant` (Phase C) now actually gets populated by real drafts
(defaulted from `Draft.draft_type` when a rep logs one as sent), so there's real variant data
accumulating — but the aggregate response-rate-per-variant stats endpoint/UI remains deliberately
out of scope until a dedicated pass is worth it.

## Known mismatches vs. the meeting notes

Called out explicitly here so they don't get silently carried forward:

- **"Everything stays in-tool, no external redirects"** was a pointed live-demo critique
  ("we don't want any person to probably click something and go to the internet himself") that
  currently lives only in the transcript, not as a written design principle. Worth its own short
  ADR so it's an enforced constraint on future outreach/tracker UI, not something that has to be
  independently rediscovered.

## Source

See `Meeting notes/` for the full transcript this roadmap derives from.
