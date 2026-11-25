# Architecture

_Last updated: 2026-11-24._

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
                  modules/products, modules/offerings, modules/opportunity,
                  modules/quicklook (+ modules/llm)
Knowledge      →  modules/documents (our own decks, PDFs and Word files, read into passages,
                  summaries and knowledge cards that the AI Analysis modules draw on)
Reach Out      →  modules/draft, modules/outreach (cadence, tracker)
Orchestration  →  modules/orchestrator (the one-prompt pipeline chaining the stages above)
```

Cross-cutting: `modules/auth` (sign-in, users, invitations, access requests and roles; see
[Sign-in and Access](#sign-in-and-access) below), `modules/credits` (credit ledger),
`modules/usage` (per-call cost and token log), `modules/review` (the log of what a person decided
about something the system flagged), `modules/jobs` (background work tracking and the worker),
`modules/dashboard` (read-only reporting over the pipeline's own data, no writes and no data model
of its own).

Behind these sit the AI governance controls (G1 to G10): see
[AI Governance and Evals](#ai-governance-and-evals) below and [`ai-governance.md`](ai-governance.md).

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

Job types (`_HANDLERS`): CSV ingestion, scrape/enrich, Market Discovery and auto-pipeline, contact
verification, bulk and ad hoc qualification (`adhoc_qualify` powers Quick Check), bulk confirm,
`sync_offerings`, the opportunity jobs (assess, analyse, recommend, suggest areas, company
offers), and the documents jobs (`ingest_document`, `embed_document`, `summarise_document`). The
hourly loop also clears old staged uploads and queues embeddings and summaries for any document
that is missing them, so a spent quota catches up by itself.

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
- **Two ways to call a model, both ending in one place.**
  - `ai_recommendation/gemini_client.py::generate_structured()` is the **only place a Gemini client
    is built** (control G6, enforced by a governance check). It sets an output cap
    (`MAX_OUTPUT_TOKENS`, 8192) and a temperature on every call, sends a thinking budget only when a
    caller asks, gives one repair retry on an unreadable answer, fails at once on an answer cut off
    at the cap, and records the call in `api_usage`. Market parsing, discovery extraction,
    qualification, role relevance, recommendations and drafting call Gemini through it directly.
  - `modules/llm/structured.py`: a **structured-output LLM seam** (`StructuredLLM`) with a Groq
    implementation, a Gemini implementation (through `generate_structured()`) and a fallback
    wrapper (`build_structured_llm`). The order is configurable (`OFFERINGS_LLM_ORDER`, default
    `groq,gemini`); any failure or rate limit on the first falls through to the next. Used by the
    offerings importer, Quick Look, opportunity research and the buyer-profile generator.
    `build_structured_llm(..., personal_data=True)` drops vendors not cleared for names or emails
    (control G1): Groq stays excluded until `GROQ_MAY_RECEIVE_PERSONAL_DATA=true` is set after a
    privacy review, and a chain left with no cleared vendor fails instead of leaking.
  - Moving the six older direct call sites behind the Groq-first seam is **not done** on purpose: it
    changes model settings and can change wording, and four of them handle personal data, so it
    needs a side-by-side check on real output first.
- `modules/llm/untrusted.py`: `wrap_untrusted()` fences scraped pages, search snippets, news, job
  posts and contact titles in every prompt that includes outside text, and each prompt starts with
  a notice that marked text is data and never instructions (control G2). It lowers the risk; the
  real limits stay in code (schema checks, quote verification, verdicts computed in Python, a
  person reviews drafts).
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

### Opportunity module layout
`opportunity/` is split into small files: `service.py` and `areas.py` (an opportunity per business
area, with free-text areas turned into stable keys), `evidence.py` and `research/` (collectors and
the Greenhouse, Lever and Ashby readers), `assessment.py` and `sufficiency.py` (the model's findings
and the verdict computed in code), `fit.py`, `shortlist.py`, `pick.py` and `offers.py` (offering fit:
a free word-overlap shortlist, a model pick when it finds none, and ideas for a company with no area
chosen), `relevance.py` (contacts matched to an opportunity), `recommend.py`, `suggest.py` (area
suggestions, below), `quickcheck.py` (the opportunity step of a Quick Check; it never fails the
check), `run_stage.py` (one light fit job per ranked company after a run, outside the pipeline's
stages so it can never fail or slow a run) and `jobs.py`.

**AI Recommended Areas.** `suggest.py` reads the evidence already on file for a company and saves
areas it points to, each with a one-line reason. It makes one model call the first time; reopening
the Brief makes none. An explicit "Refresh AI Recommendations" makes a fresh call and replaces the
chips, and if that call fails or returns nothing new the old chips stay.

## Quick Look (the app's "Quick Check")
`modules/quicklook/` answers "is this company worth a look" from a name or website, without
creating a company. `resolve.py` turns a name into a website candidate, or asks the person when it
is ambiguous. `research.py` gathers news, jobs and web evidence, time-boxed and best-effort.
`snapshot.py` has the model suggest which offerings fit, with quoted sources; code verifies each
quote and computes the yes / maybe / no call. `service.py` writes a `company_snapshots` row, cached
per domain and invalidated when Our Offerings changes (`offerings_hash`). Nothing reaches the
Companies list until `POST /quick-look/save` turns the snapshot into a company. Every check is also
kept in `quick_check_history` with a copy of its answer, and the page lists each person's own
earlier checks below the search. The page route is `/qualification/check` and the component is
`QuickLookPage`.

## Documents Knowledge Base (Phase 8)
`modules/documents/` turns our own files into knowledge the AI flows can cite
([ADR 0015](decisions/0015-documents-knowledge-base.md)):

```
upload ─► staging row ─► ingest_document ─► pages + passages (+ picture descriptions)
                                  │
                                  ├─► embed_document ─► passage and card vectors (pgvector)
                                  └─► summarise_document ─► summaries, knowledge cards,
                                                            offering description proposals
