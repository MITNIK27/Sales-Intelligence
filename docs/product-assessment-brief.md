# Sales Intelligence — Product Assessment Brief

> **What this document is.** This is the master context file for an outside product/UX/market
> assessment of "Sales Intelligence," run as a Claude.ai Project. Add this file plus the
> knowledge-base files listed at the end to that Project, then run the assessment prompt at the
> bottom. Everything above the prompt is factual background — pulled from the actual codebase,
> architecture docs, ADRs, and a live walkthrough of the running app on 2026-09-29/30 — not
> marketing copy.

## 1. Executive summary

Sales Intelligence is a B2B prospecting and outreach-prep tool built internally at InfoBeans. It
automates the manual workflow a salesperson currently does by hand in Google Sheets: given a
target industry, find companies worth pursuing, find the right decision-makers inside each one
(not just anyone — the *right* function, since title conventions vary wildly company to company),
judge whether each company is actually worth the effort, and draft the first cold outreach email —
with an audit trail of everything so a rep can trust and correct the output rather than blindly
send it.

It is **not** a concept — it is a working, end-to-end system. This assessment ran a real Market
Discovery query ("freight forwarding and logistics companies in Germany, 200–2000 employees")
against the live app during this review: it found 10 real companies (Dachser, myGermany, ITG,
Dimerco, and others), qualified them, classified contacts by role, and got as far as attempting
outreach drafts — all from one text prompt and one confirmation click. Screenshots of that exact
run are in `docs/assessment/screenshots/`.

**Who it's for today:** InfoBeans' own sales/BD team (the tool grew out of one rep's actual
workflow — see Origin, below). **Who it's meant for eventually:** the intent, stated explicitly by
its two originators, is to prove it out internally first and then take it to market as a
standalone product for any B2B sales team. The data model (`Organization`/`User`, multi-tenant
from day one) was built with that second life in mind, even though only one org exists in the
database today.

## 2. Origin & motivation

The project comes directly from a working session between **Paarth Sahni** (building it; AI/ML
engineer) and **Abhas Jain** (the sales rep whose actual workflow it automates) on 2026-09-08 —
transcript in `Meeting notes/`. Abhas's description of his day-to-day is the spec:

- Given an industry ("go figure out which companies can we target"), manually research and
  shortlist companies against informal criteria (IT spend, digital-transformation signals, deal
  size worth pursuing).
- For each shortlisted company, figure out *who* to contact — hard because the same function has
  different titles at different companies ("IT vendor" at one, "category procurement manager" at
  another), and reaching the wrong person gets you ignored, not redirected.
- Track everything in a manually-maintained spreadsheet (name, geography, designation, company,
  LinkedIn URL, per-channel done-flags, next-action date, free-text remarks) — explicitly
  described as the part that burns him out ("half of your enthusiasm goes down").
- Write cold emails by hand to a fairly strict formula: ≤7–8 lines, 1–2 lines credibility, 1–2
  lines a relevant proof point, one closing CTA to get on a call — deliberately *not* stating the
  prospect's problem outright, because an unresearched, over-confident claim is worse than a
  generic hook.

Two design principles came directly out of that conversation and are worth knowing when judging
the product, because they explain choices that otherwise look like odd scope cuts:

1. **"We don't want any person to probably click something and go to the internet himself... we
   want everything to be here."** — an explicit reaction to an early prototype that surfaced raw
   search-result links. This is *why* the discovery agent resolves candidates into structured
   company records instead of a link list, and it's flagged in `docs/roadmap.md` as a principle
   that's real but not yet written up as its own ADR — worth checking whether it's actually held to
   everywhere in the UI.
2. **"Everything actually 100% factual, validated from official sources... anything the agent
   can't define as true, it flags it, it doesn't use it."** — the explicit anti-hallucination
   mandate. This shows up in the codebase as the deliberate pattern (repeated across qualification,
   role-relevance, and drafting) of the LLM only ever producing per-item judgments with evidence,
   while the actual qualify/not-qualify or primary/secondary verdict is computed in plain
   deterministic Python from those judgments — never inferred wholesale by the model.

