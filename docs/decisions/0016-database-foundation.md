# ADR 0016: PostgreSQL with pgvector, managed by us, as the one database

**Status:** accepted
**Date:** 2026-11-24

## Context

Phase 8 added a knowledge base that needs vector search, and sign-in is coming, so the database had
to be fit for production before more data moved into it. Before Phase 8a the app ran on a stock
Alpine Postgres with default connection settings, no backups, no checks on status values, plain
`JSON` columns, and tests on in-memory SQLite (which does not enforce foreign keys and behaves
differently from Postgres).

Options considered: Supabase (hosted Postgres with its own auth and APIs), a separate vector
database beside Postgres, or plain PostgreSQL with the pgvector extension that we run ourselves.
No hosting provider has been chosen yet; that belongs to the deployment team.

## Decision

1. **Plain PostgreSQL 16 with pgvector, managed by us.** Locally the Docker image
   `pgvector/pgvector:0.8.7-pg16` (service `postgres-pgvector`, port 5435). Any managed Postgres
   that offers PostgreSQL 16+, `vector`, `pg_trgm` and `pg_stat_statements` works later without a
   code change (AWS RDS or Aurora, Azure Database for PostgreSQL, Google Cloud SQL). Not Supabase:
   it would tie sign-in and APIs to one vendor when only the database was needed.
2. **Alembic is the only way the schema changes**, the same migrations building local, CI, test and
   any hosted database. Extensions are created by a migration.
3. **A data-safety protocol for every migration:** back up and prove the backup restores, rehearse
   on a copy, compare table fingerprints before and after (`scripts/db_verify.py`), one transaction
   per migration, expand before contract (nothing moved and deleted in one step), and test the
   downgrade.
4. **The schema says what it means:** JSON columns are `JSONB`; status and kind columns have CHECK
   constraints (a new value needs a migration first); every foreign key has an index; constraint
   names follow one naming convention.
5. **Two roles and set limits.** The schema owner runs migrations; `sales_intel_app` can read and
   write rows but not change the schema. Pools, statement and lock timeouts differ for the API,
   the worker and migrations, and each connection names itself in `pg_stat_activity`.
6. **Tests run on real Postgres**, in a `sales_intel_test` database rebuilt from the migrations on
   every run.
7. **Backups:** `scripts/db_backup.py` takes a compressed dump with a fingerprint and checks it by
   restoring into a throwaway database; a hosted database must add daily backups and point-in-time
   recovery. Since no original document is kept (ADR 0015), the database and its backups are the
   only copy of the knowledge base.
8. **Users live here, sign-in is Firebase.** Firebase Authentication will hold the sign-in only;
   the `users` table (with `firebase_uid`, role and status) and the "who did it" columns are ready
   in Postgres, so sign-in plugs in without another schema change.

The day-to-day commands are in [`docs/database-runbook.md`](../database-runbook.md).

## Consequences

- Easier: one database for rows, vectors and full-text search, joined in one query; one backup
  covers everything; moving to a host is a dump and restore.
- Harder: we run upgrades, backups and monitoring ourselves until a managed host is chosen; every
  new status value needs a migration; schema work follows the protocol, which is slower than
  editing tables.
- Vectors share the database's resources. The 8f load test (4,000 passages and 1,000 cards with
  vectors) searches in well under half a second, but building the HNSW index slows bulk inserts.
- Revisit when a host is chosen (TLS, network rules, its backup and recovery), and if vector search
  starts to compete with the app's own queries, at which point the `VectorStore` interface lets a
  dedicated store take over vectors only.
- The old Alpine server (port 5433) is kept as a fallback until the team decides to remove it.
