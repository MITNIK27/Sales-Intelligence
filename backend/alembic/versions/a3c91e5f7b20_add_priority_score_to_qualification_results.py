"""add priority score to qualification results, source/confidence to contacts, provenance to companies

Revision ID: a3c91e5f7b20
Revises: 564bb6626f0a
Create Date: 2026-10-04 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'a3c91e5f7b20'
down_revision: str | None = '564bb6626f0a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('qualification_results', sa.Column('priority_score', sa.Float(), nullable=True))
    op.add_column('qualification_results', sa.Column('score_breakdown', sa.JSON(), nullable=True))
    op.add_column('contacts', sa.Column('source', sa.String(length=100), nullable=True))
    op.add_column('contacts', sa.Column('confidence', sa.Float(), nullable=True))
    op.add_column('companies', sa.Column('field_provenance', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('companies', 'field_provenance')
    op.drop_column('contacts', 'confidence')
    op.drop_column('contacts', 'source')
    op.drop_column('qualification_results', 'score_breakdown')
    op.drop_column('qualification_results', 'priority_score')
