"""add buyer profile to products

Revision ID: b8c3f5a17d94
Revises: a2d9e4b6c183
Create Date: 2026-11-01 13:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'b8c3f5a17d94'
down_revision: str | None = 'a2d9e4b6c183'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # All nullable, no default: every existing offering simply has no profile yet.
    op.add_column('products', sa.Column('buyer_profile', sa.JSON(), nullable=True))
    op.add_column('products', sa.Column('profile_status', sa.String(length=10), nullable=True))
    op.add_column('products', sa.Column('profile_hash', sa.String(length=64), nullable=True))
    op.add_column('products', sa.Column('profile_source_hash', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('products', 'profile_source_hash')
    op.drop_column('products', 'profile_hash')
    op.drop_column('products', 'profile_status')
    op.drop_column('products', 'buyer_profile')