The stated go-to-market sequencing, also explicit in the transcript: build it, test it between the
two of them, demo internally to leadership ("Mesh") before this document's date, prove it
internally, *then* take it externally — "this is a more universal use case... any salesperson in
any company has to go through these stages."

## 3. Product vision & target users

- **Now:** internal tool for InfoBeans sales/BD reps, one organization, one shared instance.
- **Later (explicit intent, not yet built toward):** a sellable, multi-tenant SaaS product for any
  B2B sales team. `docs/architecture.md` calls this out directly as "Phase 7 — SaaS readiness,
  deferred until there are green flags to pursue it," and the `Organization`/`User` multi-tenant
  model has existed since Phase 0 specifically so this doesn't require a schema migration later.
- **What's genuinely reusable vs. sales-specific today:** qualification criteria, role categories,
  and the product catalog are already org-configurable database rows, not hardcoded logic — so
  *what* the system judges companies/contacts against is already flexible per tenant. What's
  *not* generalized: the pipeline shape itself (discover → qualify → classify → draft) and the
  domain vocabulary throughout the code (`Company`, `Contact`, `QualificationResult`, ...) are
  sales-specific. `docs/roadmap.md` calls a fully domain-agnostic version ("Phase D — Workflow
  Generalization") out as deliberately deferred, real future work, not an afterthought.

## 4. Architecture overview

- **Stack:** Python 3.12 / FastAPI / SQLAlchemy (async) / Alembic / PostgreSQL on the backend;
  TypeScript / React 18 / Vite / Tailwind on the frontend.
- **Shape:** a modular monolith — one deployable FastAPI app with strict module boundaries
  (`backend/app/modules/{auth,credits,jobs,ingestion,discovery_agent,enrichment,companies,
  contacts,verification,ai_recommendation,products,qualification,role_relevance,draft,outreach,
  orchestrator}`), chosen explicitly to keep operational overhead low for an internal-first tool
  while leaving a clean seam to split a module into its own service later.
- **Background jobs:** no message broker. A plain Postgres `jobs` table plus an `asyncio` worker
  process poll for pending work; the frontend polls `GET /jobs/{id}` for progress. Deliberately
  minimal — the team's own reasoning is documented in `docs/architecture.md`.
- **LLM:** Google Gemini, free tier, behind a thin client abstraction so the provider can be
  swapped without touching prompt/orchestration logic.
- **Data sourcing:** in-house scraping of company websites plus a search-based contact discovery
  provider that reads only what Google/Serper already indexed on a trusted-domain allowlist
  (default: linkedin.com) — it never logs into or scrapes LinkedIn directly, a deliberate ToS/
  account-ban avoidance decision (ADR 0001, ADR 0010).
- **Architectural decision records** (`docs/decisions/`, 11 so far) are the authoritative detail
  on every non-obvious choice — data sourcing strategy, LLM provider choice, the job mechanism,
  the discovery agent design, qualification scoring, role-relevance classification, tracker
  cadence, outreach draft generation, auto-pipeline orchestration, search-based contact discovery,
  and the explicit decision to *not* build LinkedIn/Gmail account integration yet. All are in the
  knowledge-base upload list below — read them for real depth rather than relying on this
  summary.

## 5. Core pipeline & live UX walkthrough

The product frames itself as four stages — **Ingest → Enrich → AI Analysis → Reach Out** — and the
UI now makes that pipeline visible per-company via a status stepper (Discovered → Enriched →
Qualified → Roles classified → Drafted). Screenshots below are all from a live run against the
actual local instance during this review, not mockups.

### 5.1 Getting companies in

![Dashboard](assessment/screenshots/01-dashboard.png)
![Upload CSV](assessment/screenshots/02-upload-csv.png)

Two entry points: upload a CSV of known prospects (dedupes automatically), or describe a target
market in plain English and let the system find companies itself. The dashboard is a flat grid of
every capability — simple, no onboarding flow, assumes the user already knows what each tile does.

### 5.2 Market Discovery → one-click auto-pipeline (the newest, headline feature)

This is the most important flow to evaluate, since it's what turns four separately-triggered tools
into one prompt-driven pipeline.

1. **Describe the market** in plain text. We entered "Freight forwarding and logistics companies
   in Germany, 200-2000 employees."

   ![Market Discovery, empty](assessment/screenshots/03-market-discovery-empty.png)

2. **Confirm the parsed interpretation** — the system correctly split this into industry keywords
   ("freight forwarding, logistics"), location ("Germany"), and employee range ("200-2000") for the
   rep to correct before anything runs. This confirm-before-run step exists specifically because of
   the "everything factual, nothing assumed" principle from the origin conversation.

   ![Confirm interpretation](assessment/screenshots/04-market-discovery-parsed.png)

3. **One click — "Confirm & Start Discovery"** — starts a single background job that chains
   *market discovery → qualification → role-relevance classification → draft generation*
   automatically, showing live stage progress.

   ![Auto-pipeline running](assessment/screenshots/05-auto-pipeline-running.png)

4. **Result:** in this run, 10 real candidate companies were found and created (Dachser,
   myGermany, ITG, 7 Worldwide Logistics, ASF Global Logistics, Fulfillment-Box, and others — all
   genuine German freight/logistics companies, not noise), all 10 were qualified, 1 company was
   carried through to role classification, and drafting was skipped for it ("no primary-target
   contacts identified").

   ![Auto-pipeline done](assessment/screenshots/06-auto-pipeline-done.png)

**Observations worth the assessor's attention, not just the happy path:**

- **All 10 candidates were qualified — 0 rejected**, and this matched the pattern in the
  pre-existing seed data too (below: the full company list — every single company, including
  several where enrichment *failed outright*, is marked QUALIFIED). Either the configured
  qualification criteria in this environment are too permissive to be a meaningful filter, or
  qualification is not actually gating on enrichment success — both worth the assessor digging
  into via `docs/decisions/0005-qualification-scoring.md` and the live qualification criteria
  shown in 5.6, since a qualification step that never says "no" isn't doing its job.

  ![Companies list after the run](assessment/screenshots/07-companies-list.png)

- **Website enrichment fails often.** Several companies (Royal Mail, and Dimerco from this run)
  show "could not fetch homepage" — yet still show a "Qualified" verdict and proceed through the
  pipeline with zero contacts:

  ![Company detail, enrichment failed](assessment/screenshots/09-company-detail-enrichment-failed.png)

  Contrast with ITG, where enrichment succeeded and produced real signals (news mentions, hiring
  posts) and 4 classified contacts. Enrichment reliability is a real gate on whether the rest of
  the pipeline has anything to work with.

  ![Company detail, full pipeline](assessment/screenshots/08-company-detail-full-pipeline.png)

- **The 5-company cap is real and working as designed** (ADR 0009): only 1 of the 10 qualified
  companies from this run got carried through to role-classification/drafting automatically — by
  design, to protect the shared Gemini free-tier quota. This is a genuine constraint on how useful
  one "auto-pipeline" run is at scale, and worth the assessor weighing explicitly: is this
  acceptable for an internal free-tier tool, and does it need to change before this could be sold
  as a product with real usage volume?

### 5.3 Per-company detail & pipeline visibility

Each company page shows the same five-stage stepper, enrichment signals (news/hiring mentions),
qualification verdict, contact list, and draft status (see the two screenshots above). This was a
recent UX fix in its own right — previously these were five disconnected manual buttons in an
order that didn't match the actual pipeline; `docs/roadmap.md`'s "Company Page UX — Pipeline
Visibility" entry documents the before/after.

### 5.4 Needs Review & bulk confirm

![Needs Review](assessment/screenshots/11-needs-review.png)

Search-derived and low-confidence matches are flagged `needs_review` rather than silently trusted
or silently blocking the pipeline — consistent with the "don't assume, flag it" principle. A bulk
"Confirm all" action exists so a rep isn't stuck confirming one company at a time.

### 5.5 Follow-ups

![Follow-ups](assessment/screenshots/10-follow-ups.png)

Replaces the manual "when do I need to follow up on whom" tracking Abhas described as the most
draining part of his current process — a live due/overdue list instead of a spreadsheet a rep has
to remember to open.

### 5.6 Products, Qualification Criteria, Role Categories, Quick Check

![Products](assessment/screenshots/12-products.png)
![Qualification Criteria](assessment/screenshots/13-qualification-criteria.png)
![Role Categories](assessment/screenshots/15-role-categories.png)
![Quick Check](assessment/screenshots/14-quick-check.png)

These are the org-configurable building blocks everything else judges against: what you sell (for
grounding draft copy in a real proof point), what makes a company worth pursuing, and which
functions at a target company actually matter. Quick Check is the ad hoc "someone just mentioned
this company, is it worth pursuing right now" case Abhas described explicitly — type a name, get
an instant qualification verdict without a full discovery run.

## 6. Current state vs. roadmap

Per `docs/roadmap.md` (the single source of truth for feature-level status), as of this branch:

**Done:** company discovery agent, qualification criteria + judgment + quick check + list
surfacing, role-relevance classification, tracker/cadence auto-updates and send-window scheduling,
outreach draft generation (**email only** — cold email + one follow-up, human-in-the-loop edit
before "Log as Sent"), the one-prompt auto-pipeline orchestrator, companies-list sorting/paging,
in-house search-based contact discovery, company-page pipeline visibility, and a real bug fix
(`needs_review` was being force-set on every Market Discovery company regardless of actual
confidence, blocking the pipeline unnecessarily — now fixed, plus bulk confirm was added).

**Deliberately not built yet, with reasons on record:**

- **Contact verification** (email/phone validity checking) — Phase 5, not started.
- **Actual outreach sending** — drafts are generated and edited, but sending is still a manual
  "send it yourself, then click Log as Sent" step; no Gmail/email-adapter integration exists.
  ADR 0011 explicitly identifies Gmail send (not LinkedIn account integration, which is
  deliberately ruled out on ToS/ban-risk grounds) as the highest-value next step here.
- **A/B template-variant reporting** — the data (`template_variant`) is being captured on every
  send already, but the aggregate response-rate-per-variant view doesn't exist yet.
- **Domain-agnostic workflow generalization** (using this outside sales entirely) — raised in the
  original meeting, explicitly deferred as its own future phase.
- **The "no external redirects" principle** from the origin conversation is real but not yet
  written up as an enforced design constraint (own ADR) — flagged by the team itself as a gap.

**One factual inconsistency found during this review, worth fixing regardless of the assessment:**
the root `README.md`'s "Status" section still says *"Outreach draft generation and tracker/cadence
automation are not yet built"* — that is stale. Both are done per `docs/roadmap.md` and were
directly observed working in the live walkthrough (draft generation is wired into the auto-
pipeline; e.g. `06-auto-pipeline-done.png` shows a real "Drafting" stage result).

## 7. Access notes for the assessor

This brief, the screenshots embedded in it, and the knowledge-base files listed below are the
**primary evidence** for this assessment — they were gathered directly from the running local
instance and the actual codebase, not from documentation claims alone. A live `localhost` link to
the running app is **not reachable from a Claude.ai Project** (project knowledge bases have no
outbound network access), so do not attempt to browse to one. If a future run of this assessment
happens inside an environment that *does* have live desktop/browser access, the app runs at
`http://localhost:5173` (frontend) with the API at `http://localhost:8000` — but absent that,
treat this document as the complete picture, and say explicitly in your assessment if something
would need live interaction to verify further.

---

## 8. The assessment prompt

*(Everything below this line is the instruction set for the assessing Claude session. Run it as
your first message in the Project, or as a standing Project instruction.)*

You are acting as an independent, outside product strategist and UX reviewer evaluating
**Sales Intelligence**, a B2B prospecting/outreach-prep platform built internally at InfoBeans,
with the explicit long-term intent of selling it as a standalone product in the broader market —
not just for internal InfoBeans use. You have this brief document, the screenshots embedded in it,
and the project's real documentation (README, architecture, data model, roadmap, and all
architectural decision records) as your knowledge base.

Do the following, in order:

1. **Build an accurate model of the system first.** Read this brief and the attached docs fully
   before forming opinions. Where the brief flags something as observed-but-unresolved (e.g. the
   100% qualification rate, enrichment failures, the README status discrepancy), treat that as a
   pointer to investigate via the ADRs and data model, not as a settled conclusion.
2. **Judge UX and flow coherence.** Does the one-click auto-pipeline actually deliver on "give it a
   prompt and it works on its own"? Is the per-company pipeline stepper an honest, legible
   representation of what actually happened? Where would a first-time user (an InfoBeans rep who
   has never used it) get confused or stuck? Use the actual screenshots, not just feature
   descriptions, to judge this.
3. **Judge whether the implementation matches the original ideation.** Compare what's built against
   the origin conversation (Section 2) and `docs/roadmap.md`'s "Known mismatches vs. meeting
   notes" section. Where does the product undersell or oversell what it promises?
4. **Research the market.** Identify and evaluate this product against real, current competitors
   and adjacent categories via web search — at minimum consider B2B contact/company data providers
   (Apollo.io, ZoomInfo, Clearbit, Lusha, Cognism, Seamless.AI), AI-driven prospecting/enrichment
   tools (Clay, Clay-style workflow builders), and sales engagement/outreach platforms (Outreach,
   Salesloft, Instantly, Smartlead). For each, note briefly what they do that this doesn't (or vice
   versa) — pricing model, data breadth, integrations, and anything structurally hard to replicate
   (e.g. proprietary contact databases).
