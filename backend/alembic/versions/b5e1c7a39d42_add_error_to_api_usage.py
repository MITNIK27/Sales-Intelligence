"""add the failure reason to api_usage

Revision ID: b5e1c7a39d42
Revises: a8d3f6e24c19
Create Date: 2026-11-12 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'b5e1c7a39d42'
down_revision: str | None = 'a8d3f6e24c19'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable, no default: calls that failed before this keep "not recorded".
    op.add_column('api_usage', sa.Column('error', sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column('api_usage', 'error')
