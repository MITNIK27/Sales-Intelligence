# Sales Intelligence — Deep Context Brief

*As of 2026-11-16, branch `feat/SI-governance` (latest commit `0ba10bf`, Phase 7).*

This is the long, single-file brief: what the product is, how each stage works, how it decides, and
what is and is not built. It is meant to be handed to a person or to Claude as full context (for
example before branding or positioning work). The detailed, always-maintained sources are in
`docs/`: [`project-overview.md`](docs/project-overview.md), [`architecture.md`](docs/architecture.md),
[`data-model.md`](docs/data-model.md), [`roadmap.md`](docs/roadmap.md),
[`ai-governance.md`](docs/ai-governance.md) and [`docs/decisions/`](docs/decisions/). If this file and
those disagree, those win.

## 1. What this system does

Sales Intelligence automates the manual prospecting workflow that Paarth Sahni and Abhas Jain
(InfoBeans) described in their working session (`Meeting notes/Sales Funnel Automation
Discussion...md`, 2026-09-08): going from "here's the kind of company we want to sell to" to a
drafted, ready-to-send cold email for a named decision-maker at a real company, without a rep
searching, judging, classifying and writing each step by hand. The rep reviews and sends; **the tool
never sends anything itself.**

Two ways in:

- **The One-Prompt Pipeline** (Market Discovery). Type a free-text market description, confirm the
  system's interpretation once, and discovery, qualification, ranking, role classification and
  drafting run as one background job. A CSV upload is the other bulk way in.
- **Quick Check** (code name: Quick Look). Type a company name or website and get a short answer
  with evidence, the offerings that might fit, and a yes / maybe / no call. It creates no company
  until the rep saves it.

Around them: a **Company Brief** (per company and business area), **Not a fit** (a rejection that
sticks), **Drafts** and **Follow-ups**, **Our Offerings** (what InfoBeans sells, kept in step with
its website by proposals a person approves), and a read-only **leadership dashboard**.

Who it is for: InfoBeans' own sales team today (one organization, no sign-in yet, trusted network
only). The stated intent is to prove it internally, then take it to market as a standalone product
for any B2B sales team; the data model is multi-tenant from day one for that reason.

## 2. Architecture

**Modular monolith**: one FastAPI deployable, strict module boundaries (`backend/app/modules/`),
each module owning its models, schemas, routes and services. Three processes share one PostgreSQL
database: the **API**, a **worker** and the **React/Vite frontend**.

**Background jobs without new infrastructure.** Scraping and model calls take real time, so nothing
runs inline in a request. A `jobs` table (`pending`/`running`/`done`/`failed`, JSONB result and
error) is polled by one asyncio worker (`modules/jobs/worker.py`, handlers in `_HANDLERS`). The
frontend polls `GET /jobs/{id}`. The worker also runs a scheduler that enqueues the weekly offerings
check. This is the seam where Celery/Arq plus Redis would swap in if volume demands it. The worker
does not reload on code changes.

**Provider/adapter seams**
- `enrichment/providers/`: company, contact, signal and domain-discovery providers. The free
  in-house scraper is the default; **context.dev** fills only the gaps it leaves (thin firmographics,
  too few genuine signals) under a per-run credit ceiling; **Serper** handles domain lookup and
  public-web search. LinkedIn is never scraped or logged into ([ADR 0001](docs/decisions/0001-data-sourcing-strategy.md),
  [0010](docs/decisions/0010-search-based-contact-discovery.md)).
- **One place builds a Gemini client**: `ai_recommendation/gemini_client.py::generate_structured()`
  (output cap, temperature, one repair retry, usage logging). `llm/structured.py` is a Groq-first,
  Gemini-fallback seam used by the offerings importer, Quick Look, opportunity research and buyer
  profiles; Groq is kept away from personal data until InfoBeans security confirms its terms.
- `outreach/`: email only. LinkedIn send, Gmail send and WhatsApp/call adapters are deliberately
  deferred ([ADR 0011](docs/decisions/0011-linkedin-gmail-integration-scope.md)).

