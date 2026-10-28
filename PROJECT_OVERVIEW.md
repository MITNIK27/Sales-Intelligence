# Sales Intelligence — System Overview

*As of 2026-10-20, branch `feat/new-pipeline`.*

## 1. What this system does

Sales Intelligence automates the manual sales-prospecting workflow Paarth Sahni and Abhas Jain
(InfoBeans) described in their working session (`Meeting notes/Sales Funnel Automation
Discussion...md`): going from "here's the kind of company we want to sell to" to a drafted,
ready-to-send cold email for a named decision-maker at a real company — without a rep manually
searching, judging, classifying, and writing each step by hand.

The product today is a single internal tool (one organization, no multi-tenant auth yet) built
around one capability: **the One-Prompt Pipeline** — type a free-text market description, confirm
the system's interpretation of it once, and everything after that (discovery, qualification,
ranking, role classification, outreach drafting) runs automatically as one background job. A
read-only leadership dashboard reports on how that pipeline is doing across searches.

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

**Provider/adapter abstractions** — areas that depend on an interface, not a hardcoded vendor,
because the concrete choice is either swappable or still open:
- `enrichment/providers/` — `CompanyDataProvider`/`ContactDataProvider`/`DomainDiscoveryProvider`/
  `SignalDataProvider`. **Two** `CompanyDataProvider`/`SignalDataProvider` implementations exist
  now, chosen per-org via `settings.company_data_source` (`enrichment/providers/factory.py`):
  the free in-house scraper (`WebsiteScraperProvider`) alone, or that scraper first with
  **context.dev** (`context_dev.py`) filling only the specific gaps it left (a paid brand lookup
  when firmographics are thin, a paid news lookup when there aren't enough genuine signals — never
  both for a company that already has sufficient free data; `enrichment/completeness.py` decides
  "sufficient"). A per-run credit ceiling caps spend either way. Contacts always stay with the
  in-house scraper regardless of this setting. `SerperSearchProvider` (wraps Serper.dev's Google
  SERP API) handles domain lookup and public-web company/contact search throughout. LinkedIn itself
  is never scraped or logged into (ADR 0001) — only what a search engine already indexed about it.
- `ai_recommendation/gemini_client.py` — the LLM provider (Google Gemini, free tier) sits behind a
  thin client so prompt/orchestration logic doesn't depend on the specific provider.
- `outreach/` — email only today; WhatsApp/call adapters and LinkedIn send are explicitly
  deferred (Phase E), not built.

**Two genuine multi-step "agents"** (as opposed to simple generator+service modules):
- `discovery_agent/` — turns a market description into real companies via
  gather → LLM-extract → resolve, see §3.
- `orchestrator/` — runs the pipeline stages in sequence, deciding what to run next based on each
  stage's actual outcome.

## 3. The One-Prompt Pipeline, stage by stage

Entry point: `POST /market-discovery/parse` → `POST /market-discovery/{run_id}/confirm` (the one
remaining manual step — reviewing the parsed criteria before real work starts) → enqueues one
`auto_pipeline` job (`orchestrator/service.py::run_auto_pipeline_job`). The frontend
(`MarketDiscoveryPage.tsx`) polls `GET /jobs/{id}` and renders a stage-by-stage progress indicator.

### Stage 0 — Parse (inline, not a job)
A single fast Gemini call (`GeminiMarketDescriptionParser`) turns free text like *"SaaS companies
in Bangalore, 50-200 employees"* into `{industry_keywords, location, employee_size_range}`, each
with a `confidence` (`confident` / `could_not_determine`) — low-confidence fields are left blank
for the user to fill in, never guessed. Stored as an `IngestionRun` in `awaiting_confirmation`. At
confirm time, a rep can also attach one-off **hard requirements specific to this search**
(`market_fit_criteria`, via `MarketFitRequirements.tsx`) that get judged for every company in this
run alongside the org's saved, reusable criteria — without polluting the org-wide criteria catalog
with search-specific asks. A rep also selects **one or more products** to potentially pitch (see
Stage 4 — this used to be a single optional product, now a list).

### Stage 1 — Discovery & enrichment (`discovery_agent/` + `ingestion/market_discovery.py`)
1. **Compounding index check** — `search_company_index` first reuses companies this org already
   discovered for overlapping keywords, before paying for a live search. Reduces live-discovery
   calls over time as the org's company index grows.
