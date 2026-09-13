# Sales Intelligence

A standalone B2B sales intelligence and data enrichment platform. It automates the manual
B2B prospecting workflow — find companies, find decision-makers, get verified contact info,
figure out what to pitch and why — through a four-stage pipeline:

**Ingest → Enrich → AI Analysis → Reach Out**

See [`docs/architecture.md`](docs/architecture.md) for the full system design and
[`docs/data-model.md`](docs/data-model.md) for the entity model. Architectural decisions still
open or made along the way are tracked in [`docs/decisions/`](docs/decisions/).

## Status

End-to-end functional for the core targeting/qualification workflow: CSV/Market-Discovery
ingestion, enrichment, company qualification scoring, and role-relevance classification are
built. Outreach draft generation and tracker/cadence automation are not yet built. See
[`docs/roadmap.md`](docs/roadmap.md) for the feature-level phase breakdown and
`docs/architecture.md` for the infra/module phase breakdown.

## Stack

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy, Alembic, PostgreSQL
- **Frontend:** TypeScript, React, Vite
- **Background jobs:** a simple Postgres-backed job table + `asyncio` worker (no broker
  infrastructure for now — see `docs/architecture.md` for why)

## Local Development

Prerequisites: Docker Desktop (or a local Postgres instance), Python 3.12+, Node 20+.

```bash
# 1. Copy env template and fill in secrets (API keys etc.)
cp .env.example .env

# 2. Start Postgres (and, once services exist, the backend/frontend) via docker-compose
docker compose -f infra/docker-compose.yml up -d

# 3. Backend: install deps and run migrations
cd backend
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload

# 4. Frontend: install deps and run the dev server
cd ../frontend
npm install
npm run dev
```

## Repository Layout

```
backend/    FastAPI application (modular monolith — see docs/architecture.md)
frontend/   React/TypeScript dashboard
docs/       Architecture, data model, and decision records
infra/      Local dev infrastructure (docker-compose)
```
