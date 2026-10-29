"""add focus to qualification results

Revision ID: e5b3a7c92d18
Revises: d7a2f5b81c94
Create Date: 2026-10-29 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'e5b3a7c92d18'
down_revision: str | None = 'd7a2f5b81c94'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable, no default: every existing result stays a general (no-focus) judgment.
    op.add_column('qualification_results', sa.Column('focus', sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column('qualification_results', 'focus')
