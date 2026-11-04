"""add api usage table

Revision ID: f1a6c2d84e57
Revises: e5b3a7c92d18
Create Date: 2026-10-31 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'f1a6c2d84e57'
down_revision: str | None = 'e5b3a7c92d18'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A new, empty log. Nothing existing is touched. The id columns deliberately have no foreign
    # keys, so the log survives a test-data wipe and never blocks deleting what it describes.
    op.create_table(
        'api_usage',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=True),
        sa.Column('job_id', sa.Uuid(), nullable=True),
        sa.Column('run_id', sa.Uuid(), nullable=True),
        sa.Column('company_id', sa.Uuid(), nullable=True),
        sa.Column('opportunity_id', sa.Uuid(), nullable=True),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=True),
        sa.Column('task', sa.String(length=60), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('tokens_in', sa.Integer(), nullable=True),
        sa.Column('tokens_out', sa.Integer(), nullable=True),
        sa.Column('units', sa.Integer(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('est_cost_usd', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_api_usage_organization_id'), 'api_usage', ['organization_id'])
    op.create_index(op.f('ix_api_usage_job_id'), 'api_usage', ['job_id'])
    op.create_index(op.f('ix_api_usage_run_id'), 'api_usage', ['run_id'])
    op.create_index(op.f('ix_api_usage_company_id'), 'api_usage', ['company_id'])
    op.create_index(op.f('ix_api_usage_provider'), 'api_usage', ['provider'])


def downgrade() -> None:
    op.drop_index(op.f('ix_api_usage_provider'), table_name='api_usage')
    op.drop_index(op.f('ix_api_usage_company_id'), table_name='api_usage')
    op.drop_index(op.f('ix_api_usage_run_id'), table_name='api_usage')
    op.drop_index(op.f('ix_api_usage_job_id'), table_name='api_usage')
    op.drop_index(op.f('ix_api_usage_organization_id'), table_name='api_usage')
    op.drop_table('api_usage')
