"""add grounding flags to drafts

Revision ID: e7c1a4d92b53
Revises: d6b2f9a43e18
Create Date: 2026-11-04 17:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'e7c1a4d92b53'
down_revision: str | None = 'd6b2f9a43e18'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable, no default: drafts written so far were never checked, so they carry no flags.
    op.add_column('drafts', sa.Column('grounding_flags', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('drafts', 'grounding_flags')
