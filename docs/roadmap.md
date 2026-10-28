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

## Evidence-Grounded Qualification, Priority Ranking & Drafting — **Done**

Three related upgrades to the judgment/drafting core, shipped together because each one closes a
gap the others exposed:

- **Evidence-grounded qualification** (`qualification/evidence.py`) — a "met"/"not_met" verdict
  must now cite *what it relied on*: a source reference (a company field like
  `company.description`, or a numbered signal `S1`, `S2`, ...) plus a verbatim quote. A quote that
  cannot actually be found in the cited source is not trusted and the verdict is downgraded to
  `could_not_determine` — an unverifiable claim never becomes a PASS or FAIL ("no negative
  evidence" is explicitly not evidence). Same "LLM judges narrowly, code decides/verifies the
  outcome" pattern as every other judgment core in this app.
- **Signal normalization** (`enrichment/signals.py`) — the scraper reads page headings off
  news/careers pages and cannot tell a real headline from a menu entry ("Track shipment", "Go to
  homepage"); context.dev returns real articles but some are personal gossip, not business signals.
  Both sources are now filtered by the same deterministic rules (drop page chrome, require a link,
  drop stale news, de-duplicate across providers, keep the best few, newest first) before anything
  downstream — the qualification prompt, the Priority Score, drafts — ever sees them.
- **context.dev as a second CompanyDataProvider/SignalDataProvider** (`enrichment/providers/
  context_dev.py`, `enrichment/providers/factory.py`, `enrichment/completeness.py`) — a paid API
  (brand/retrieve, web/scrape, news/search), used only to fill gaps the free in-house scraper left:
  a brand lookup when firmographics are too thin, a news lookup when there aren't enough genuine
  signals — never both for a company that already has sufficient data from the free scraper.
  Selected per-org via `settings.company_data_source`; a per-run credit ceiling
  (`context_dev_max_credits_per_run`) caps spend, with usage reported in the run summary. Contacts
  always stay with the in-house scraper regardless of this setting — context.dev doesn't own
  contact extraction.
- **Priority Score ranking** (`qualification/ranking.py`, `orchestrator/ranking_step.py`) — the
  auto-pipeline used to carry qualified companies into role-classification/drafting in whatever
  order discovery happened to return them. Now every judged company gets a pure, auditable score
  (seven weighted, normalized-to-0..1 components; missing data scores a neutral-low value rather
  than being penalized as if it were *known bad*; the weighted sum is then scaled by an evidence
  factor from the weakest hard-criterion's confidence, so a well-evidenced company outranks one
  that merely has more data; a hard FAIL excludes a company outright) and the pipeline's
  drafting cap takes the best-scoring companies first, not just the first N discovered.
- **Evidence-grounded drafting** (`draft/evidence.py`) — the first-touch prompt has always asked
  for "a specific, researched trigger," but the only grounding available was an optional
  `Recommendation`, which the auto-pipeline never actually creates. Drafts now cite facts the
  system *verified*: recent cleaned signals, the qualification points that passed with evidence,
  company size, and the recipient's seniority — formatted for the prompt with an explicit "use
  these, invent nothing else" instruction.
- **Per-search hard requirements** (`MarketFitCriterionIn`/`market_fit_criteria` on
  `MarketDiscoveryConfirmRequest`, `MarketFitRequirements.tsx`) — a rep can now attach one-off hard
  requirements to a single Market Discovery run (e.g. "operates in logistics") that get judged for
  every company in that run alongside the org's saved, reusable qualification criteria, without
  polluting the org-wide criteria catalog with search-specific asks.

`qualification/evidence.py`, `qualification/ranking.py`, `orchestrator/ranking_step.py`,
`draft/evidence.py`, `enrichment/signals.py`, `enrichment/completeness.py`,
`enrichment/providers/context_dev.py`/`factory.py`.

## Rep-Facing Run Worklist — **Done**

The Market Discovery results screen used to be a bare companies list. `GET /market-discovery/
{run_id}/companies` (`ingestion/run_results.py`) now assembles a rep-facing worklist from what the
auto-pipeline already decided — no new judgment happens here, this is a pure read side: a
`ready` list (qualified, with at least one primary-target candidate contact, each with the
evidence a rep needs to pick the right person — role, LinkedIn profile link, email if one was
actually found, and that contact's draft once confirmed) and a `not_shown` list (everything else,
each with a single-sentence reason it didn't make the cut). A draft only ever appears on a
candidate once a rep has confirmed that specific contact. `RunWorklist.tsx`, `RunProgress.tsx`.

## Leadership Dashboard — **Done**

A read-only reporting surface (`dashboard/service.py`, `api/v1/dashboard.py`, `DashboardPage.tsx`
+ its KPI/funnel/cost/attention-queue sub-components) — every function only `SELECT`s, nothing
here can change pipeline data. Reports on either one chosen Market Discovery run or the union of
all runs over a period (7d/30d/all, de-duplicated by company so a company reused across two
searches is counted once): a KPI strip, a discover→qualify→classify→draft funnel, context.dev
credit spend vs. the per-run ceiling, qualification-criteria/role-category breakdowns, an
attention queue (stuck/failed runs, needs-review backlog), and a recent-activity feed. Built for
the "is the pipeline healthy, where did this batch of spend go" question a rep/manager previously
had no way to answer without reading the database directly.

## Multi-Product Pipeline Selection — **Done**

The pipeline only ever accepted one optional product to pitch per run. A rep now selects **one or
more** products at confirm time (Market Discovery confirm, a single company's confirm, and bulk
Needs-Review confirm all take `product_ids: list[uuid.UUID]` now, not one optional id) — useful
once an org's product catalog covers genuinely different pitches for the same company (e.g. a
general digital-transformation service line alongside a specific SAP ECC→S/4HANA migration
offering for the same European logistics ICP).

The draft generator itself picks which **one** of the given candidates best fits each specific
company/contact — never blending more than one service into a single email. It's given a numbered
list of candidate products (each with its own grounding, when a matching `Recommendation` exists)
and returns which option number it chose (`DraftResult.chosen_option`); the caller
(`draft/service.py::generate_draft`) deterministically maps that back to a real `product_id` —
same "LLM judges narrowly, code decides the outcome" pattern as every other judgment core here,
never an LLM-echoed id trusted directly. An out-of-range `chosen_option` is treated as a hard
Gemini-response error, not silently clamped.

Manual, single-product actions (generating a one-off `Recommendation`, drafting a specific contact
from the Run Worklist) are deliberately **unchanged** — that's a rep picking exactly one product
for one person right now, a different interaction from the automated pipeline's multi-candidate
case. `CompanyDetailPage.tsx` previously shared one product-selection dropdown between its
single-product "Generate Recommendation" action and the now-multi "Confirm Company" action; these
are now two independent selections. A small new `ProductMultiSelect.tsx` (a checklist built on the
existing `Checkbox` component) is shared across the three multi-select entry points — no new
design-system primitive, no DB schema change.

## Market Discovery Transparency on Zero Results — **Done**

A real, reproduced edge case: a topic-shaped query (e.g. *"healthcare software companies piloting
generative AI"*) reliably returns editorial/thought-leadership search results rather than actual
company pages, which the extraction stage correctly rejects — but a rep saw nothing but a bare
"0 candidates found," even though the backend had already computed exactly why (a full
raw→extracted→accepted→rejected funnel, each rejection carrying the model's own reasoning) and
simply discarded it before the job returned.

Fixed as pure transparency, no discovery/extraction behavior change: `_run_market_discovery` now
keeps a capped sample of rejection reasons (`rejected_samples`) instead of only a count, and
`MarketDiscoveryPage.tsx` shows a prominent callout with a plain-language explanation plus real
rejected-item reasons whenever `candidates_found` is 0, alongside an always-visible search-funnel
line in "Run details." Separately, `search_gatherer.py`'s fixed 3-template query-variant tuple
gained two directory-biased variants ("list of X vendors", "X providers directory") to give
topic-shaped input a better (not guaranteed) chance of surfacing real companies in the first
place — a small, flagged cost tradeoff (2 more parallel Serper calls per run).

Explicitly scoped out for now, not forgotten: a batch-level "this looks like topic noise, not
company-shaped" signal from the extraction LLM itself, and genuine query reformulation (the LLM
rewriting the query when the first attempt fails) — both real, larger pieces of work, better
judged once this transparency fix shows how often the problem actually recurs in practice.

## Market Discovery Page UX fixes — **Done**

Two small but real gaps found while manually testing the above: the page had no way to abandon an
in-progress parse/confirm and start over except after a run fully finished or failed (`resetSearch`
was only reachable post-completion) — fixed with an always-visible **Reset** button next to Parse,
hidden only while a job is actively pending/running. Separately, clicking Parse or Confirm left
every *other* button on the page (Reset in particular) clickable for the async window before the
request resolved — fixed with one `busy` flag (`parsing || confirming || runInProgress`) gating
every action button and the input textarea consistently, instead of each one checking a different,
incomplete subset of the in-flight states.

## Known mismatches vs. the meeting notes

Called out explicitly here so they don't get silently carried forward:

- **"Everything stays in-tool, no external redirects"** was a pointed live-demo critique
  ("we don't want any person to probably click something and go to the internet himself") that
  currently lives only in the transcript, not as a written design principle. Worth its own short
  ADR so it's an enforced constraint on future outreach/tracker UI, not something has to be
  independently rediscovered.

## Known documentation gaps

- Two code comments reference ADRs that were never actually written: `context_dev.py` cites
  "docs/decisions/0012-context-dev-evaluation.md" and `qualification/ranking.py` cites "ADR 0005/
  0013" for the Priority Score — only `0011` exists in `docs/decisions/` today. Both decisions were
  made and shipped (see "Evidence-Grounded Qualification, Priority Ranking & Drafting" above); the
  write-up just never happened. Flagged here rather than silently fabricated ADR text.

## Source

See `Meeting notes/` for the full transcript this roadmap derives from.