5. **Rate the system** on each of these axes, with a short justification for each score (use
   whatever scale you find clearest, e.g. 1–10, but be consistent and explain what would move the
   score):
   - Technical architecture and engineering soundness
   - UX quality and flow coherence
   - Feature completeness against the product's own stated vision
   - Competitive differentiation in the current market
   - Readiness for external, paid, multi-tenant market use
   - Readiness for broader internal InfoBeans rollout (beyond the two people who built/tested it)
6. **Give concrete, prioritized, actionable feedback.** Not a generic SWOT — specific next steps,
   ranked by impact, distinguishing what's needed to safely expand internal InfoBeans usage from
   what's needed before any external/market attempt would be credible. Call out anything you
   believe is a real risk (data provenance/hallucination claims, LinkedIn ToS exposure, qualification
   criteria that don't actually filter, free-tier quota ceilings) as clearly as you call out
   opportunities.
7. **Give an explicit recommendation** on sequencing: what should happen before wider internal
   rollout, and separately, what would need to be true before an external/market push makes sense,
   given this is explicitly the founders' stated long-term goal.

---

## 9. Knowledge-base upload checklist

Add this file plus the following, unmodified, to the Claude.ai Project's knowledge base:

- `README.md`
- `docs/architecture.md`
- `docs/data-model.md`
- `docs/roadmap.md`
- `docs/decisions/0001-data-sourcing-strategy.md`
- `docs/decisions/0002-llm-provider.md`
- `docs/decisions/0003-background-job-mechanism.md`
- `docs/decisions/0004-discovery-agent.md`
- `docs/decisions/0005-qualification-scoring.md`
- `docs/decisions/0006-role-relevance-classification.md`
- `docs/decisions/0007-tracker-cadence.md`
- `docs/decisions/0008-outreach-draft-generation.md`
- `docs/decisions/0009-auto-pipeline-orchestration.md`
- `docs/decisions/0010-search-based-contact-discovery.md`
- `docs/decisions/0011-linkedin-gmail-integration-scope.md`
- `Meeting notes/Sales Funnel Automation Discussion  - 2026_09_08 16_31 IST - Notes by Gemini.md`
  (use only this file, not the `(1)`/`(2)` duplicates alongside it)

All screenshots referenced above are already embedded via relative path in
`docs/assessment/screenshots/` — if your Project tooling doesn't render relative image paths,
upload that folder's contents as well.
