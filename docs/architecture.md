# Architecture

## Overview

Sales Intelligence is a **modular monolith**: a single FastAPI deployable with strict internal
module boundaries, rather than microservices. Each module owns its own models, schemas, routes,
and services. This keeps operational complexity low for an internal-first tool while leaving a
clean seam to extract a module into its own service later if scale ever demands it.

The four product stages map onto backend modules as follows:

```
Ingest         →  modules/ingestion (+ modules/discovery_agent for Market Discovery)
Enrich         →  modules/enrichment (+ providers/), modules/companies, modules/contacts
Verify         →  modules/verification (Phase 5, deferred — see Phases below)
AI Analysis    →  modules/ai_recommendation, modules/products
Reach Out      →  modules/outreach (+ adapters/) (Phase 6, deferred)
```

Cross-cutting: `modules/auth` (org/user/roles), `modules/credits` (usage ledger),
`modules/jobs` (background work tracking).

## Background Jobs, Simplified

Scraping a company's site, calling the AI model, etc. all take real time and repeat across
potentially hundreds of companies per run. That can't happen inline in an HTTP request without
the UI hanging — it has to run in the background while the frontend polls for progress.

Rather than standing up Celery + Redis (a message broker + worker fleet — real infrastructure to
run, monitor, and debug), the approach here is intentionally minimal:

- A `jobs` table in Postgres: one row per unit of work, with a status column
  (`pending` / `running` / `done` / `failed`) and a result/error field.
- A single background worker process (a plain Python `asyncio` loop, run alongside the API) that
  polls that table for pending rows and processes them.
- The frontend polls a `GET /jobs/{id}` status endpoint to show progress.

No new infrastructure dependency beyond the Postgres database the app already needs. If volume
ever genuinely outgrows a single polling worker, this can be swapped for Celery/Arq + Redis later
— the `jobs` module is the seam where that swap happens; nothing above it needs to change.

## Provider / Adapter Abstractions

Three modules are built around a swappable interface rather than a hardcoded external dependency,
because the concrete choice is either still open or deliberately deferred:

- `enrichment/providers/` — `CompanyDataProvider` / `ContactDataProvider`. Default
  implementation: an in-house scraper of free/public sources (company websites, public web
  search, business directories — respecting `robots.txt` and rate limits). See
  [`docs/decisions/`](decisions/) for the LinkedIn-as-a-source question.
- `verification/providers/` — `VerificationProvider`. Built in Phase 5. Default plan: in-house
  free check (MX-record lookup + SMTP handshake probe for email, format/pattern check for phone).
- `outreach/adapters/` — `OutreachAdapter`. Built in Phase 6. Email first; WhatsApp/call adapters
  pending a provider decision.

The AI recommendation layer (`ai_recommendation/`) also sits behind a thin client abstraction so
the LLM provider (currently: free-tier Google Gemini) can be swapped later without touching
prompt/orchestration logic.

`discovery_agent/` (Phase A1, see [ADR 0004](decisions/0004-discovery-agent.md)) is a similarly
isolated module: it turns a free-text market description into real, criteria-matched companies
via a layered gather → extract → resolve pipeline, exposing one narrow interface
(`CompanyDiscoveryAgent.discover`) so a failure in any internal stage can never propagate a
partially-broken state into the rest of Market Discovery, and so the module could be moved behind
a real service boundary later without callers changing.

## Cross-Cutting Concerns

- **Dedup**: company (domain) and contact (email) dedup is core to data quality, not an
  afterthought — enforced in `companies`/`contacts` from Phase 1.
- **Observability**: structured logging plus a pipeline trace per Company/Contact (which stage,
  which provider, success/failure), so a stuck or bad prospect record is debuggable.
- **Cost/rate control**: retries with backoff and rate limiting at the provider/adapter boundary.
- **Security/PII**: contact emails/phones are personal data even in a B2B context — access is
  role-restricted, provider API keys live in env/secrets and are never committed.
- **Testability**: provider/adapter abstractions exist specifically so unit tests run against
  mocks without hitting real external services.
- **Multi-tenancy**: `Organization`/`User` modeled from day one (see `docs/data-model.md`) even
  though only one internal org exists today, so tenant isolation doesn't require a schema
  migration later if/when this becomes a SaaS product.

## Implementation Phases

| Phase | Scope |
|---|---|
| 0 | Repo scaffolding, core `Organization`/`User` models, CI, docs (this phase) |
| 1 | Ingestion (CSV upload), core `Company`/`Contact`/`ContactChannel` models, `jobs` mechanism |
| 2 | Enrichment (in-house scraper) + Market Discovery |
| 3 | Product catalog + AI Recommendation layer (Gemini) |
| 4 | Credits & usage tracking |
| 5 | Contact verification |
| 6 | Reach Out (outreach adapters, starting with email) |
| 7 | SaaS readiness (deferred until there are "green flags" to pursue it) |

These are infra/module build-out phases. For the feature-level roadmap (company targeting →
qualification → tracking → outreach) and what's actually shipped vs. planned, see
[`docs/roadmap.md`](roadmap.md).
