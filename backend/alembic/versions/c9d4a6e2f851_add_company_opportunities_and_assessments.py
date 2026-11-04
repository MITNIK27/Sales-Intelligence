"""add company opportunities, assessments and evidence tagging

Revision ID: c9d4a6e2f851
Revises: b8c3f5a17d94
Create Date: 2026-11-02 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'c9d4a6e2f851'
down_revision: str | None = 'b8c3f5a17d94'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Two new, empty tables plus one nullable column. Nothing existing is changed.
    op.create_table(
        'company_opportunities',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('company_id', sa.Uuid(), nullable=False),
        sa.Column('area_key', sa.String(length=120), nullable=False),
        sa.Column('area_label', sa.String(length=200), nullable=False),
        sa.Column('origin', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('industry_context', sa.String(length=255), nullable=True),
        sa.Column('created_by_run_id', sa.Uuid(), nullable=True),
        sa.Column('suggestion_reason', sa.String(length=500), nullable=True),
        sa.Column('research_log', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ['organization_id'], ['organizations.id'],
            name='fk_company_opportunities_organization_id',
        ),
        sa.ForeignKeyConstraint(
            ['company_id'], ['companies.id'], name='fk_company_opportunities_company_id'
        ),
        sa.ForeignKeyConstraint(
            ['created_by_run_id'], ['ingestion_runs.id'],
            name='fk_company_opportunities_created_by_run_id',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'organization_id', 'company_id', 'area_key', name='uq_company_opportunities_area'
        ),
    )
    op.create_index(
        op.f('ix_company_opportunities_organization_id'), 'company_opportunities',
        ['organization_id'],
    )
    op.create_index(
        op.f('ix_company_opportunities_company_id'), 'company_opportunities', ['company_id']
    )

    op.create_table(
        'opportunity_assessments',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('company_opportunity_id', sa.Uuid(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('verdict', sa.String(length=24), nullable=False),
        sa.Column('summary', sa.String(), nullable=False),
        sa.Column('findings', sa.JSON(), nullable=False),
        sa.Column('not_found', sa.JSON(), nullable=False),
        sa.Column('dropped_count', sa.Integer(), nullable=False),
        sa.Column('evidence_count', sa.Integer(), nullable=False),
        sa.Column('evidence_set_hash', sa.String(length=64), nullable=False),
        sa.Column('prompt_version', sa.String(length=20), nullable=False),
        sa.Column('model_used', sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(
            ['organization_id'], ['organizations.id'],
            name='fk_opportunity_assessments_organization_id',
        ),
        sa.ForeignKeyConstraint(
            ['company_opportunity_id'], ['company_opportunities.id'],
            name='fk_opportunity_assessments_company_opportunity_id',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'company_opportunity_id', 'version', name='uq_opportunity_assessments_version'
        ),
    )
    op.create_index(
        op.f('ix_opportunity_assessments_organization_id'), 'opportunity_assessments',
        ['organization_id'],
    )
    op.create_index(
        op.f('ix_opportunity_assessments_company_opportunity_id'), 'opportunity_assessments',
        ['company_opportunity_id'],
    )

    # Evidence gathered for one area is tagged with it; null means company-level and shared.
    op.add_column(
        'enrichment_records', sa.Column('company_opportunity_id', sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        'fk_enrichment_records_company_opportunity_id', 'enrichment_records',
        'company_opportunities', ['company_opportunity_id'], ['id'],
    )
    op.create_index(
        op.f('ix_enrichment_records_company_opportunity_id'), 'enrichment_records',
        ['company_opportunity_id'],
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_enrichment_records_company_opportunity_id'), table_name='enrichment_records'
    )
    op.drop_constraint(
        'fk_enrichment_records_company_opportunity_id', 'enrichment_records', type_='foreignkey'
    )
    op.drop_column('enrichment_records', 'company_opportunity_id')
    op.drop_index(
        op.f('ix_opportunity_assessments_company_opportunity_id'),
        table_name='opportunity_assessments',
    )
    op.drop_index(
        op.f('ix_opportunity_assessments_organization_id'), table_name='opportunity_assessments'
    )
    op.drop_table('opportunity_assessments')
    op.drop_index(op.f('ix_company_opportunities_company_id'), table_name='company_opportunities')
    op.drop_index(
        op.f('ix_company_opportunities_organization_id'), table_name='company_opportunities'
    )
    op.drop_table('company_opportunities')
