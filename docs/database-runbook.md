# Database runbook

PostgreSQL 16 with pgvector, managed by us (Phase 8a). One page for running, changing, backing up and
moving the database. Commands are for Command Prompt, from `backend/` with the venv active, unless
marked otherwise.

## What runs where

| | Local | Notes |
|---|---|---|
| Database server | Docker service `postgres-pgvector` (`infra/docker-compose.yml`), image `pgvector/pgvector:0.8.7-pg16`, host port **5435** | 5434 is often taken by another local project. |
| Working database | `sales_intel` | The app's data. |
| Test database | `sales_intel_test` (same server) | Dropped and rebuilt from the migrations on every test run. The tests refuse any database not named `*_test`. |
| Old server | Docker service `postgres` (Alpine, port 5433) | Retired at the Phase 8a cut-over, kept as a fallback. Delete it (and its volume) once you no longer want the fallback. |
| Extensions | `vector`, `pg_trgm`, `pg_stat_statements` | Created by migration `b2f6c8d41a05`. `pg_stat_statements` also needs `shared_preload_libraries` (set in the compose file). |

Start the server: `docker compose -f infra/docker-compose.yml up -d postgres-pgvector` (from the repo root).

## Connections and roles

| Setting | Used by | Value |
|---|---|---|
| `DATABASE_URL` | API, worker, scripts | the app's connection |
| `MIGRATION_DATABASE_URL` | Alembic only | the schema owner's connection; falls back to `DATABASE_URL` |
| `DB_SSL_MODE`, `DB_SSL_ROOT_CERT` | everything | `disable` locally; `require` or `verify-full` on a hosted database |

- **Two roles.** The schema owner (`sales_intel` locally) runs migrations and maintenance scripts.
  `sales_intel_app` is for the running app: it can read and write rows but cannot change the schema.
  Create or refresh it with `infra/db/create_app_role.sql` (instructions at the top of that file).
  Scripts that truncate or change the schema (`scripts/reset_test_data.py`, migrations) need the owner.
- **Limits per connection** (`backend/app/core/config.py`, `backend/app/db/session.py`): pool of 5 plus 10
  overflow, connections checked before use and recycled every 30 minutes. The API stops a single SQL
  statement after 30 s and a lock wait after 15 s; the worker after 5 min and 60 s; migrations wait at
  most 10 s for a lock and have no statement limit. A model call is not a SQL statement and is not cut off.
- **Who is connected:** `SELECT application_name, state, query_start, query FROM pg_stat_activity
  WHERE datname = 'sales_intel';` shows `sales-intel-api`, `sales-intel-worker`, `sales-intel-migrations`.
- **Slow queries:** `SELECT calls, mean_exec_time, query FROM pg_stat_statements ORDER BY
  mean_exec_time DESC LIMIT 20;`

## Changing the schema (every migration)

Alembic is the only way the schema changes. Never edit tables by hand.

1. **Back up** and prove the backup restores: `python scripts\db_backup.py backup`, then
   `python scripts\db_backup.py restore-check logs\backups\<file>.dump`.
2. **Rehearse** on a copy: restore the dump into a scratch database, run
   `set MIGRATION_DATABASE_URL=<copy url>` and `alembic upgrade head`, then compare fingerprints:
   `python scripts\db_verify.py snapshot --database-url <copy url> --out before.json` (before) and
   `... --out after.json` (after), then `python scripts\db_verify.py compare before.json after.json
   --allow <table or table.column you meant to change>`. It must end with **OK**. Also run
   `alembic downgrade <previous revision>` on the copy and compare again.
3. **Apply** to the working database with the API and worker stopped, compare the same way, start them.
4. **Expand, then contract.** A migration that moves data only adds and copies; the old column is
   removed in a later migration once the new one has been in use. Nothing is moved and deleted in one step.
5. Every migration runs in one transaction: if it fails, nothing is left half-changed.

Writing migrations:
- Name constraints explicitly and wrap the name in `op.f(...)`. The models use a naming convention
  (`app/db/base.py`); without `op.f` Alembic applies it a second time (`ck_<table>_ck_<table>_...`).
- Names must fit Postgres' 63-character limit.
- New string columns that hold a fixed set of values get a CHECK constraint. When code gains a new
  value, a migration must allow it first; `tests/unit/test_status_checks.py` fails until it does.
