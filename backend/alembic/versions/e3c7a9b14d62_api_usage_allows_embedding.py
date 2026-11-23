"""api_usage.kind also allows "embedding"

Revision ID: e3c7a9b14d62
Revises: d5b9f2a73c18
Create Date: 2026-11-23

Phase 8c fix. Embedding calls are logged with kind "embedding", but the CHECK on api_usage.kind
(added in a8e2b4c96f50) only allowed llm, search and credits, so every embedding row was refused and
its cost was not recorded. Only the constraint changes; no rows are touched.
"""

from alembic import op

revision = "e3c7a9b14d62"
down_revision = "d5b9f2a73c18"
branch_labels = None
depends_on = None

_NAME = "ck_api_usage_kind"


def upgrade() -> None:
    op.drop_constraint(op.f(_NAME), "api_usage", type_="check")
    op.create_check_constraint(
        op.f(_NAME), "api_usage", "kind IN ('llm', 'search', 'credits', 'embedding')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM api_usage WHERE kind = 'embedding'")  # the old rule refuses them
    op.drop_constraint(op.f(_NAME), "api_usage", type_="check")
    op.create_check_constraint(op.f(_NAME), "api_usage", "kind IN ('llm', 'search', 'credits')")
