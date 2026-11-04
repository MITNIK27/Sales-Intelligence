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
for what is built and what is planned, and [`docs/decisions/`](docs/decisions/) for the reasoning
behind the non-obvious choices.

_Documentation last updated: 2026-10-30._

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
- **Quick Check**: type a company name or website, optionally a focus area, and get a qualification
  verdict with evidence.
- **Role categories** and per-run target roles, **Verify Contacts** (confirm or discard before
  drafting), **Drafts** that depend on the email type (first touch, follow-ups 1 to 3) and on
  whether the offering is a product or a service, **Follow-ups** with send-window scheduling, and a
  read-only **leadership dashboard**.

Not built yet: contact verification (email and phone checks), sending through Gmail, and reporting
on template performance. See [`docs/roadmap.md`](docs/roadmap.md).

## Stack

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy (async), Alembic, PostgreSQL
- **Frontend:** TypeScript, React, Vite, Tailwind, Vitest
- **Background jobs:** a Postgres-backed job table and an `asyncio` worker (no broker; see
  `docs/architecture.md` for why). The worker also runs the weekly offerings check.
- **AI and data providers:** Gemini for most language tasks, Groq (tried first, Gemini as fallback)
  for the offerings importer, context.dev as the main page scraper for the importer with the
  in-house scraper as fallback, Serper for web search.

## Local Development

Prerequisites: Docker Desktop (or a local Postgres), Python 3.12+, Node 20+.

```bash
# 1. Copy the env template and fill in the keys you have (never commit .env)
cp .env.example .env

# 2. Start Postgres
docker compose -f infra/docker-compose.yml up -d

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
- The **worker does not reload itself**: restart it after changing backend code. The API does reload.
- Without the worker running, discovery, Quick Check, the offerings check and draft jobs stay
  "pending".
- Run migrations yourself with `alembic upgrade head` after pulling a change that adds one.

### Tests and checks

```bash
cd backend && python -m pytest tests -q && python -m ruff check app tests
cd frontend && npx tsc -b && npx eslint src && npx vitest run
```

## Repository Layout

```
backend/    FastAPI application (modular monolith, see docs/architecture.md)
frontend/   React/TypeScript app
docs/       Overview, architecture, data model, roadmap, and decision records
infra/      Local dev infrastructure (docker-compose)
```
