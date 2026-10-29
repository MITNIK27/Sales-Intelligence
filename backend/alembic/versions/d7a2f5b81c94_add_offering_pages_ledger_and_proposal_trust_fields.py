"""add offering_pages ledger and proposal origin/excerpt/grounding fields

Revision ID: d7a2f5b81c94
Revises: c4e8d19a7b36
Create Date: 2026-10-28 18:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'd7a2f5b81c94'
down_revision: str | None = 'c4e8d19a7b36'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'offering_proposals',
        sa.Column('origin', sa.String(length=10), server_default='site', nullable=False),
    )
    op.add_column('offering_proposals', sa.Column('source_excerpt', sa.String(), nullable=True))
    op.add_column('offering_proposals', sa.Column('grounding_flags', sa.JSON(), nullable=True))

    op.create_table(
        'offering_pages',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('url', sa.String(length=512), nullable=False),
        sa.Column('lane', sa.String(length=10), nullable=False),
        sa.Column('title', sa.String(length=512), nullable=True),
        sa.Column('lastmod', sa.DateTime(timezone=True), nullable=True),
        sa.Column('content_hash', sa.String(length=64), nullable=True),
        sa.Column('verdict', sa.String(length=20), nullable=False),
        sa.Column('reason', sa.String(length=255), nullable=True),
        sa.Column('last_fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('force_extract', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'url'),
    )
    op.create_index(
        op.f('ix_offering_pages_organization_id'), 'offering_pages', ['organization_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_offering_pages_organization_id'), table_name='offering_pages')
    op.drop_table('offering_pages')
    op.drop_column('offering_proposals', 'grounding_flags')
    op.drop_column('offering_proposals', 'source_excerpt')
    op.drop_column('offering_proposals', 'origin')
