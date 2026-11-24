# Sales Intelligence

A B2B sales intelligence platform built at InfoBeans for its sales and customer-success teams. It
takes over the manual prospecting workflow: find companies, find the right decision-makers, judge
whether each company is worth pursuing, decide what to pitch, and draft the outreach, with the
evidence for every step visible so a person can trust and correct the result.

**Ingest → Enrich → AI Analysis → Reach Out**

A person always has the final say. Nothing the system finds about InfoBeans' own offerings goes
live until it is approved, contacts are confirmed before anything is drafted for them, and nothing
is sent automatically.

Start with [`docs/project-overview.md`](docs/project-overview.md) for what the product does and how
it is used. Then [`docs/architecture.md`](docs/architecture.md) for the system design,
[`docs/data-model.md`](docs/data-model.md) for the entities, [`docs/roadmap.md`](docs/roadmap.md)
for what is built and what is planned, [`docs/ai-governance.md`](docs/ai-governance.md) for the
rules wherever a language model is used, and [`docs/decisions/`](docs/decisions/) for the reasoning
behind the non-obvious choices. [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) is the long, single-file
deep-context brief (the pipeline stage by stage, how it decides, current configuration).

_Documentation last updated: 2026-11-24._

## Status

End-to-end functional. A rep describes a target market in plain words (or uploads a CSV), confirms
the interpretation, and one background run discovers companies, enriches them, qualifies them with
cited evidence, ranks them, classifies contacts by role, and drafts first emails for the contacts
the rep confirms.

Built and in use:

- **Market Discovery and CSV upload**, with a Priority Score ranking and a run worklist.
- **Our Offerings**: the services and products InfoBeans sells, imported from the company website
  as proposals a person approves, with a "What was checked" coverage view. Hand-added entries are
  kept and marked Manual.
- **Quick Check**: type a company name or website, optionally a focus area, and get a short answer
  with evidence, the offerings that might fit, and a yes, maybe or no call. Nothing is saved as a company until
  you save it.
- **Company Brief**: per company and business area, a map from evidence to engagement, with
  verified, inferred and unsupported links drawn differently, and **AI Recommended Areas** chips
  suggested from the evidence on file.
- **Not a fit**: mark a company out, with a reason, singly or in bulk, and Undo. It is then left out
  of every automatic step and does not come back from later searches.
- **Role categories** and per-run target roles, **Verify Contacts** (confirm or discard before
  drafting), **Drafts** that depend on the email type (first touch, follow-ups 1 to 3) and on
  whether the offering is a product or a service, with a **Check before sending** note for figures
  or past-work claims the email was not given, **Follow-ups** with send-window scheduling, and a
  read-only **leadership dashboard** with a cost and health panel.
- **Documents**: upload decks, PDFs, Word and text files about what we sell. They are read into
  searchable passages, a summary and knowledge cards (short facts checked against their source),
  and the offering fit, recommendation, area suggestions and Quick Check cite them as "From our
  documents". Only Gemini ever sees their content; a wrong card can be hidden; offering
  descriptions change only when a person approves.
- **Sign-in and access**: sign in with an InfoBeans Google account; access by invitation on
  **User Management** (admins and managers), with roles, Request access for newcomers, and who did
  what recorded on uploads, decisions, searches, jobs and AI calls.
- **AI governance**: control checks that run without keys (`backend/governance_checks/`), a
  hand-written eval set and reports (`backend/evals/`), prompt and model versions on every
  AI-written row, and per-call cost metering (`backend/scripts/usage_report.py`).

Not built yet: contact verification (email and phone checks), sending through Gmail, separation
between organisations, and reporting on template performance. See [`docs/roadmap.md`](docs/roadmap.md).

## Stack

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy (async), Alembic, PostgreSQL 16 with pgvector
  (see [`docs/database-runbook.md`](docs/database-runbook.md))
- **Frontend:** TypeScript, React, Vite, Tailwind, Vitest
- **Background jobs:** a Postgres-backed job table and an `asyncio` worker (no broker; see
  `docs/architecture.md` for why). The worker also runs the weekly offerings check.
- **AI and data providers:** Gemini for most language tasks, Groq (tried first, Gemini as fallback)
  for the offerings importer, context.dev as the main page scraper for the importer with the
  in-house scraper as fallback, Serper for web search, Gemini embeddings for document search.

## Local Development

Prerequisites: Docker Desktop (or a local Postgres), Python 3.12+, Node 20+.

```bash
# 1. Copy the env template and fill in the keys you have (never commit .env)
cp .env.example .env

# 2. Start Postgres (with pgvector)
docker compose -f infra/docker-compose.yml up -d postgres-pgvector

# 3. Backend: install, migrate
cd backend
pip install -e ".[dev]"
alembic upgrade head

# 4. Run the three processes, each in its own terminal (virtualenv active in the backend ones)
uvicorn app.main:app --reload --port 8003      # API
python -m app.modules.jobs.worker              # background worker
cd ../frontend && npm install && npm run dev   # frontend
```

- The frontend dev server proxies `/api` to `http://localhost:8003`, so the API has to run on 8003.
- **Sign-in** ([ADR 0017](docs/decisions/0017-sign-in-and-access.md)) needs a Firebase project,
  once, with an InfoBeans Google account:
  1. console.firebase.google.com: create a project; Authentication, Sign-in method: enable Google.
  2. In Google Cloud console, same project: OAuth consent screen (Audience), user type Internal.
  3. Firebase Project settings, Your apps: add a Web app and copy `apiKey`, `authDomain`,
     `projectId` and `appId`.
  4. `backend/.env`: `FIREBASE_PROJECT_ID`, `AUTH_ALLOWED_DOMAINS=infobeans.com` and
     `AUTH_BOOTSTRAP_ADMINS=<your email>` (you become the first admin). `frontend/.env.local`: copy
     `frontend/.env.example` and fill in the four `VITE_FIREBASE_*` values. Both are git-ignored.
  5. Sign in, then give others access on **User Management**. No email is sent; tell them.
- The **worker does not reload itself**: restart it after changing backend code. The API does reload.
- Without the worker running, discovery, Quick Check, the offerings check, draft jobs and
  document reading stay "pending".
- Run migrations yourself with `alembic upgrade head` after pulling a change that adds one.

### Tests and checks

```bash
cd backend && python -m pytest governance_checks -q && python -m ruff check . && python -m mypy app evals governance_checks
cd frontend && npx tsc -b && npx eslint src && npx vitest run
```

`governance_checks` need no keys or network and are what CI runs. `backend/tests/` and the frontend
test files are git-ignored (they exist on a developer's machine only), so run them locally with
`python -m pytest tests -q`. Evals call real models only with `python -m evals.run --yes`; the
default is a dry run.

## Repository Layout

```
backend/    FastAPI application (modular monolith, see docs/architecture.md)
  evals/              hand-written eval cases, graders, runner and committed reports
  governance_checks/  key-free tests that enforce the AI governance controls
  scripts/            usage report, offerings audit, data clean-up and other tools
frontend/   React/TypeScript app
docs/       Overview, architecture, data model, roadmap, AI governance, decision records, marketing
infra/      Local dev infrastructure (docker-compose)
design-kit/ InfoBeans brand standards, theme and component patterns for the UI
```
