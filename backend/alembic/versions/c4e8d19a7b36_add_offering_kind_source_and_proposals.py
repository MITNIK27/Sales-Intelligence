"""add offering kind/source/status to products, add offering_proposals

Revision ID: c4e8d19a7b36
Revises: a3c91e5f7b20
Create Date: 2026-10-28 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'c4e8d19a7b36'
down_revision: str | None = 'a3c91e5f7b20'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing rows become manual, active products: nothing about them changes.
    op.add_column(
        'products',
        sa.Column('kind', sa.String(length=20), server_default='product', nullable=False),
    )
    op.add_column(
        'products',
        sa.Column('source', sa.String(length=20), server_default='manual', nullable=False),
    )
    op.add_column('products', sa.Column('source_url', sa.String(length=512), nullable=True))
    op.add_column('products', sa.Column('source_hash', sa.String(length=64), nullable=True))
    op.add_column(
        'products',
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
    )
    op.add_column('products', sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint(
        'uq_products_organization_id_source_url', 'products', ['organization_id', 'source_url']
    )

    op.create_table(
        'offering_proposals',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=True),
        sa.Column('change', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('source_url', sa.String(length=512), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=True),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_offering_proposals_organization_id'),
        'offering_proposals',
        ['organization_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_offering_proposals_product_id'), 'offering_proposals', ['product_id'], unique=False
    )
    op.create_index(
        op.f('ix_offering_proposals_status'), 'offering_proposals', ['status'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_offering_proposals_status'), table_name='offering_proposals')
    op.drop_index(op.f('ix_offering_proposals_product_id'), table_name='offering_proposals')
    op.drop_index(op.f('ix_offering_proposals_organization_id'), table_name='offering_proposals')
    op.drop_table('offering_proposals')
    op.drop_constraint('uq_products_organization_id_source_url', 'products', type_='unique')
    op.drop_column('products', 'last_seen_at')
    op.drop_column('products', 'status')
    op.drop_column('products', 'source_hash')
    op.drop_column('products', 'source_url')
    op.drop_column('products', 'source')
    op.drop_column('products', 'kind')
