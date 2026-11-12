"""add company dismissal, discovery evidence and review reasons

Revision ID: a8d3f6e24c19
Revises: f2d8b5c91a37
Create Date: 2026-11-12 11:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'a8d3f6e24c19'
down_revision: str | None = 'f2d8b5c91a37'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # All nullable, no default: no company is dismissed, and companies found before this keep an
    # empty discovery_evidence (it was not kept then). No existing data is rewritten.
    op.add_column('companies', sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('companies', sa.Column('dismissed_reason', sa.String(length=30), nullable=True))
    op.add_column('companies', sa.Column('dismissed_note', sa.String(length=500), nullable=True))
    op.add_column('companies', sa.Column('discovery_evidence', sa.JSON(), nullable=True))
    op.add_column('review_decisions', sa.Column('reason_code', sa.String(length=30), nullable=True))
    op.add_column('review_decisions', sa.Column('note', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('review_decisions', 'note')
    op.drop_column('review_decisions', 'reason_code')
    op.drop_column('companies', 'discovery_evidence')
    op.drop_column('companies', 'dismissed_note')
    op.drop_column('companies', 'dismissed_reason')
    op.drop_column('companies', 'dismissed_at')