- New JSON columns use `app.db.types.JsonB` (JSONB). New foreign key columns get `index=True`.

## Backups

- **Take one:** `python scripts\db_backup.py backup` writes `logs\backups\sales_intel_<UTC time>.dump`
  plus a fingerprint, and keeps the newest 14 (`--keep N`). `logs\` is git-ignored; copy dumps somewhere
  off this machine as well, since they contain people's names and email addresses.
- **Check one:** `python scripts\db_backup.py restore-check <dump>` restores it into a throwaway
  database and compares it with the fingerprint taken at backup time. Run it while the app is idle;
  otherwise only `api_usage` and `jobs` may differ.
- **Schedule it** (Windows Task Scheduler, daily): program `cmd.exe`, arguments
  `/c cd /d "C:\Users\Parth\Documents\Sales Intelligence\backend" && .venv\Scripts\python scripts\db_backup.py backup`.
- **Restore for real** (repo root): stop the API and worker, then
  `docker exec infra-postgres-pgvector-1 psql -U sales_intel -d postgres -c "DROP DATABASE sales_intel WITH (FORCE)"`,
  `docker exec infra-postgres-pgvector-1 psql -U sales_intel -d postgres -c "CREATE DATABASE sales_intel"`,
  `docker cp <dump> infra-postgres-pgvector-1:/tmp/restore.dump`,
  `docker exec infra-postgres-pgvector-1 pg_restore -U sales_intel -d sales_intel --no-owner --exit-on-error /tmp/restore.dump`.
  Re-run `infra/db/create_app_role.sql` if the app uses `sales_intel_app`. Start the app.

## Moving to a hosted database

The code needs no change; any managed PostgreSQL that offers the following works (AWS RDS/Aurora,
Azure Database for PostgreSQL, Google Cloud SQL and others):
- PostgreSQL 16 or newer, with the extensions `vector`, `pg_trgm` and `pg_stat_statements` allowed
  (`pg_stat_statements` preloaded).
- Daily backups and point-in-time recovery switched on; the provider's backups replace the local
  schedule above (keep `restore-check` as the proof they work).
- TLS: set `DB_SSL_MODE=verify-full` and `DB_SSL_ROOT_CERT` to the provider's CA certificate.
- Network access limited to the app servers and the office or VPN.
- Two logins: the owner for `MIGRATION_DATABASE_URL`, `sales_intel_app` for `DATABASE_URL`.
- Moving the data: `scripts\db_backup.py backup`, restore the dump into the new server, compare
  fingerprints with `db_verify.py --database-url`, then run `alembic upgrade head` there.

## Documents and vectors (Phase 8)

- **Where the knowledge lives:** `documents`, `document_versions`, `document_pages`,
  `document_chunks` (passages, with a 768-number `embedding` and a `tsv` word index),
  `document_assets`, `document_summaries`, `knowledge_cards` (with their own `embedding` and `tsv`),
  `document_offerings`, `document_ingestion_events` and `document_audit`. No original file is kept,
  so **the database and its backups are the only copy**: back up before deleting documents in bulk.
- **Size:** a vector is about 3 KB, so 10,000 passages and cards are roughly 30 MB of vectors plus
  their HNSW indexes (`ix_document_chunks_embedding`, `ix_knowledge_cards_embedding`).
- **Changing the embedding model** (`DOCUMENTS_EMBEDDING_MODEL`): rows record the model that made
  their vector, so the worker re-embeds everything on its next hourly pass. Search uses only vectors
  of the current model meanwhile (words still work). Expect one embedding call per 20 rows.
- **Rebuilding a vector index** after a large import (slow inserts, or search quality dropping):
  `REINDEX INDEX CONCURRENTLY ix_document_chunks_embedding;` (and the same for the cards index), run
  as the owner while the app is quiet.
- **The app role** gets the new tables automatically (default privileges in
  `infra/db/create_app_role.sql`).

## Known traps

- **Do not reuse a data directory across images.** Alpine (musl) and Debian (glibc) sort text
  differently; always move data by dump and restore.
- **Git Bash rewrites `/tmp/...` paths** passed to `docker exec`; run those commands from Command
  Prompt, or set `MSYS_NO_PATHCONV=1` first.
- **Transaction-mode connection poolers** (PgBouncer and similar) break asyncpg's prepared
  statements. Connect directly or through a session-mode pooler.
