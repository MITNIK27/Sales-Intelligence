# Architecture

_Last updated: 2026-10-30._

## Overview

Sales Intelligence is a **modular monolith**: a single FastAPI deployable with strict internal
module boundaries, rather than microservices. Each module owns its own models, schemas, routes,
and services. This keeps operational complexity low for an internal-first tool while leaving a
clean seam to extract a module into its own service later if scale ever demands it.

Three processes run together: the **API** (FastAPI), a **worker** (a plain Python `asyncio` loop
that executes background jobs and the weekly offerings check), and the **frontend** (React, served
by Vite in development). They share one PostgreSQL database.

The four product stages map onto backend modules as follows:

```
Ingest         →  modules/ingestion (+ modules/discovery_agent for Market Discovery)
Enrich         →  modules/enrichment (+ providers/), modules/companies, modules/contacts
Verify         →  modules/verification (deferred, see Phases below)
AI Analysis    →  modules/qualification, modules/role_relevance, modules/ai_recommendation,
                  modules/products, modules/offerings (+ modules/llm)
Reach Out      →  modules/draft, modules/outreach (cadence, tracker)
Orchestration  →  modules/orchestrator (the one-prompt pipeline chaining the stages above)
```

Cross-cutting: `modules/auth` (org/user/roles), `modules/credits` (usage ledger),
`modules/jobs` (background work tracking and the worker), `modules/dashboard` (read-only reporting
over the pipeline's own data, no writes and no data model of its own).

## Background Jobs, Simplified

Scraping a company's site, calling the AI model, etc. all take real time and repeat across
potentially hundreds of companies per run. That can't happen inline in an HTTP request without
the UI hanging, so it runs in the background while the frontend polls for progress.

Rather than standing up Celery + Redis (a message broker + worker fleet), the approach here is
intentionally minimal:

- A `jobs` table in Postgres: one row per unit of work, with a status column
  (`pending` / `running` / `done` / `failed`), a progress field and a result/error field.
- A single worker process (`python -m app.modules.jobs.worker`) that polls the table for pending
  rows and runs the handler registered for the job type (`_HANDLERS` in `jobs/worker.py`).
- The frontend polls `GET /jobs/{id}` to show progress (for example "Checking page 62 of 87").
- A small **scheduler loop** inside the worker checks hourly whether a scheduled task is due. Today
  it has one task: enqueue the offerings check when none has succeeded in the last 7 days and none
  is already pending. The schedule lives in the worker, so it works on any host without cron.

No new infrastructure beyond Postgres. If volume ever outgrows one polling worker, this can be
swapped for Celery/Arq + Redis; `jobs` is the seam where that happens.

Job types: CSV ingestion, scrape/enrich, Market Discovery parse and auto-pipeline, bulk and ad hoc
qualification (`adhoc_qualify` powers Quick Check), bulk confirm, and `sync_offerings`.

The worker does not reload on code changes; restart it after a backend change.

## Provider / Adapter Abstractions

Several modules are built around a swappable interface rather than a hardcoded external
dependency:

- `enrichment/providers/`: `CompanyDataProvider` / `ContactDataProvider` / `SignalDataProvider`.
  Default: an in-house scraper of public sources (company websites, web search), respecting
  `robots.txt` and rate limits. A second provider (context.dev, a paid API) fills only the gaps the
  free scraper leaves (thin firmographics, too few genuine signals) under a per-run credit ceiling.
  Search-based contact discovery reads only what Serper already indexed on a trusted-domain
  allowlist and never logs into or scrapes LinkedIn ([ADR 0010](decisions/0010-search-based-contact-discovery.md)).
- `modules/llm/structured.py`: a small **structured-output LLM seam** (`StructuredLLM`) with a Groq
  implementation, a Gemini implementation and a fallback wrapper (`build_structured_llm`). The
  order is configurable (`OFFERINGS_LLM_ORDER`, default `groq,gemini`); any failure or rate limit
  on the first falls through to the next. Only the offerings importer uses it today. The rest of
  the app (qualification, role relevance, drafting, discovery, recommendations) still calls Gemini
  directly through `ai_recommendation/gemini_client.py`; moving those behind the seam, one task at
  a time and after a side-by-side comparison, is planned.
- `offerings/sources.py`: a **page source** seam for reading website pages, with context.dev as the
  primary reader and the in-house scraper as fallback (`OFFERINGS_SOURCE_ORDER`).
- `discovery_agent/` ([ADR 0004](decisions/0004-discovery-agent.md)): turns a free-text market
  description into real, criteria-matched companies through gather, extract and resolve stages,
  behind one narrow interface (`CompanyDiscoveryAgent.discover`).
- `verification/providers/` and `outreach/adapters/` remain designs for deferred phases.

## The Offerings Importer

`modules/offerings/` keeps the catalog of what InfoBeans sells in step with its website, without
anyone retyping it. It never changes live data by itself.

1. **Discover.** Read the sitemap (with each page's `lastmod`) and the website menu. Pages found
   under the menu's "Disciplines" and "Innovation" entries are queued even if no sitemap lists
   them, so nothing is hard-wired to named products. Blog posts form a separate lane.
2. **Gate.** A **page ledger** (`offering_pages`) remembers every page ever considered, its content
   hash and verdict. A page whose `lastmod` has not moved is skipped entirely: no scrape, no model
   call. A page whose text hash is unchanged costs no model call. Failed pages are retried, pages
   with no `lastmod` are rechecked after 6 days, and everything is fully re-read every 30 days.
3. **Read and extract.** A page is read through the page source, then one structured LLM call
   returns name, kind (service or product) and a short description. Blog posts are first screened
   by a light model (batches of 20, capped per sync) so only likely offerings are read.
4. **Check.** A deterministic grounding check flags numbers or names in the description that the
   page does not contain, and each proposal stores a source excerpt so a reviewer can compare.
5. **Propose.** Results are written only as `offering_proposals` (`new`, `changed`, `removed`).
   Approving one is the only path that creates, changes or archives a live offering. Removal means
   archive, never delete, because drafts and recommendations reference offerings.

Safeguards that matter in practice: every address is reduced to one canonical form before
comparison; a removal is proposed only when the page itself answers 404 or 410; a run that could
read nothing (or mostly nothing) fails with a plain message instead of proposing removals; stale
pending removals are withdrawn automatically; network reads retry on transient errors. The
"What was checked" view in the app shows every page considered, what was decided and why, and the
website menu compared with the catalog. `backend/scripts/audit_offerings.py` is a read-only audit
that exits non-zero when something needs attention.

## Opportunity Research

`modules/opportunity/` answers "what is this company doing in this business area, and how do we
know". One company can have several opportunities (one per area), and everything area-specific
hangs off a `CompanyOpportunity`.

- **Evidence with stable provenance.** Findings cite the evidence record (id, address, fetch time,
  a hash of its text) and an exact quote that must appear in it; a citation that does not check out
  is dropped. The verdict is computed in code from the verified findings and never by the model.
- **Collectors** (`opportunity/research/`) gather evidence for one area: news (context.dev, dated),
  job postings (the public Greenhouse, Lever and Ashby job boards, found from links on the
  company's own careers page and never guessed; LinkedIn is not read), and announcements on the
  company's site and the web (context.dev, with Serper as a backup; context.dev results carry no
  date). Each collector skips itself while its last results are fresh (hiring 3 days, news 7, web
  14) and reports what it searched, so a gap is stated rather than hidden. A failing collector
  reports an error and the rest carry on.
- **Cache.** An assessment is keyed by a fingerprint of the evidence shown plus the prompt version;
  unchanged evidence is not judged again, and a newly stated gap is never served from the cache.
- **Limits.** Many companies use their own career sites, so hiring coverage is partial; Lever's
  board gives no posting date; trends need at least two collections over time.

## How a Draft Is Written

`draft/` builds the prompt from small, reviewable pieces. The email type (first touch, follow-up 1,
2 or 3) selects the closing-line rule, and handing the email on to someone else is allowed only
from follow-up 2. Each offering option carries its type: a product may offer a walkthrough, a
service proposes a short conversation. Follow-ups are given the earlier emails to the same person.
The role framing (business or technical) changes vocabulary only. All of it sits under the
existing guardrails: only verified facts may be cited, nothing is invented, and the model picks
exactly one offering per email.

## Principles the Design Follows

- **A person decides.** AI output is a proposal or a draft until someone approves, confirms or
  edits it.
- **The model judges, code decides.** Verdicts, priorities and rankings are computed in
  deterministic code from per-item judgments that cite evidence; a verdict whose quote does not
  check out is downgraded to "could not determine".
- **Nothing is silently changed.** Judgment and activity tables are append-only; configuration is
  retired with `is_active` or `status`, not deleted.
- **Flag, don't assume.** Uncertain matches are marked `needs_review` rather than trusted or
  blocking the run.

## Cross-Cutting Concerns

- **Dedup**: company (domain) and contact (email) dedup is core to data quality, enforced in
  `companies`/`contacts`.
- **Observability**: structured logging, job progress and result summaries, and per-company
  pipeline status so a stuck record is debuggable.
- **Cost and rate control**: retries with backoff and rate limiting at provider boundaries; credit
  ceilings per run for context.dev; a cap on automatic drafting per run.
- **Security and PII**: contact details are personal data even in a B2B context; provider keys
  live in env and are never committed. The app has no sign-in yet (see the roadmap), so it must
  not be exposed publicly as is.
- **Testability**: provider and LLM seams exist so unit tests run against fakes without network
  access.
- **Multi-tenancy**: `Organization`/`User` are modeled from day one even though one internal org
  exists, so tenant isolation won't need a schema migration later.

## Implementation Phases

| Phase | Scope | State |
|---|---|---|
| 0 | Repo scaffolding, core `Organization`/`User` models, CI, docs | Done |
| 1 | Ingestion (CSV upload), core `Company`/`Contact`/`ContactChannel`, `jobs` | Done |
| 2 | Enrichment (in-house scraper) + Market Discovery | Done |
| 3 | Product catalog + AI recommendation layer (Gemini) | Done; the catalog is now "Our Offerings" and website-imported |
| 4 | Credits and usage tracking | Ledger in place |
| 5 | Contact verification | Not started |
| 6 | Reach Out (drafting, tracker, cadence) | Done for email, sending is manual |
| 7 | SaaS readiness (sign-in, tenant isolation, spend caps) | Deferred |

For the feature-level roadmap and what is shipped versus planned, see
[`docs/roadmap.md`](roadmap.md).
