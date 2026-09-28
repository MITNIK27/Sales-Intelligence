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

## One-Prompt Pipeline Orchestration — **Done**

Every phase above existed as an independent, manually-triggered step — going from a market
description to a drafted email required, per company: Parse → Confirm → bulk-qualify button →
Classify Roles button (per company) → Generate Draft button (per contact). This is the actual
"give the system a prompt and it works on its own" automation Abhas asked for, closing the gap
A2.4 only partially addressed (it automated discovery→qualification, not what came after).

A single orchestrator (`orchestrator/service.py`, job type `auto_pipeline`) now runs
`market_discovery` → `qualification` → `role_relevance` → `draft` in sequence automatically. It
owns none of their logic — each stays independently callable exactly as before (a rep can still
classify one company or draft one contact by hand). The **only remaining manual step** is the
existing "Confirm & Start Discovery" click (reviewing parsed criteria before any real work starts,
by explicit choice — not auto-confirmed); everything after that one click is automatic:
- If a later stage's prerequisites are missing (no active qualification criteria, no active role
  categories, no product specified), the pipeline **continues and reports what was skipped**
  rather than failing the whole run over one optional later stage.
- A safety cap (`settings.auto_pipeline_max_companies_to_draft`, default 5) limits how many
  qualified companies get carried through to role-classification and drafting in one run —
  protects the shared Gemini free-tier daily quota from one broad prompt exhausting it. Discovery
  and qualification themselves still process everything found; only the two more Gemini-call-heavy
  later stages are capped.
- This is the system's second genuine multi-step "agent" (after `discovery_agent/`) — it decides
  what to run next based on each stage's actual outcome. The simpler modules underneath it
  (`qualification/`, `role_relevance/`, `draft/`) correctly stay generator+service pairs, not
  agents themselves.

`orchestrator/`, [ADR 0009](decisions/0009-auto-pipeline-orchestration.md).

## Phase D — Workflow Generalization — **Not started, deliberately deferred**

Raised explicitly: could this become a domain-agnostic workflow platform (e.g. reconfigured for
vendor management, not just sales prospecting) rather than a sales-specific tool? The
org-configurable pieces (qualification criteria, role categories, products) are already database
rows, not hardcoded logic, so *what* gets judged already doesn't require code changes. What's still
sales-specific and hardcoded is the pipeline shape itself (discover → qualify → classify → draft)
and the entity names throughout the code (`Company`, `Contact`, `QualificationResult`, ...).
Generalizing that into a true domain-agnostic workflow engine is real, substantial work — decided
explicitly to do the sales pipeline correctly first and treat this as its own deliberate future
phase, not an afterthought bolted onto the orchestrator above.

Also deferred, same reasoning: once Abhas shares his own cold-email/LinkedIn templates, `draft/`'s
prompts should incorporate them as a style/structure *reference* the LLM adapts to the specific
recipient — never fully relied on (the LLM still grounds in real company/contact data and takes
ideation from the template) nor fully ignored — while continuing to avoid overclaiming and never
reading as AI-written. Not implemented now since no templates exist yet to design against; noted
here so the intent isn't lost.

## Companies List Sorting — **Done**

The companies list was hardcoded to alphabetical with no sort option, and — a coupled bug found
while fixing this — the frontend never sent real pagination to the backend at all, so companies
past the first 50 were silently unreachable regardless of sort. Both fixed together: `GET
/companies` now takes `sort_by` (`name`/`created_at`/`last_enriched_at`/`enrichment_status`/
`qualification`) and `sort_dir`, with nullable sort keys (never-enriched, never-qualified) always
sorting last; the frontend does real server-side paging and clickable sortable column headers
instead of client-side slicing over one fetched page.

## In-House Search-Based Contact Discovery — **Done**

The website scraper is the only automated contact source — many real decision-makers are never
listed on a company's own `/about`/`/team` pages. Rather than a paid vendor (Apollo/Hunter —
researched, viable, deliberately deferred to their own pass) or scraping LinkedIn directly
(excluded per ADR 0001), this reuses already-built, already-paid-for search infrastructure
(`SerperSearchProvider.search_raw`) to find public mentions of a company's people on an
org-configurable, curated allowlist of trusted sites (default: `linkedin.com`) — reading only what
a search engine already indexed, never fetching the trusted sites themselves. Runs automatically
during enrichment alongside the website scraper, and on demand per company
(`POST /companies/{id}/search-contacts`). Every result is heuristic and low-confidence by nature,
so it's flagged `needs_review` like every other search-derived record in this app — and, new,
contacts can now actually be deleted (`DELETE /contacts/{id}`, refused with a clear error if real
outreach/draft/role-relevance history depends on the contact) so a rep can remove a bad match.