2. **Gather** (`search_gatherer.py`) — issues 5 Serper.dev search-query variants per run: the
   original 3 generic templates, plus 2 directory-biased ones ("list of X vendors", "X providers
   directory") added to give topic-shaped input (e.g. "companies piloting generative AI," which
   otherwise tends to surface editorial content rather than real companies) a better, if not
   guaranteed, chance.
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
   (`_enrich_company` — company-data provider, website/context.dev signals, Serper-based
   public-search contact discovery) runs immediately, not as a separate step. Raw scraped/
   context.dev signals are normalized (`enrichment/signals.py`) before anything downstream sees
   them — dropping page chrome ("Track shipment", "Go to homepage"), requiring a real link,
   dropping stale items, de-duplicating across providers.
- A candidate's `needs_review` flag comes from the discovery agent's own per-candidate confidence
  signal, not a blanket `True` for everything created by Market Discovery.
- Failure here is loud, not silent: a broken discovery run raises, it never quietly returns zero
  candidates — but a *successful* run that still finds 0 real companies (the topic-query case
  above) now explains itself: the UI shows a prominent callout with a plain-language reason plus
  real sampled rejection text from the LLM, instead of a bare "0 candidates found" dead end.

### Stage 2 — Qualification (`qualification/`)
Judges every discovered-or-reused company against the org's **active** `QualificationCriterion`
rows (plus this run's own `market_fit_criteria`, if any). The LLM judges each criterion
individually (`met`/`not_met`/`could_not_determine`) and must now cite **evidence** for it: a
source reference (a company field, or a numbered signal `S1`, `S2`, ...) plus a verbatim quote
(`qualification/evidence.py`) — a quote that can't actually be found in the cited source is not
trusted, and the verdict is downgraded to `could_not_determine` rather than trusted as a PASS/FAIL.
The **overall verdict is still computed deterministically in Python**, never by the LLM — only
`is_disqualifying` criteria can flip it to `not_qualified`. Every check is append-only
(`QualificationResult`) — re-checking never overwrites history.

### Stage 3 — Ranking (`qualification/ranking.py`, `orchestrator/ranking_step.py`)
Every qualified-or-undetermined company gets a pure, auditable **Priority Score**: seven weighted
components, each normalized to 0..1, summed and then scaled by an evidence factor from the weakest
hard-criterion's confidence — a well-evidenced company outranks one that merely has more data.
Missing data scores a neutral-low value, not a penalty (never ranked down for what wasn't found as
hard as for what was found to be wrong). A hard FAIL excludes a company outright regardless of
score. The capped set that proceeds to Stage 4/5 is the **best-scoring** companies, not just the
first N discovered.

### Stage 4 — Role classification (`role_relevance/`)
For each ranked company's contacts, matches each one to the best-fitting **org-configurable**
`RoleCategory` by inferred function rather than title keyword-matching (a "VP Engineering" and a
"Head of IT" at different companies both need to resolve to the same function). `priority`
(`primary`/`secondary`/`not_relevant`) is computed deterministically from the matched category's
`is_primary_target` flag, not decided by the LLM. Append-only (`RoleRelevanceResult`). A company
still flagged `needs_review` is skipped here on purpose — bad data never reaches a customer-facing
draft. Bounded to `settings.auto_pipeline_max_companies_to_draft` (default 5) companies per run,
to protect the shared Gemini free-tier daily quota.

### Stage 5 — Drafting (`draft/`)
For every contact classified `primary`, generates a first-touch cold email (`GeminiDraftGenerator`):
max 7-8 lines, explicit structure (credibility → a proof point → one CTA). Grounded in **verified
evidence** (`draft/evidence.py`): recent cleaned signals, the qualification points that passed
*with evidence*, company size, and the recipient's seniority — explicit "use these, invent nothing
else" instruction, since the optional `Recommendation` grounding this used to rely on is never
actually created by the auto-pipeline in practice. Written in whichever register
(`business`/`technical`) the matched role category's `framing_style` specifies.

A rep may select **more than one** candidate product at confirm time now (`product_ids`, not one
optional `product_id`) — the generator itself is given a numbered list of candidates (each with its
own grounding when a matching `Recommendation` exists) and picks the **one** that best fits this
specific company/contact, returning which option it chose; the caller deterministically maps that
back to a real product id, never trusting an LLM-echoed id directly. One email never pitches more
than one product. If no product was selected at all, this stage reports itself skipped. A `Draft`
is mutable: a rep edits subject/body before clicking "Log as Sent," which creates an
`OutreachActivity` linked back to the draft and flips it to `sent`.

Manual, single-product actions elsewhere in the app — generating a one-off `Recommendation`,
writing a draft for one contact from the Run Worklist — are **unchanged**: a rep deliberately
picking one product for one person right now is a different interaction from the automated
pipeline's multi-candidate case, and keeps its own single-select control.

**Every stage reports `{"ran": bool, ...}` or `{"ran": false, "skipped_reason": ...}`** — a missing
prerequisite (no active criteria, no active role categories, no product selected) skips just that
stage and is reported, never aborts the whole run.

## 4. Supporting mechanics (independent of the pipeline)

- **Rep-facing Run Worklist** (`ingestion/run_results.py`, `RunWorklist.tsx`) — a pure read side
  over what the pipeline already decided: a `ready` list (qualified, with at least one
  primary-target candidate contact and the evidence to pick the right person — role, LinkedIn
  link, email if found) and a `not_shown` list (everything else, each with a one-sentence reason).
  A draft only appears on a candidate once a rep has confirmed that specific contact.
- **Leadership dashboard** (`dashboard/`, `DashboardPage.tsx`) — read-only (every query is a
  `SELECT`, nothing here can write). Reports on one chosen run or the union of all runs over a
  period (7d/30d/all, de-duplicated by company), via a KPI strip, a discover→qualify→classify→draft
  funnel, context.dev credit spend vs. its per-run ceiling, an attention queue (stuck/failed runs,
  needs-review backlog), and a recent-activity feed.
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

**Products** (2):
- *InfoBeans - Digital Transformation & Product Engineering* — service lines: Salesforce (280+
  specialists, 2,000+ implementations, incl. Agentforce/Data Cloud/MuleSoft/Tableau), ServiceNow,
  AI & Generative AI (InsaneSDD, Expona AI, BeanTrail), enterprise app development/cloud
  migration/modernization/DevOps.
- *InfoBeans - SAP ECC to S/4HANA Migration & Managed Support* — a support-first model ahead of
  SAP's 2027 end-of-mainstream-maintenance deadline: a team takes over day-to-day ECC support
  first, then senior S/4HANA architects join for the migration itself. Added as a second,
  deliberately separate product (not folded into the first) specifically so a rep can select both
  at once and let drafting choose per company — see Stage 5 above.

With 2+ products configured, nothing auto-selects at confirm time anymore (that only happens when
exactly one product exists) — a rep picks explicitly via the product checklist.

**Qualification criteria** (3, all active, all non-disqualifying):
- *Digital transformation maturity* — evidence of an active DT/modernization initiative.
- *Operates in Europe* — worded specifically around the European parcel/postal market (a holdover
  from early postal-industry test runs, not a generic geography filter — worth broadening if
  future runs target non-logistics verticals).
- *SAP ECC exposure (2027 S/4HANA deadline)* — evidence a company still runs SAP ECC and hasn't
  migrated to S/4HANA, especially relevant for companies with an acquisition history. Added
  alongside the second product above, both prompted by a sales VP's LinkedIn post describing
  exactly this pitch for European postal/parcel operators.

**Role categories** (6, all active):
- Primary targets: *IT / Engineering Leadership*, *Vendor / IT Procurement*,
  *Digital Transformation / Innovation*.
- Secondary: *Business / P&L Leadership*, *Marketing*, *Product Management*.

**Test history so far**: 8 Market Discovery runs (postal/parcel + Europe + digital-transformation/
SAP variants, a fintech/Salesforce/Indore query, and a healthcare/generative-AI query used to
reproduce and fix the zero-candidate transparency gap above), 17 companies in the index.

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
| Evidence-grounded qualification & drafting, Priority Score ranking, context.dev provider | Done |
| Rep-facing Run Worklist | Done |
| Leadership dashboard (read-only) | Done |
| Multi-product pipeline selection | Done |
| Market Discovery zero-result transparency + query-variant improvement | Done |
| Market Discovery page UX (Reset button, consistent busy-state disabling) | Done |
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
- **Two dangling ADR references in code comments**: `context_dev.py` cites a never-written
  "0012-context-dev-evaluation.md"; `qualification/ranking.py` cites "ADR 0005/0013" for the
  Priority Score, but only `0001`-`0011` exist in `docs/decisions/`. Both decisions were made and
  shipped — only the write-up is missing.
- **Topic-shaped Market Discovery queries can still return 0 real companies** even after the
  directory-biased query-variant fix — that fix is a heuristic, not a guarantee. The system now
  explains *why* when it happens (see Stage 1), but doesn't yet reformulate the query itself or
  flag at parse time that a query reads as a topic rather than a company search — both noted as
  deliberate, larger follow-ups, not oversights.

## Sources

- `docs/roadmap.md` — the authoritative feature-level roadmap this section summarizes.
- `docs/architecture.md` — module boundaries and infra phases.
- `docs/data-model.md` — full entity/field reference.
- `docs/decisions/0001` through `0011` — ADRs for each major design choice referenced above (two
  more decisions are shipped but undocumented — see Known gaps).
- Live Postgres state (`products`, `qualification_criteria`, `role_categories`, `companies`,
  `ingestion_runs` tables) for §5.