**Multi-step agents**: `discovery_agent/` (gather, extract, resolve) and `orchestrator/` (runs the
pipeline stages in order, deciding what runs next from each stage's real outcome).

**Other modules**: `quicklook/` (Quick Check), `opportunity/` (areas, evidence, assessments, offering
fit, area suggestions), `offerings/` (website importer), `review/` (log of human decisions),
`usage/` (per-call cost and tokens), `dashboard/` (read-only), `credits/`, `auth/`.

## 3. The One-Prompt Pipeline, stage by stage

Entry: `POST /market-discovery/parse`, then `POST /market-discovery/{run_id}/confirm` (the one
manual step) enqueues one `auto_pipeline` job (`orchestrator/service.py::run_auto_pipeline_job`).
`MarketDiscoveryPage.tsx` polls the job and shows the run screen (see §4).

### Stage 0: Parse (inline)
One fast Gemini call turns "SaaS companies in Bangalore, 50-200 employees" into
`{industry_keywords, location, employee_size_range}`, each with a `confidence`
(`confident` / `could_not_determine`). Low-confidence fields are left blank for the rep, never
guessed. Stored as an `IngestionRun` in `awaiting_confirmation`. At confirm time the rep may add
search-specific hard requirements (`market_fit_criteria`), choose the offerings to pitch (one or
more), and optionally choose target roles. The choices are kept on the run (`context`).

### Stage 1: Discovery and enrichment (`discovery_agent/`, `ingestion/market_discovery.py`)
1. **Compounding index check**: reuse companies the org already found for overlapping keywords
   before paying for a live search. Companies marked "not a fit" are left out of this index.
2. **Gather**: five Serper query variants (three generic, two directory-biased).
3. **Extract** (Gemini): structured candidates, each with `accepted`, `grounded_in_source` and
   `reasoning`.
4. **Heuristic backstop** (`heuristics.py`): listicle- or article-shaped names are rejected before
   they can become a company; structurally suspicious ones are kept but flagged `needs_review`.
5. **Resolve**: find each candidate's real domain, filtering aggregator and social domains
   (`market_discovery_domain_denylist`).
6. For each new candidate: `get_or_create_company` (deduped by domain), then full enrichment
   immediately (company data, signals, search-based contact discovery). Raw signals are normalized
   before anything downstream sees them (page chrome dropped, a real link required, stale items
   dropped, duplicates removed). What discovery saw is stored on the company (`discovery_evidence`).
   A company already dismissed is not linked, enriched or passed on; the run counts it as
   `skipped_dismissed`.

Failure is loud: a broken discovery run raises. A successful run that finds no real companies
explains itself, with a plain-language reason and real sampled rejection text.

### Stage 2: Qualification (`qualification/`)
Every discovered or reused company (not dismissed) is judged against the org's active
`QualificationCriterion` rows plus the run's own `market_fit_criteria`. The model judges each
criterion (`met` / `not_met` / `could_not_determine`) and must cite **evidence**: a source reference
(a company field or a numbered signal) and a verbatim quote. A quote that cannot be found in the
cited source is not trusted and the verdict drops to `could_not_determine`. **The overall verdict is
computed in Python, never by the model**; only `is_disqualifying` criteria can make it
`not_qualified`. Results are append-only (`QualificationResult`).

### Stage 3: Ranking (`qualification/ranking.py`, `orchestrator/ranking_step.py`)
A pure, auditable **Priority Score**: seven weighted components, each 0 to 1, scaled by an evidence
factor from the weakest hard criterion's confidence, so a well-evidenced company outranks one that
merely has more data. Missing data scores neutral-low, not as a penalty. A hard FAIL excludes a
company. The capped set that goes on is the best-scoring companies, not the first N found.

### Stage 4: Role classification (`role_relevance/`)
Each ranked company's contacts are matched to the best-fitting org-configurable `RoleCategory` by
inferred function, not title keywords. `priority` (`primary` / `secondary` / `not_relevant`) is
computed in code: a run may name target categories (those are `primary`), otherwise every matched
contact is `primary` so no role is filtered out before a person looks. A company still flagged
`needs_review` is skipped on purpose. Bounded by `auto_pipeline_max_companies_to_draft` (default 5)
to protect free-tier quota; the run result says when the cap applied and which qualified companies
fell outside it.

### Stage 5: Drafting (`draft/`)
For primary contacts, and when offerings were chosen, a first-touch email is written (max 7 to 8
lines: credibility, a proof point, one CTA). It is grounded in verified evidence only (cleaned
signals, qualification points that passed with evidence, company size, recipient seniority) with an
explicit "use these, invent nothing else". The email type (first touch, follow-up 1 to 3) selects
the closing rule, and an offering is described as a product (offer a walkthrough) or a service
(offer a short conversation). With several candidate offerings the model picks the **one** that
fits and the caller maps it back to a real id deterministically; one email never pitches two. After
generation `draft/claims.py` flags figures and past-work wording ("case study", "our clients", "we
helped") that were not in the draft's inputs, shown as **Check before sending**. It warns and never
blocks. A draft is mutable: the rep edits it, sends it themselves and clicks "Log as Sent", which
creates an `OutreachActivity`. Drafts can also be written one contact at a time from the worklist
("Write draft").

Every stage reports `{"ran": true, ...}` or `{"ran": false, "skipped_reason": ...}`. A missing
prerequisite skips only that stage and is reported; it never aborts the run.

## 4. Supporting mechanics

- **Run screen** (`MarketDiscoveryPage.tsx`, `RunProgress.tsx`, `RunOutcome.tsx`, `runStory.ts`):
  stages are named in plain words and name the company being worked on, with a short trail of the
  last real events. The finish summary gives a headline, a Found > Fit > People sorted > Ready
  funnel and a next step. "Ready for you" is a grid of compact cards (logo, score, why it fits);
  a click opens full details in a dialog. Companies not shown are listed with the reason.
- **Run worklist** (`ingestion/run_results.py`): a pure read of what the pipeline decided: a `ready`
  list (qualified, with candidate contacts and the evidence to pick the right person) and a
  `not_shown` list with a one-sentence reason each. A draft appears only once a rep confirms that
  contact.
- **Company Brief** (`features/brief/`, `modules/opportunity/`): one company, several business
  areas. Findings cite an evidence record and an exact quote; a citation that does not check out is
  dropped; the verdict is computed in code; unchanged evidence is not judged again (cache keyed on
  an evidence fingerprint plus prompt version). Collectors cover news, job boards (Greenhouse,
  Lever, Ashby, found from the company's own careers page, never guessed) and web announcements,
  each stating what it searched so a gap is stated, not hidden. A hand-built SVG map links evidence
  to engagement, drawing verified, inferred and unsupported links differently. Offering fit uses a
  free shortlist, one grounded model call and a band and score computed in code. **AI Recommended
  Areas** suggests areas from the evidence on file; Refresh replaces the chips and keeps the old ones
  if the call fails.
- **Not a fit**: a reason from a fixed list and an optional note, singly or in bulk, with Undo. The
  company disappears from lists and every automatic step, is not revived by later searches, and the
  decision is logged with what the person saw. Companies with logged outreach need confirmation.
- **Our Offerings importer** (`modules/offerings/`): reads the sitemap and menu, keeps a page ledger
  so unchanged pages cost no scrape or model call, extracts proposals (new, changed, removed), checks
  each description against the page, and never changes live data without approval. Removal means
  archive, only when a page really answers 404 or 410.
- **Leadership dashboard** (`dashboard/`): read-only; KPIs, funnel, context.dev spend against its
  ceiling, attention queue, recent activity, and a Cost and health panel (30-day estimated spend by
  provider, `GET /usage/summary`).
- **Tracker and cadence** (`outreach/`): logging `sent` or `response_received` derives the
  contact's status and next follow-up via a pure send-window rule (Monday to Wednesday, Thursday if
  urgent, never Friday or weekend, 11:00 in the contact's timezone). No model involved. A/B variant
  data is captured; reporting on it is not built.
- **Needs Review and bulk confirm**: uncertain companies and contacts are flagged, not trusted;
  bulk confirm clears a batch and resumes role classification and drafting.

## 5. How it decides, and why you can trust it

- **The model judges, code decides.** Verdicts, priorities, scores and offering bands come from code
  over per-item judgments that cite evidence.
- **Quotes are checked.** A verdict whose verbatim quote is not in its cited source becomes "could
  not determine". Descriptions are checked against their pages.
- **A person decides.** Offerings proposals, flagged companies, contacts and drafts all wait for a
  person. Nothing is sent automatically. Every review decision is recorded.
- **Nothing is silently changed.** Judgment and activity tables are append-only; configuration is
  retired with `is_active`, not deleted.
- **Web text is data.** Scraped pages, snippets, news and job posts are fenced in every prompt and
  the model is told to ignore instructions inside them (a first layer, not a guarantee).
- **Every AI row is traceable.** `model_used` and `prompt_version` on every AI-written row; every
  call metered by task, run and company; prompt changes require an eval report.
- Governance controls G1 to G10, their status and the key-free checks that enforce them are in
  [`docs/ai-governance.md`](docs/ai-governance.md); the checks run with
  `pytest governance_checks` from `backend/`.

## 6. Configuration recorded in the org

The org is `00000000-0000-0000-0000-000000000001`. The configuration below was last recorded on
2026-10-20 and is edited in the app, so check the live Our Offerings, criteria and role category
screens for current values.

- **Offerings**: InfoBeans digital transformation and product engineering (Salesforce, ServiceNow,
  AI and Generative AI, enterprise apps, cloud migration, DevOps) and a separate SAP ECC to S/4HANA
  migration and managed support offering ahead of SAP's 2027 deadline, kept separate so a rep can
  select both and let drafting choose per company. Offerings are now imported from the website with
  approval.
- **Criteria** (optional per search; informational on a company): digital transformation maturity,
  operates in Europe (worded around the parcel and postal market, a holdover from early test runs),
  SAP ECC exposure.
- **Role categories**: IT / Engineering Leadership, Vendor / IT Procurement, Digital Transformation
  / Innovation, Business / P&L Leadership, Marketing, Product Management. Targets are now chosen per
  run, not set on the category.

## 7. Status

| Area | Status |
|---|---|
| Company Discovery Agent, Market Discovery, CSV upload | Done |
| Qualification (evidence-cited), Priority Score ranking | Done |
| Role classification, per-run target roles, Verify Contacts | Done |
| Drafting by email type and offering kind, "Check before sending" | Done (email only) |
| Tracker and cadence, Follow-ups | Done; A/B reporting not built |
| Our Offerings website import with review | Done |
| Quick Check (Quick Look) with save-as-company | Done |
| Company Brief, offering fit, AI Recommended Areas | Built; not yet reviewed against real data |
| Not a fit, review decision log | Done |
| New run screen and finish summary | Done |
| Leadership dashboard and cost panel | Done |
| AI governance G1 to G10 and key-free checks | Built; some gaps open (see `ai-governance.md`) |
| Evals | 37 cases, nine tasks; four reports committed, five tasks awaiting a first report |
| Contact verification (email and phone validity) | Not built |
| Gmail send, LinkedIn | Not built, deliberately scoped ([ADR 0011](docs/decisions/0011-linkedin-gmail-integration-scope.md)) |
| Sign-in, access control, spend ceiling, deployment | Deferred until there is reason to pursue SaaS |
| Domain-agnostic generalization (Phase D) | Deliberately deferred |

## 8. Known gaps worth tracking

- **No sign-in or access control**: do not expose it publicly as it is.
- **Contact details are found, not verified.** There is no email or phone validity check.
- **Accuracy is unmeasured against real labelled companies**; the eval set is small and five tasks
  have no first report yet.
- **CI runs only the governance checks**: `backend/tests/` and the frontend test files are
  git-ignored, so unit and frontend tests are not part of CI.
- **Free-tier limits** cap how many companies get drafted per run.
- **Hiring coverage is partial** (many companies use their own career sites); Lever gives no posting
  date; trends need at least two collections.
- **Discovery noise**: listicle-shaped names and forum threads can still slip through and land in
  Needs Review. Topic-shaped queries ("companies piloting generative AI") can still return no real
  companies; the system now says why, but does not reformulate the query.
- **"Everything stays in-tool, no external redirects"** was an explicit live-demo critique but is
  not yet written down as a design constraint (it deserves its own ADR).
- **Dangling ADR references**: code cites `0012-context-dev-evaluation.md` and ADR 0013 (Priority
  Score), which were never written. ADR 0014 (AI governance) used its number so those stay free.
- **Naming**: the app's nav says "Quick Check"; code, API and module say "Quick Look".
- **UI brand**: `design-kit/` holds the InfoBeans brand standards (cream, charcoal, crimson, Lexend,
  square corners, light mode only). Whether the product keeps the InfoBeans brand or becomes its own
  is undecided (see `docs/marketing/purple-cow-analysis.md`).

## Sources

- `docs/` (overview, architecture, data model, roadmap, governance) and `docs/decisions/` (ADRs
  0001 to 0011 and 0014).
- `Meeting notes/` for the original working session, `docs/product-assessment-brief.md` for a
  dated 2026-09-29 outside-assessment brief (historical).
- The code itself (`backend/app/modules/`, `frontend/src/features/`) for anything above.
