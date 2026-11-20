"""enable postgres extensions: vector, pg_trgm, pg_stat_statements

Revision ID: b2f6c8d41a05
Revises: a7c3e9d52b18
Create Date: 2026-11-20

Phase 8a. Needs a Postgres build that ships pgvector (the `postgres-pgvector` service in
infra/docker-compose.yml, or any hosted Postgres with pgvector); on the old postgres:16-alpine
image this fails with "extension vector is not available", and nothing is changed.
pg_stat_statements also needs `shared_preload_libraries=pg_stat_statements` on the server (set in
the compose file) before it records anything.
"""

from alembic import op

revision = "b2f6c8d41a05"
down_revision = "a7c3e9d52b18"
branch_labels = None
depends_on = None

EXTENSIONS = ("vector", "pg_trgm", "pg_stat_statements")


def upgrade() -> None:
    for name in EXTENSIONS:
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {name}")


def downgrade() -> None:
    for name in reversed(EXTENSIONS):
        op.execute(f"DROP EXTENSION IF EXISTS {name}")
