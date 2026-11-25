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

## Our Offerings — Website Import with Review — **Done**

The catalog of what InfoBeans sells (formerly Products) now keeps itself in step with the company
website, as proposals a person approves. Design in [`architecture.md`](architecture.md) ("The
Offerings Importer"); entities in [`data-model.md`](data-model.md).

- Services and Products tabs; a "Check for updates" button plus an automatic weekly check run by
  the worker; hand-added entries are kept and marked Manual.
- Page ledger with a sitemap `lastmod` gate, so unchanged pages cost no scrape and no model call;
  a blog-post lane screened by a light model; discovery driven by the website menu, with nothing
  hard-wired to named products.
- Trust layer: a "What was checked" coverage view, website-menu reconciliation, a grounding check
  with a source excerpt on every proposal, and a read-only audit script.
- Removals only when a page really answers 404 or 410; a run that read nothing fails instead of
  proposing removals.
- Groq-first structured LLM seam (Gemini fallback); context.dev as the primary page reader with the
  in-house scraper as fallback.

## Quick Check, Role Targets, Verify Contacts — **Done**

- **Quick Check** takes one field (company name or website) and an optional focus area, keeps its
  inputs, and shows a progress card with steps and a timer. The focus steers the fit judgment and
  adds a focused web search as evidence; it is stored on the result.
- **Role categories** no longer ask for a primary target. Target roles are chosen, optionally, per
  Market Discovery run; with none chosen every matched contact counts and the rep confirms the ones
  they want.
- **Verify Contacts**: the offerings picker is a compact popover instead of an always-open list.

## Drafting by Email Type and Offering Kind — **Done**

- First touch, Follow-up 1, 2 and 3. Handing the email on to someone else is allowed only from
  follow-up 2; the picker starts on the next email in the sequence, based on emails already logged
  as sent.
- Each offering is described to the model as a product (offer a walkthrough or demo) or a service
  (offer a short conversation), written from the buyer's point of view.
- Follow-ups are given the earlier emails to the same person so they add something new.

## Opportunity Research — **In progress**

- **Done:** opportunities per company and area, stable evidence references with verbatim-quote
  checking, a code-decided verdict, versioned cached assessments, area suggestions from evidence,
  and Quick Check driving all of it (phase 1); research collectors for news, job boards and web
  announcements with freshness windows, stated gaps and hiring counts over time (phase 2).
- **Phase 3 built:** offering fit (a free shortlist, one grounded model call, band and score
  computed in code), contacts matched to the opportunity from title and offering profile only (no
  names sent) with human overrides kept beside the model's view, an area-aware contact search when
  too few relevant people are known, recommendations made once per assessment version, and drafts
  that can be written for an opportunity. Quick Check shows the fit, the people and the
  recommendation under each area.
- **Phase 4 (built, not yet run against real data):** the Company Brief on the company page and in Quick Check: separate industry, area and offering selectors (area and offering live in the address), a hand-built SVG map from evidence to engagement (verified, inferred and unsupported links drawn differently, gaps shown as placeholders), a text view of the same facts, an evidence panel, compare views for two offerings or two areas, and a copyable one-page brief. `POST /companies/{id}/opportunities` starts an area.
- **Phase 5 (built, not yet run against real data):** after ranking, a run queues one light fit job per ranked company (up to `auto_pipeline_max_companies_to_draft`) for the run's chosen offerings, without contact search and outside the pipeline's stages, so it can never fail or slow a run. Worklist links carry `?run=<id>`; the company page reads the run's offerings (`GET /market-discovery/{run}/offerings`), starts with them selected and labels fits "Chosen for this run" or "Also fits". "Suggest other areas" (`POST /companies/{id}/opportunities/suggest`) saves areas the evidence points to, once per company.
- **Phase 6 (done, apart from the real-data review):** (1) the dashboard's Cost and health panel shows 30-day estimated spend by provider (`GET /usage/summary`); (2) `python scripts/usage_report.py --review` prints average cost per researched company, the most expensive companies, the failed-call rate and the top cost lines beside the plan's estimates, so the cost review is one command once real runs exist; (3) the structured-output seam has a per-vendor personal-data flag: `build_structured_llm(..., personal_data=True)` drops vendors not cleared to receive names or emails, Groq stays excluded until `GROQ_MAY_RECEIVE_PERSONAL_DATA=true` is set after a privacy review, and a chain left with no cleared vendor fails instead of leaking; (4) the new screens use the app's own select component rather than the browser's.
- **Cost review, to do after the real test runs:** run `python scripts/usage_report.py --days 7 --review` and compare with the plan's estimates (about $0.02 to $0.04 per researched area, about $0.005 per fit judgment, about $0.03 to $0.05 per Quick Check brief). Then decide the open items: a paid Gemini key for prompts that carry personal data, and whether Groq may receive any.
- **Phase 7 (done):** "AI Recommended Areas" on the Brief tab: a button that shows chips (an area and a one-line reason) suggested from the evidence on file, becoming "Refresh AI Recommendations" once chips exist. Refresh makes a fresh model call and replaces the chips; if it fails or returns nothing new the old chips stay, repeat clicks while running are ignored, and reopening the tab makes no model call.
- **Deliberately not done:** moving the six older direct Gemini call sites (market parser, qualification, role relevance, recommendation, draft, discovery extraction) behind the Groq-first seam. They are metered and all go through the single `generate_structured()` helper now (see AI Governance below). Moving them changes the model settings (the seam uses temperature 0) and can change wording, and four of them handle personal data, so it needs a side-by-side check on real output first. It is a separate change, not polish.

## "Not a Fit" (governance Phase 4a) — **Done**

Mark a company out so it stays out. Design in [`architecture.md`](architecture.md) ("Not a Fit and the Review Log"); fields in [`data-model.md`](data-model.md).

- Dismiss and restore a company, singly or in bulk, with a reason from a short fixed list and an optional note; hidden from lists by default (`dismissed=hide|include|only`).
- Left out of every automatic path (auto pipeline, bulk qualification and scrape, contact verification, Needs Review, follow-up reminders, dashboard figures, run results) and out of the discovery reuse index. A later Market Discovery run that finds it again counts `skipped_dismissed`. Drafting and role classification are refused until it is restored.
- A company with logged outreach or sent drafts is not dismissed until the person confirms: the screen warns, and the server answers 409 without the confirmation.
- Screens: a "Not a fit" button on the company page, the Run Worklist and the companies list; an Active / Not a fit toggle with Undo; a banner on a dismissed company; what Quick Check said about the site shown on the company page.
- **Not built (Phase 4b):** a Market Discovery judge that reads the note and the saved discovery evidence to explain why the search got it wrong.

## Run Screen and Company Page Tidy-up (Phase 7) — **Done**

- Honest progress: stages name the company being worked on and keep a short trail of real events; "Starting…" only appears while a job waits for the worker.
- A finish summary (headline, Found > Fit > People sorted > Ready, next step); "Ready for you" as compact cards with logo, score and why it fits, opening details in a dialog; companies not shown are listed in a highlighted box with the reason; the "run limit" skip reason says what it means and what to do; the draft button reads "Write draft".
- Company page: the unused "Choose offerings" dropdown beside Confirm Company is gone; "Not a fit" looks like a button. Companies list sorts by last discovered, newest first. Select dropdowns open under their trigger.
- `backend/scripts/delete_companies_before.py` removes companies discovered before a date with their dependent data (dry run by default; `--yes` asks for the count).

## AI Governance (controls G1 to G10) — **Phases 0 to 7 built; see the file for status**

Rules, status of each control and the check that enforces it are in [`ai-governance.md`](ai-governance.md) ([ADR 0014](decisions/0014-ai-governance.md)). Shipped between 2026-11-04 and 2026-11-16:

- Phase 0 to 1: the controls and key-free checks (`backend/governance_checks/`); every Gemini call through `generate_structured()` with an output cap and a repair retry; cached and thinking tokens logged; `model_used` and `prompt_version` on every AI-written row; model calls from web routes named `api:<route>`.
- Phase 2: outside text fenced in every prompt (`llm/untrusted.py`); finished drafts checked for invented figures and past-work claims (`draft/claims.py`, "Check before sending").
- Phase 3: the eval harness (`backend/evals/`, now 68 cases and thirteen tasks, reports, `--repeat`, spreadsheet labels); the review decision log (`modules/review/`); every measured prompt version needs an eval report.
- Phase 4a: "Not a fit" (above). Phase 5 prep and 6: failure reasons stored on failed calls (`api_usage.error`), the Gemini price check, clean types and CI, and the reusable `ai-project-governance` skill (`docs/skills/`).
- **Open:** first reports for the three tasks still without one (opportunity assessment, contact relevance, role relevance); accuracy against real labelled companies (needs labels from the team); temperature 0 for judgments (an experiment, to be measured); a spending ceiling (deferred to a paid key); confirming Groq's terms before it may see personal data; the Market Discovery judge (Phase 4b).

## Database Foundation and Documents Knowledge Base (Phase 8) — **Done**

- **8a, database foundation** ([ADR 0016](decisions/0016-database-foundation.md)): PostgreSQL 16 with
  pgvector, managed by us; JSONB, CHECK constraints and indexed foreign keys; an owner and an app
  role with set timeouts; tests on real Postgres; backups with a restore check; the data-safety
  protocol for every migration ([runbook](database-runbook.md)); the `users` table ready for
  Firebase sign-in.
- **8b, documents library:** upload decks, PDFs, Word, Markdown and text (5 MB by default), read in
  the background into pages and passages, with versions, an activity log, an audit trail that
  outlives deletes, optional Gemini descriptions of pictures, and no original file kept.
- **8c, search:** Gemini embeddings and pgvector search merged with full-text search; a search box
  on the Documents page that says when it is searching by words only.
- **8d, knowledge in the flows:** offering fit, the recommendation, area suggestions and Quick
  Check are shown the best passages (Gemini only), cite them as K1, K2..., and show "From our
  documents" links; passages are never evidence about a company.
- **8e, summaries and knowledge cards:** a summary per document and section and short facts
  checked against their passage, shown to the flows first; a person can hide a wrong card;
  documents tied to an offering can propose a better description, applied only on approval.
- **8f, release:** ADRs 0015 and 0016; a governance check that nothing from the documents reaches
  a vendor other than Gemini; eval tasks for knowledge cards and picture descriptions (every prompt
  in the app now has one); load and failure tests (a large library, broken files, spent quota, a
  dead worker, a document deleted mid-job); documents, meaning search and summaries on by default.
- Open: confirm the PyMuPDF licence in writing before serving anyone outside InfoBeans (ADR 0015).
- First reports: `knowledge_cards` 8/9 (one offering description left out "Azure"),
  `picture_description` 6/6.

## Sign-in, Access and Roles (Phase 9) — **Done**

- **Sign in with Google** through Firebase Authentication, InfoBeans accounts only
  ([ADR 0017](decisions/0017-sign-in-and-access.md)). The API checks each request's token against
  Google's certificates; no service-account key.
- **Invite only.** Admins and managers give access by email and role on **User Management**; no
  email is sent. Someone without access sees the app frame with only the Dashboard and can
  **Request access**; requests wait on User Management with a badge. The first admin comes from
  `AUTH_BOOTSTRAP_ADMINS`.
- **Roles** in one table: reps are kept out of User Management and costs; managers cannot make,
  change or deactivate admins; nobody changes their own role. People are deactivated, never deleted.
- **Who did what** on uploads, the document history, review decisions, searches, jobs and AI calls.
- A governance check calls every endpoint without signing in and fails if any lets it through.
- New top bar (wordmark, New search, account menu) and a Profile page.
- Open: email to admins about access requests (needs an approved mailbox); restricting the
  Firebase web key and adding the real domain at deployment.

## Planned Next

- **Gmail**: send from the app and see replies. Needs its own Google consent with offline access
  (sign-in does not give lasting mailbox access), stored encrypted; its own ADR.
- **Separate organisations** before anyone outside InfoBeans uses the app, and per-person visibility
  if reps should see only their own work.

- **Fit for sales and customer-success reps**: plan the daily routine of each role and cut the steps
  between "I have a company or a list" and "I sent a good email". To be scoped from how each role
  actually works.
- Move the other Gemini call sites behind the structured LLM seam, Groq first, one task at a time
  after a side-by-side comparison on real data (all already go through `generate_structured()`).
- Close the AI governance open items (see "AI Governance" above): first eval reports for the three tasks without one,
  labelled-company accuracy, and the Market Discovery judge.
- Make CI mean something: the unit and frontend tests are git-ignored, so CI runs only the
  governance checks.
- Branding and positioning (briefing material is kept locally and is not committed).
- A graph view over knowledge cards (clients, industries, offerings), built from the columns the
  cards already keep. The vector index is done (Phase 8).
- Deployment (hosted API, worker and database) with spend caps and separate keys; sign-in and
  access control are done (Phase 9).

## Known mismatches vs. the meeting notes

Called out explicitly here so they don't get silently carried forward:

- **"Everything stays in-tool, no external redirects"** was a pointed live-demo critique
  ("we don't want any person to probably click something and go to the internet himself") that
  currently lives only in the transcript, not as a written design principle. Worth its own short
  ADR so it's an enforced constraint on future outreach/tracker UI, not something has to be
  independently rediscovered.

## Known documentation gaps

- No ADR yet for the offerings importer (page ledger and verification layers), for qualification
  states, for Quick Look or for "Not a fit"; the design is described in `architecture.md` for now.
  AI governance has its own record ([ADR 0014](decisions/0014-ai-governance.md)), which used that
  number so 0012 and 0013 stay free; Phase 8 added [ADR 0015](decisions/0015-documents-knowledge-base.md)
  and [ADR 0016](decisions/0016-database-foundation.md), Phase 9
  [ADR 0017](decisions/0017-sign-in-and-access.md).
- Two code comments reference ADRs that were never actually written: `context_dev.py` cites
  "docs/decisions/0012-context-dev-evaluation.md" and `qualification/ranking.py` cites "ADR 0005/
  0013" for the Priority Score — only `0001` to `0011` and `0014` exist in `docs/decisions/` today. Both decisions were
  made and shipped (see "Evidence-Grounded Qualification, Priority Ranking & Drafting" above); the
  write-up just never happened. Flagged here rather than silently fabricated ADR text.

## Source

See `Meeting notes/` for the full transcript this roadmap derives from.

## Company Brief v2 (after the first browser test)

Built from the user's review of the first version (see the plan file). Not yet seen in a browser.

- **People search uses the role categories.** The titles searched for are the examples after "e.g." in each active role category's description (`role_relevance/titles.py`), first-reach categories first, plus the roles an offering is sold to from its buyer profile. Nothing is built in except a short list of seniority words used to recognise a senior role in a result. Up to three Serper queries per company; the share of results lost at each step is recorded and shown ("People search: 10 results, 3 profiles, 0 kept"). `scripts/contact_search_probe.py` shows this for one company (real calls, run by a person).
- **Offering filter.** Quick Check takes the offerings to check fit for (`product_ids`); the company page's Brief uses the same filter, kept in the address and remembered in the browser; a company opened from a Market Discovery run starts with that run's offerings. With nothing chosen only the single best match is judged. Runs made before run context was stored have no offerings, so their filter starts empty (stored data is never edited).
- **One Brief** (`frontend/src/features/brief/`) for Quick Check and the company page: sticky filter bar (offering, area), a three-fact verdict strip, the hierarchy map always open (evidence, area, offering, buying committee in tiers, outreach), then Why now, Buying committee (decides, influences, evaluates and uses, most senior first, "start here" marked), Recommended approach, What we could not find, and "Recommend on a different basis?".
- **Controls:** `FilterButton` and `Segmented` look and behave as controls; `StatusTag` (dot and word, no border) is used for read-only statuses so they are never mistaken for buttons.

## Repair pass: silent failures, readable values, one source of truth, workflow graph

- **Failures are visible.** An analysis that judges nothing now says why (no active offerings, or none
  stood out), the Quick Check shows the lookup, fit and opportunity problems under the results, a
  repeat check judges newly chosen offerings, and the people search says when it found nobody.
- **Deletes cannot 500.** Deleting a person also removes their buying-role judgments; deleting a
  role category clears the link on earlier classifications; an offering that has been analysed,
  drafted for or recommended is refused with "archive it instead". A foreign-key failure is no
  longer reported as "already exists".
- **Readable values.** Dates, times and job states go through `lib/format.ts` (text that is not a
  date is shown as it came, never guessed into one); failed loads say so with a Retry; unknown
  keys are made readable.
- **One source of truth.** A role set in the Brief shows on the People tab and in the stepper; the
  Brief refreshes the company page after changes; with no older classification a draft's tone
  follows the person's role in the opportunity.
- **Opportunity flow.** The SVG map is replaced by four numbered steps (what they are doing, what we
  would sell, who to talk to, what to say) with labelled arrows, status words, visible gaps and a
  detail panel, built from HTML so text wraps. Pure model: `features/brief/flow/flowStages.ts`.
- Not done here: drafts still do not read the opportunity's evidence (only its role), and the draft
  form does not send `opportunity_id`; the paid people-data provider question is still open.

## Quick Check v2: a short answer from a company name
Quick Check is now a look-up: type a name, get what the company does, how it relates to our offerings and a clear Yes / Maybe / No call, in about 10 to 20 seconds. Nothing is added to the companies list until the person clicks "Save to my companies" or "Go deeper" (which also starts research on the company page). Under "Advanced" the person can add an area to research and their own criteria (ticked from saved ones or typed for this search). They are optional, informational and never change the call. The old criteria-gated full check is no longer part of Quick Check.
- Backend: `modules/quicklook/` (resolve, snapshot, service), `POST /quick-look`, `POST /quick-look/save`, `GET /quick-look/{id}`; new table `company_snapshots` (migration `e2f7a9c14b68`, run `alembic upgrade head`).
- Which company: scored by name match against the website, plus a small bonus for results about what we sell. A clear winner is picked; otherwise the person chooses. "Not this one?" lists the other matches or takes a pasted website.
- The call is computed in code, not by the model: Yes needs a strong fit proven by a quote on the company's own site; a strong fit from search results alone is a Maybe; thin evidence is "not enough information".
- Answers are cached per website for 7 days, and go stale when the offerings change.

## Criteria are optional per search and informational on a company
Saved qualification criteria are no longer applied automatically anywhere.
- **Market Discovery:** the confirm card lists saved criteria unticked. Only ticked ones (plus ones typed for that search) are judged, and each can be marked "Must have" for that search; only must-haves can drop a company. The choice is stored on the run (`context.criteria`, with the saved name and description copied at confirm). With none chosen, the run still completes: companies get the new verdict `not_checked`, are ranked by offering fit, and none is excluded.
- **Company page:** "Check against criteria" lets the person pick criteria (saved ones by id, or typed) and shows Met / Not met / Could not determine for each. The stored verdict is `not_checked`, so it never reads Qualified or Not qualified.
- **"Hard requirement" is now "Must have"** on a saved criterion: only the default for a search's must-have switch. No database change (`is_disqualifying` is the same column).
- Backend: `run_qualification_check` takes the criteria explicitly; `resolve_run_criteria` / `build_run_criteria` build them; the confirm payload field `market_fit_criteria` became `criteria`.

## After the FedEx test: evidence, honest calls, offer ideas
- **Blocked sites:** `looks_blocked` (in `enrichment/signals.py`) recognises access-denied / bot-check pages. They are never kept as a company description (a re-scrape replaces one that was), never trigger "enough data" (so the context.dev fallback runs), and are never used as Quick Check evidence.
- **Page refresh:** a company page that arrives with enrichment "pending" (for example after Go deeper) now watches it every 2 seconds and updates by itself when the scrape finishes.
- **Quick Check:** besides the homepage and search snippets it reads recent news, open jobs and a related-work search (company name plus our offering areas). The card shows "What they are working on" and "What we could offer", each backed by a verified quote with its source and date. The call is "Yes", "Maybe", "No clear opening yet" or "Not enough information"; a Yes needs a real quote from their site, a news item or a job posting.
- **Brief:** the filter is "Our offerings". Picking an offering with no brief open offers "Create a brief around <offering>?". The overall view has "Research what we could offer" (new job `company_offers`, `POST /companies/{id}/opportunities/offers`): it researches the company in the areas we sell in and judges every active offering, not a word-match shortlist.

## Brief redesign: only what exists, a real map, clearer names
- A new area shows one "Research <area>" card (named steps while it runs). After research the Brief is a stack of collapsible sections, each hidden when it has nothing to say: What <company> is doing, Connection map, Best offering to lead with (holds the "Work out the best offering" button), Who to start with, What to say, Gaps in the research, Try another angle. The Opportunity / Lead offering / People strip is gone.
- **Connection map** (`brief/graph/`, React Flow `@xyflow/react`, loaded only when opened): company, their findings (news, hiring, initiative, partnership, technology), our offerings, people by tier, and the message. A finding is joined to an offering only where the fit cites the same evidence; dashed lines are inference or "not found yet". Drag, pan, zoom, hover to light up a path, click a box for its quote or reasoning; "Show as a list" for keyboards and small screens.
- **Buying committee** moved to the People tab (`PeopleCommittee`) and no longer lists people twice: it ranks them for the first researched area (or `?area=`) and the one list of people below shows each person's part as a chip in front of the name (Decides, Influences, Would use it, Not involved, Not judged yet), with "Start here", the reasoning and a role selector on their own card, in committee order. The Brief keeps a one-line "Start with <name>" that links there.

## Personal criteria, researched-only drafts, one Outreach tab
- **Criteria are personal now.** The Qualification Criteria page, the saved list and its endpoints are gone. Criteria are typed where they are used and kept on the company (`companies.criteria`, migration `a7c3e9d15b24`): on the company's Overview ("Criteria for this company", `PUT /companies/{id}/criteria`, then "Check this company"), in a Market Discovery search (the criteria are also written onto every company the run finds), or in Quick Check's Advanced box (copied onto the company when saved). The `qualification_criteria` table is kept for now; the checks build temporary criteria from the typed ones.
- **Why "Not worked out yet" did nothing:** the offering shortlist was a pure word match, so a company sharing no word with any offering got no judgement at all. When nothing is chosen and nothing matches, the model now names the offerings worth judging (`opportunity/pick.py`, ids checked against the catalogue; if it cannot answer, the first few offerings are judged), and each is still judged against evidence.
- **Drafts follow the Brief.** A contact's "Write a draft" lists only the offerings already researched for the company, best fit first and preselected as the recommendation. With nothing researched it lists everything, seven at a time. The shared `OfferingPicker` (researched group, seven at a time on scroll) is also used on the Recommendations tab.
- **Outreach** replaces the Drafts and Follow-ups sidebar items: one page with Drafts and Follow-ups tabs (`/outreach?view=`), ready for sent mail and replies once Gmail is linked. `/drafts` and `/follow-ups` redirect there.

## Brief starts from the Market Discovery search
- **Discovery always searches globally.** It used to fill its 10-company quota from companies already in the database (a loose keyword match) before searching the web, so a stress run could show only companies you already had. The index step is gone; a found company you already have is matched by domain and linked to the run, not duplicated.
- **The Brief opens with the answer.** `GET /companies/{id}/search-context` reads the company's own run memberships (not the `?run=` address) and returns what was searched, the run's criteria and, per offering searched, the stored fit (band computed in code), reasoning, quotes and a state (judged, being worked out, not checked). The card "From your Market Discovery search" shows it above the recommendations.
- **The searched offerings are researched for real.** After ranking, the top companies (`run_area_research_company_limit`, default 5) get the first few run offerings (`run_area_research_offering_limit`, default 3) researched in their own area, then judged. Capped because each is several model and search calls.
- **One recommendation list, in order.** The two buttons were the same job. Now one control suggests: first the areas searched in Market Discovery (reason built in code from the stored fit), then evidence-backed areas connected to those offerings or to ones selected on the Brief, then next best areas when the searched fit is low or unchecked. Pass 1 proposes with verified quotes, pass 2 (`judge_areas`) maps each area to an offering and drops unsupported ones, pass 3 widens only when needed. Code decides the order. Rows record source, rank and a focus hash (migration `c4d8e2f61a93`), so a list made for other offerings is not reused, and the screen says in a sentence what happened.

## Describe your message: change a draft without leaving the tool
- **Flow.** Generate the draft as before. Under it a "Describe your message" box appears: type what to change, or press a chip (Shorter, More formal, Friendlier, Plainer words, Stronger opening, Softer ask). The draft is rewritten in place from the text on screen (hand edits included), and a line says what changed and how the length moved ("Shorter: 88 to 61 words"). **Undo** goes back one version. The same box is on the contact card, the Drafts page and the run results window.
- **Rules that do not move.** The structure stays (a specific opening, who we are, one grounded proof point, a soft next step), first name only, nothing invented. The rep's request can change tone, length, order, emphasis and add facts they state. The rewritten text is checked for invented claims again; a fact the rep typed is not flagged. A rewrite never sends anything, and it needs a confirmed contact like generation.
- **Under the hood.** `POST /drafts/{id}/refine` and `/undo`; `draft/refine.py` has its own prompt and `REFINE_PROMPT_VERSION`, so the first-touch and follow-up templates are untouched. Migration `e3b9d5a14c70` adds `drafts.instruction` and `drafts.revisions` (the last ten replaced versions). New eval task `draft_refine` (4 cases) is waiting for its first report with real models.

