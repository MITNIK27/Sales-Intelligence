# Sales Intelligence — System Overview

*As of 2026-10-07, branch `feat/new-pipeline`.*

## 1. What this system does

Sales Intelligence automates the manual sales-prospecting workflow Paarth Sahni and Abhas Jain
(InfoBeans) described in their working session (`Meeting notes/Sales Funnel Automation
Discussion...md`): going from "here's the kind of company we want to sell to" to a drafted,
ready-to-send cold email for a named decision-maker at a real company — without a rep manually
searching, judging, classifying, and writing each step by hand.

The product today is a single internal tool (one organization, no multi-tenant auth yet) built
around one capability: **the One-Prompt Pipeline** — type a free-text market description, confirm
the system's interpretation of it once, and everything after that (discovery, qualification, role
classification, outreach drafting) runs automatically as one background job.

## 2. Architecture

**Modular monolith** — one FastAPI deployable, strict module boundaries, no microservices. Each
module under `backend/app/modules/` owns its own models, schemas, routes, and service functions.
Kept this way deliberately for an internal-first tool; a module could be extracted into its own
service later without a rewrite.

**Background jobs, without new infra.** Scraping sites and calling Gemini both take real time and
repeat per company, so nothing runs inline in a request. Instead of Celery/Redis, there's a plain
`jobs` table in Postgres (`pending`/`running`/`done`/`failed` + a JSONB result/error) and a single
asyncio worker process that polls it (`modules/jobs/worker.py`). The frontend polls
`GET /jobs/{id}` to show live progress. This is the one seam where real infra (Celery/Arq + Redis)
would swap in later if volume ever demands it.