```

- **Reading** (`ingest.py`, `parsers/`): the type is found from the content; PDF (PyMuPDF), PPTX,
  DOCX, Markdown and text become pages in reading order and ~1,000-character passages. Pictures,
  charts, unreadable tables and scanned pages can be described by Gemini (`vision.py`, off by
  default). No original file is kept.
- **Search** (`retrieval.py`, `vector_store.py`): meaning (pgvector cosine, HNSW) and words
  (Postgres full text) merged by reciprocal rank fusion over current versions; cards are searched
  the same way. Words only when meaning search is off or unavailable, and the screen says so.
- **Summaries and cards** (`cards.py`, `card_prompts.py`): Gemini summarises each section and the
  document and draws short facts; code keeps a card only when its quote, figures and any client
  name are in the passage it names. A document tied to an offering may propose a better
  description, applied only when a person approves it in the offering review.
- **In the flows** (`knowledge.py`): `gather()` packs the best cards and passages as `[K1]`, `[K2]`,
  fenced as untrusted text; `generate_with_knowledge()` sends that prompt to Gemini only and falls
  back to the plain prompt. Used by offering fit, the recommendation, area suggestions and Quick
  Check; what was cited is stored with the answer and shown as "From our documents".
- **Switches:** `DOCUMENTS_ENABLED`, `DOCUMENTS_EMBEDDINGS_ENABLED`, `DOCUMENTS_CARDS_ENABLED` (on;
  the last two need a Gemini key) and `DOCUMENTS_VISION_ENABLED` (off). Tables are described in
  [`data-model.md`](data-model.md#documents-phase-8b).

## Sign-in and Access (Phase 9)
[ADR 0017](decisions/0017-sign-in-and-access.md). Firebase Authentication with InfoBeans Google
accounts proves who someone is; `modules/auth/` decides what they may do.

```
browser ── Google sign-in (Firebase) ──► ID token
   │                                         │ on every request: Authorization: Bearer <token>
   ▼                                         ▼
