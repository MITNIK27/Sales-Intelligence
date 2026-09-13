"""phase 2a: company-site scraper — enrichment_status/needs_review on companies and contacts

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-03

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column(
            "enrichment_status", sa.String(20), nullable=False, server_default="never_enriched"
        ),
    )
    op.add_column(
        "companies",
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("companies", sa.Column("needs_review_reason", sa.String(255)))
    op.add_column("companies", sa.Column("last_enriched_at", sa.DateTime(timezone=True)))
    op.add_column("companies", sa.Column("enrichment_error", sa.String()))

    op.add_column(
        "contacts",
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("contacts", sa.Column("needs_review_reason", sa.String(255)))


def downgrade() -> None:
    op.drop_column("contacts", "needs_review_reason")
    op.drop_column("contacts", "needs_review")

    op.drop_column("companies", "enrichment_error")
    op.drop_column("companies", "last_enriched_at")
    op.drop_column("companies", "needs_review_reason")
    op.drop_column("companies", "needs_review")
    op.drop_column("companies", "enrichment_status")