**Provider/adapter abstractions** — three areas depend on an interface, not a hardcoded vendor,
because the concrete choice is either swappable or still open:
- `enrichment/providers/` — `CompanyDataProvider`/`ContactDataProvider`/`DomainDiscoveryProvider`/
  `SignalDataProvider`. Real implementation: an in-house scraper (`WebsiteScraperProvider`) plus
  `SerperSearchProvider` (wraps Serper.dev's Google SERP API) for domain lookup and public-web
  company/contact search. LinkedIn itself is never scraped or logged into (ADR 0001) — only what a
  search engine already indexed about it.
- `ai_recommendation/gemini_client.py` — the LLM provider (Google Gemini, free tier) sits behind a
  thin client so prompt/orchestration logic doesn't depend on the specific provider.
- `outreach/` — email only today; WhatsApp/call adapters and LinkedIn send are explicitly
  deferred (Phase E), not built.

**Two genuine multi-step "agents"** (as opposed to simple generator+service modules):
- `discovery_agent/` — turns a market description into real companies via
  gather → LLM-extract → resolve, see §3.
- `orchestrator/` — runs the four pipeline stages in sequence, deciding what to run next based on
  each stage's actual outcome.

## 3. The One-Prompt Pipeline, stage by stage

Entry point: `POST /market-discovery/parse` → `POST /market-discovery/{run_id}/confirm` (the one
remaining manual step — reviewing the parsed criteria before real work starts) → enqueues one
`auto_pipeline` job (`orchestrator/service.py::run_auto_pipeline_job`). The frontend
(`MarketDiscoveryPage.tsx`) polls `GET /jobs/{id}` and renders a 4-stage progress indicator.

### Stage 0 — Parse (inline, not a job)
A single fast Gemini call (`GeminiMarketDescriptionParser`) turns free text like *"SaaS companies
in Bangalore, 50-200 employees"* into `{industry_keywords, location, employee_size_range}`, each
with a `confidence` (`confident` / `could_not_determine`) — low-confidence fields are left blank
for the user to fill in, never guessed. Stored as an `IngestionRun` in `awaiting_confirmation`.

### Stage 1 — Discovery & enrichment (`discovery_agent/` + `ingestion/market_discovery.py`)
1. **Compounding index check** — `search_company_index` first reuses companies this org already
   discovered for overlapping keywords, before paying for a live search. Reduces live-discovery
   calls over time as the org's company index grows.
2. **Gather** (`search_gatherer.py`) — issues several Serper.dev search-query variants for the
   criteria.
3. **Extract** (`extractor.py`, Gemini) — turns raw search results into structured
   `ExtractedCompany` candidates, each with `accepted`/`grounded_in_source`/`reasoning`.
4. **Heuristic backstop** (`heuristics.py::classify_candidate_name`) — catches listicle/article-
   title-shaped names ("Best Logistics Companies in 2026", directory pages, Reddit threads) the
   LLM extraction missed: confidently listicle-shaped → force-rejected before it can become a
   `Company` row; structurally suspicious but not certain → kept but flagged `needs_review`.
5. **Resolve** (`resolver.py`) — finds each accepted candidate's real domain via search, filtering
   out aggregator/social domains that rank for company searches but aren't the company itself
   (`settings.market_discovery_domain_denylist`: LinkedIn, Crunchbase, Glassdoor, Indeed, etc.).
6. For each new candidate: `get_or_create_company` (deduped by domain), then full enrichment
   (`_enrich_company` — website scrape + Serper-based public-search contact discovery) runs
   immediately, not as a separate step.
- A candidate's `needs_review` flag now comes from the discovery agent's own per-candidate
  confidence signal, not a blanket `True` for everything created by Market Discovery (a real bug
  fixed recently — see §6).
- Failure here is loud, not silent: a broken discovery run raises, it never quietly returns zero
  candidates.

### Stage 2 — Qualification (`qualification/`)
Judges every discovered-or-reused company against the org's **active** `QualificationCriterion`
rows. The LLM only judges each criterion individually
(`met`/`not_met`/`could_not_determine` + evidence-grounded reasoning); the **overall verdict is
computed deterministically in Python**, never by the LLM — only `is_disqualifying` criteria can
flip it to `not_qualified`; non-disqualifying criteria are informational context for the rep.
Every check is append-only (`QualificationResult`) — re-checking never overwrites history. A
company that clears qualification gets **ranked** (`orchestrator/ranking_step.py`) against the
requested keywords/size, not just taken in discovery order, before the capped set moves on.
Skips cleanly (not a failure) if the org has zero active criteria.

### Stage 3 — Role classification (`role_relevance/`)
For each qualified company's contacts, matches each one to the best-fitting
**org-configurable** `RoleCategory` by inferred function rather than title keyword-matching (a
"VP Engineering" and a "Head of IT" at different companies both need to resolve to the same
function). `priority` (`primary`/`secondary`/`not_relevant`) is again computed deterministically
from the matched category's `is_primary_target` flag, not decided by the LLM. Append-only
(`RoleRelevanceResult`). A company still flagged `needs_review` is skipped here on purpose, not
silently bypassed — bad data never reaches a customer-facing draft. Bounded to
`settings.auto_pipeline_max_companies_to_draft` (default 5) qualified companies per run, to
protect the shared Gemini free-tier daily quota from one broad prompt exhausting it.

### Stage 4 — Drafting (`draft/`)
For every contact classified `primary` in stage 3, generates a first-touch cold email
(`GeminiDraftGenerator`): max 7-8 lines, explicit structure (credibility → a proof point grounded
in an existing `Recommendation` for that company+product when one exists, never hallucinated when
one doesn't → one CTA). Written in whichever register (`business`/`technical`) the matched role
category's `framing_style` specifies — not inferred by the LLM. Requires a `product_id` (the pitch
target) — if none was given at confirm time, this stage reports itself skipped rather than
guessing which product to pitch. A `Draft` is mutable: a rep edits subject/body before clicking
"Log as Sent," which creates an `OutreachActivity` linked back to the draft and flips it to `sent`.

**Every stage reports `{"ran": bool, ...}` or `{"ran": false, "skipped_reason": ...}`** — a missing
prerequisite (no active criteria, no active role categories, no product) skips just that stage and
is reported, never aborts the whole run.

## 4. Supporting mechanics (independent of the pipeline)

- **Tracker & cadence** (`outreach/`) — logging a `sent` or `response_received`
  `OutreachActivity` auto-derives the contact's status and next-follow-up date/channel via a
  pure, deterministic send-window rule (`cadence.py::next_send_window_slot`: Monday-Wednesday,
  Thursday only if urgent, never Friday/weekend, 11:00 in the contact's own timezone). No LLM
  involved. A/B variant data (`template_variant`) is captured on every logged send; aggregate
  reporting on it is deliberately not built yet.
- **Needs Review + bulk confirm** — `POST /enrichment/needs-review/confirm-bulk` clears
  `needs_review` on a batch of companies/contacts in one job and, per company, resumes role
  classification/drafting exactly like confirming one company at a time does
  (`classify_and_draft_company`).
- **Ad hoc / quick qualification check** — type a company name/domain that may not exist yet;
  resolves-or-creates it, enriches it, and judges it immediately (`POST /qualification/check`) —
  for "someone just mentioned this company, is it worth pursuing right now."
- **Companies list** — sortable/paginated server-side (`name`/`created_at`/
  `last_enriched_at`/`enrichment_status`/`qualification`), with a qualification-verdict column
  joined without N+1.

## 5. What's currently configured in this org

(Live DB state, single org `00000000-0000-0000-0000-000000000001`.)

**Product** (1 — auto-selected by the pipeline's product dropdown):
- *InfoBeans - Digital Transformation & Product Engineering* — service lines: Salesforce (280+
  specialists, 2,000+ implementations, incl. Agentforce/Data Cloud/MuleSoft/Tableau), ServiceNow,
  AI & Generative AI (InsaneSDD, Expona AI, BeanTrail), enterprise app development/cloud
  migration/modernization/DevOps. Drafting pitches whichever line best matches the prospect's
  evident need.

**Qualification criteria** (2, both active, both non-disqualifying):
- *Digital transformation maturity* — evidence of an active DT/modernization initiative.
- *Operates in Europe* — worded specifically around the European parcel/postal market (a holdover
  from early postal-industry test runs, not a generic geography filter — worth broadening if
  future runs target non-logistics verticals).

**Role categories** (6, all active):
- Primary targets: *IT / Engineering Leadership*, *Vendor / IT Procurement*,
  *Digital Transformation / Innovation*.
- Secondary: *Business / P&L Leadership*, *Marketing*, *Product Management*.

**Test history so far**: 5 Market Discovery runs (mostly "postal/parcel industry in Europe,
digital transformation" variants, plus one fintech/Salesforce/Indore query), ~22 companies, one
company carried all the way through qualify → role-classify → draft.

## 6. Status: done vs. deferred

| Area | Status |
|---|---|
| A1 Company Discovery Agent | Done |
| A2.1-A2.4 Qualification (criteria, judgment, ad hoc check, bulk surfacing) | Done |
| A3 Role-Relevance Classification | Done |
| Phase C Tracker & Cadence | Done |
| Phase B Outreach Draft Generation | Done — **email only**, LinkedIn deferred |
| One-Prompt Pipeline Orchestration | Done |
| Companies list sorting/pagination | Done |
| In-house search-based contact discovery | Done |
| `needs_review` over-flagging fix + bulk confirm | Done |
| A/B template testing | Data capture flowing; aggregate reporting deferred |
| Phase D — domain-agnostic workflow generalization | Not started, deliberately deferred |
| Phase E — LinkedIn/Gmail channel integrations | Not started, deliberately scoped (Gmail send identified as the higher-value next step; personal LinkedIn connection explicitly ruled out) |
| Phase 5 Contact verification | Deferred |
| Phase 4 Credits & usage tracking | Built but not a current focus |
| Phase 7 SaaS readiness (multi-tenant auth) | Deferred until there's reason to pursue it |

## 7. Known gaps worth tracking

- **"Everything stays in-tool, no external redirects"** was an explicit live-demo critique in the
  source meeting, but exists only in the transcript today, not as a written design constraint —
  worth its own ADR so future outreach/tracker UI doesn't silently violate it.
- **"Operates in Europe" criterion** is worded around the parcel/postal vertical specifically —
  harmless today (non-disqualifying), but will produce irrelevant-sounding reasoning if qualifying
  companies outside that vertical; worth rewording if the ICP broadens.
- **Discovery noise** — some discovered "companies" are actually listicle/article titles or forum
  threads that slipped past both the LLM extraction and the heuristic backstop (e.g. a Reddit
  thread, "Best Logistics Companies in 2026") — caught as `needs_review` but still worth an
  occasional manual sweep of the Needs Review queue.
- One earlier discovery run with near-identical wording to a successful one returned 0 accepted
  candidates (8 extracted, all 8 rejected) — not yet root-caused; worth reproducing deliberately if
  it recurs.

## Sources

- `docs/roadmap.md` — the authoritative feature-level roadmap this section summarizes.
- `docs/architecture.md` — module boundaries and infra phases.
- `docs/data-model.md` — full entity/field reference.
- `docs/decisions/0001` through `0011` — ADRs for each major design choice referenced above.
- Live Postgres state (`products`, `qualification_criteria`, `role_categories`, `companies`,
  `ingestion_runs` tables) for §5.