`enrichment/providers/search_contacts.py`, [ADR 0010](decisions/0010-search-based-contact-discovery.md).

## Phase E — Channel Integrations — **Not started, deliberately scoped**

Raised directly: connect a rep's LinkedIn and/or Gmail account for better results — more accurate
contacts, and outreach that's actually sent rather than manually logged. Neither is built. This
phase is deliberately scoped, not silently deferred: **do not** connect a rep's personal LinkedIn
account (reaffirms ADR 0001's ToS/account-ban concern; a paid enrichment vendor — Apollo.io/
Hunter.io, already researched in ADR 0010 — is the right lever if contact accuracy needs to
improve). **Gmail send** is identified as the higher-value next step instead — real OAuth2 send
would remove the last manual step in the draft-to-send flow ("Log as Sent" today) and let
`OutreachActivity` capture a real thread id, enabling automatic reply detection instead of a rep
manually logging responses. Not built now — this phase exists so the choice is explicit.
[ADR 0011](decisions/0011-linkedin-gmail-integration-scope.md).

## Company Page UX — Pipeline Visibility — **Done**

The backend orchestration (One-Prompt Pipeline Orchestration, above) was real but invisible outside
the Market Discovery page — `CompanyDetailPage` presented the same automated stages as five
disconnected manual buttons in an order that didn't match the pipeline (Qualification, a
company-level gate, rendered below Contacts). Fixed: a `PipelineStatusStepper` at the top of the
company page now shows Discovered → Enriched → Qualified → Roles classified → Drafted derived from
data the page already loads, sections were reordered to match pipeline order (Qualification now
precedes Contacts), the Signals empty state distinguishes "never scraped" from "scraped, found
nothing," and the "Search for Contacts" action is labeled to make clear it reads public search
results, never logs into LinkedIn. No backend or data-model changes.

## `needs_review` Over-Flagging Fix + Bulk Confirm — **Done**

A real defect, not just confusing UX: `ingestion/market_discovery.py` flagged **every** company
created by Market Discovery as `needs_review=True` unconditionally, discarding the discovery
agent's own per-candidate confidence signal (`ExtractedCompany.needs_review`, set only by the
listicle-name heuristic backstop in `discovery_agent/heuristics.py` — most candidates are never
flagged there). Since the auto-pipeline orchestrator skips role classification for any
`needs_review` company and drafting for any `needs_review` contact, this meant a Market Discovery
run's companies routinely could not proceed past qualification without a rep manually confirming
every single one — and confirming was strictly one-at-a-time
(`POST /companies/{id}/confirm`/`POST /contacts/{id}/confirm`), with no bulk option anywhere.

Fixed two ways:
- `market_discovery.py` now sets `company.needs_review`/`needs_review_reason` from the discovery
  agent's own candidate-level signal instead of forcing `True` for everything — a confidently
  resolved company now proceeds straight through role classification and drafting, matching what
  the confidence signal was already computing and discarding.
- Added `POST /enrichment/needs-review/confirm-bulk` (`orchestrator/service.py`,
  `JOB_TYPE_BULK_CONFIRM`) — confirms any given set of companies/contacts in one background job,
  resuming role classification/drafting per company exactly like the single-company confirm
  endpoint does. The Needs Review page now has a "Confirm all" action wired to this, and its
  description text was corrected — it previously read "nothing here is blocking the pipeline",
  which was simply false given the orchestrator's actual skip behavior.

## Known mismatches vs. the meeting notes

Called out explicitly here so they don't get silently carried forward:

- **"Everything stays in-tool, no external redirects"** was a pointed live-demo critique
  ("we don't want any person to probably click something and go to the internet himself") that
  currently lives only in the transcript, not as a written design principle. Worth its own short
  ADR so it's an enforced constraint on future outreach/tracker UI, not something that has to be
  independently rediscovered.

## Source

See `Meeting notes/` for the full transcript this roadmap derives from.
