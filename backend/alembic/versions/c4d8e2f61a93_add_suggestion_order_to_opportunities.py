"""add suggestion source, rank and focus to company_opportunities

Revision ID: c4d8e2f61a93
Revises: b5e1c7a39d42
Create Date: 2026-11-16

All three columns are nullable, so existing rows are untouched.
"""

import sqlalchemy as sa
from alembic import op

revision = "c4d8e2f61a93"
down_revision = "b5e1c7a39d42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_opportunities", sa.Column("suggestion_source", sa.String(length=20), nullable=True)
    )
    op.add_column("company_opportunities", sa.Column("suggestion_rank", sa.Integer(), nullable=True))
    op.add_column(
        "company_opportunities", sa.Column("suggestion_focus", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("company_opportunities", "suggestion_focus")
    op.drop_column("company_opportunities", "suggestion_rank")
    op.drop_column("company_opportunities", "suggestion_source")
