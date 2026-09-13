# ADR 0003: Background Job Mechanism

**Status:** accepted
**Date:** 2026-08-31

## Context

Scraping, verification, and AI calls are slow and external-API-bound, repeated across many
companies per run — this can't happen inline in an HTTP request. Some background execution
mechanism with progress tracking is required. The standard heavyweight option is Celery + Redis
(a message broker + worker fleet), which is real operational infrastructure to run and debug.

## Decision

Use a Postgres-backed `jobs` table (status: pending/running/done/failed) polled by a single
`asyncio` worker process running alongside the API. The frontend polls a job-status endpoint for
progress. No additional infrastructure (Redis) beyond the Postgres database the app already
needs.

## Consequences

- Minimal operational footprint for a PoC-stage internal tool.
- Throughput is bounded by a single polling worker — fine at current expected volume.
- If volume later genuinely outgrows this, swap to Celery/Arq + Redis. The `jobs` module is the
  intended seam for that swap; nothing above it (ingestion/enrichment/AI/etc.) should need to
  change.