api/client.ts ──────────────────────► auth/deps.py
                                         verified_identity  token checked against Google's certs
                                         signed_in          users row: invited, active, our org
                                         require(action)    role allowed (auth/permissions.py)
```

- **Tokens** (`auth/tokens.py`): `google-auth` checks signature, audience, issuer and expiry with
  only `FIREBASE_PROJECT_ID`; code adds verified email, Google provider and an allowed domain.
  Certificates are cached for as long as Google allows.
- **Access** (`auth/service.py`): a token is matched to a `users` row by Firebase id, else by email
  (taking up an invitation). No row: the person sees the app frame with only the Dashboard and a
  Request access card. `AUTH_BOOTSTRAP_ADMINS` lets the first admin in.
- **Every router** in `main.py` is mounted with `Depends(signed_in)` except `/health` and `/auth/*`;
  `governance_checks/test_routes_require_sign_in.py` fails if one is not. Routes that change
  things also ask `require(Action.X)`; the matrix is one table, sent to the browser by `/auth/me`.
- **Who did it**: `signed_in` puts the person in the request context (`usage/context.py`); audit
  lines, review decisions, runs, jobs and usage rows read it, and the worker restores it from
  `jobs.created_by`.
- **Idle sign-out** (`src/auth/idle.ts`): after 60 minutes without a click or key press (any tab
  counts; a warning shows 2 minutes before) the person is signed out and the screen is locked with
  the page still loaded underneath, so signing in again as the same person loses nothing. A
  remembered sign-in unused for longer than that (browser closed) asks to sign in again. Firebase
  ID tokens last an hour and are renewed silently; the server keeps no session.
- **Frontend** (`src/auth/`): `AuthProvider` (Firebase identity plus `/auth/me`), the sign-in page,
  the access gate around the app, the account menu, Profile and User Management.

## "Not a Fit" and the Review Log
A person can mark a company "not a fit" with a reason from a short fixed list and an optional note,
singly or in bulk, and restore it later (`POST /companies/{id}/dismiss`, `/restore`,
`/companies/dismiss`; `/companies/dismissal-check` lists outreach history a dismissal would hide).
A dismissed company is excluded from every automatic path (`orchestrator/service.py::
active_company_ids()` before qualification; bulk jobs; the Needs Review queue; reminders; dashboard
figures; run results), and a later Market Discovery run that finds it again counts it as
`skipped_dismissed` instead of reviving it. If it has logged outreach or sent drafts the server
answers 409 until the person confirms. `modules/review/` writes every such decision, and every
confirm or deletion of a flagged company or contact, to `review_decisions` with a snapshot of what
the person saw. Field detail is in [`data-model.md`](data-model.md).

## Usage Metering
`modules/usage/` records one `api_usage` row per call to a model, search or context.dev request.
`recorder.py` writes in its own short session and never raises, so a failed job still keeps its
cost record. `context.py` carries who a call is for (job, run, company, opportunity), and
`route_tag.py` names calls made inside a web request `api:<route>`, so little lands under
`unspecified`. `pricing.py` estimates cost from published prices (the Gemini price was checked
against Google's page on 2026-11-12; the rolling model alias is not documented, so pin
`GEMINI_MODEL` to a named model to remove that doubt). `GET /usage/summary` feeds the dashboard's
Cost and health panel; `scripts/usage_report.py` shows cached and thinking tokens, failed calls by
reason, and `--review` for cost per researched company. A spending ceiling is deferred until a paid
key.

## How a Draft Is Written

`draft/` builds the prompt from small, reviewable pieces. The email type (first touch, follow-up 1,
2 or 3) selects the closing-line rule, and handing the email on to someone else is allowed only
from follow-up 2. Each offering option carries its type: a product may offer a walkthrough, a
service proposes a short conversation. Follow-ups are given the earlier emails to the same person.
The role framing (business or technical) changes vocabulary only. All of it sits under the
existing guardrails: only verified facts may be cited, nothing is invented, and the model picks
exactly one offering per email.

After generation, `draft/claims.py` reads the finished email and flags figures (percentages, money,
multipliers, counts of years or clients) and past-work wording ("case study", "our clients", "we
helped", "trusted by") that were not in what the draft was given. The flags are stored on the draft
(`grounding_flags`) and shown as "Check before sending". It warns and never blocks, it is a
heuristic that can miss a claim worded another way, and it is not re-run after a person edits.

## AI Governance and Evals
The rules for every place a model is used are in [`ai-governance.md`](ai-governance.md) (controls
G1 to G10; decision record [ADR 0014](decisions/0014-ai-governance.md)). Two pieces are code:

- `backend/governance_checks/` holds tests that need no keys and no network. They fail when a new
  prompt-building file does not fence outside text (G2), a second place builds a Gemini client (G6),
  a new AI-written table lacks `model_used` and `prompt_version` (G9), the "not a fit" reasons on
  the screen and the server differ (G4), or a prompt version has no current eval report (G5). Four
  more test the eval harness itself with fakes.
- `backend/evals/` is the eval harness: thirteen tasks (Quick Look, qualification, drafts, the draft
  rewrite, offering extraction, recommendations, opportunity assessment, offering fit, area
  suggestions, knowledge cards, picture descriptions, contact relevance, role relevance) with 68
  hand-written cases (injection, grounding, a few accuracy checks), graders, committed reports in
  `evals/reports/`, and a runner (`python -m evals.run`, a dry run by default, `--yes` to call real
  models, `--repeat`). Ten tasks have reports (latest per task: 57 of 58 cases passed); three
  (opportunity assessment, contact relevance, role relevance) wait for a first run with real
  models, listed in `AWAITING_FIRST_REPORT`, and that list may only shrink. Accuracy against
  real labelled companies needs labels from the team and is not measured yet.

**CI** (`.github/workflows/ci.yml`) runs on push to main and on pull requests: `ruff`, `mypy` and
`pytest` for the backend, and lint, `tsc` and the test command for the frontend. Be aware that
`backend/tests/` and the frontend test files are git-ignored (commit `1ce0b15`), so CI effectively
runs only `governance_checks`. A pull request template carries an AI-changes checklist.

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
  pipeline status so a stuck record is debuggable. A run keeps a short trail of its last real
  progress events (`TRAIL_LENGTH = 5` in `orchestrator/service.py`) so the run screen names the
  company being worked on instead of showing "Starting…", and the finish summary reports what was
  found, what fit, whose people were sorted and what is ready.
- **Cost and rate control**: retries with backoff and rate limiting at provider boundaries; credit
  ceilings per run for context.dev; a cap on automatic drafting per run.
- **Security and PII**: contact details are personal data even in a B2B context; provider keys
  live in env and are never committed. Every API route requires a signed-in, invited InfoBeans
  account (Phase 9, ADR 0017); before deployment, restrict the Firebase web key to the real domain
  and add that domain to Firebase's authorised domains.
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
| 4 | Credits and usage tracking | Ledger in place; per-call cost and token metering done (`modules/usage`), spending ceiling deferred |
| 5 | Contact verification | Not started |
| 6 | Reach Out (drafting, tracker, cadence) | Done for email, sending is manual |
| 7 | SaaS readiness (sign-in, tenant isolation, spend caps) | Sign-in, invitations and roles done in Phase 9 (ADR 0017); tenant isolation and spend caps deferred |
| 8 | Production database (Postgres + pgvector, ADR 0016) and the documents knowledge base (ADR 0015) | Done |
| 9 | Sign-in with Google (Firebase), invite-only access, roles, who did what (ADR 0017) | Done |

The AI governance programme has its own phase numbers (0 to 7, tracked in `ai-governance.md`) that
are separate from the table above.

For the feature-level roadmap and what is shipped versus planned, see
[`docs/roadmap.md`](roadmap.md).
