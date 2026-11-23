"""company_opportunities: which documents a suggested area cited, and its prompt version

Revision ID: a6d3f8b20c45
Revises: f4a8c2e61b97
Create Date: 2026-11-23

Phase 8d. A suggested area's reason may now draw on our own documents; the passages it cited are
kept with it so a person can see where it came from, together with the area prompt version that
wrote the reason (G9). New nullable columns only; existing rows are untouched.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a6d3f8b20c45"
down_revision = "f4a8c2e61b97"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_opportunities",
        sa.Column(
            "suggestion_knowledge_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.add_column(
        "company_opportunities",
        sa.Column("suggestion_prompt_version", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("company_opportunities", "suggestion_prompt_version")
    op.drop_column("company_opportunities", "suggestion_knowledge_refs")
