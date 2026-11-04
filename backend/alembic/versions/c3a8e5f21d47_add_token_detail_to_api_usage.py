"""add cached and thinking token counts to api_usage

Revision ID: c3a8e5f21d47
Revises: a7c3e9d15b24
Create Date: 2026-11-04 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'c3a8e5f21d47'
down_revision: str | None = 'a7c3e9d15b24'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable, no default: every row recorded so far keeps "not recorded" for these two.
    op.add_column('api_usage', sa.Column('cached_tokens', sa.Integer(), nullable=True))
    op.add_column('api_usage', sa.Column('thinking_tokens', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('api_usage', 'thinking_tokens')
    op.drop_column('api_usage', 'cached_tokens')
