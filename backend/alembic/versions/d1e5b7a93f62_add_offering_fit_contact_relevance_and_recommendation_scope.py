"""add offering fit, contact relevance and opportunity scope on recommendations and drafts

Revision ID: d1e5b7a93f62
Revises: c9d4a6e2f851
Create Date: 2026-11-04 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'd1e5b7a93f62'
down_revision: str | None = 'c9d4a6e2f851'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Two new, empty tables and nullable columns on two existing ones. No existing row changes:
    # existing recommendations and drafts keep a null opportunity and read as "general".
    op.create_table(
        'opportunity_offering_matches',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('company_opportunity_id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('assessment_id', sa.Uuid(), nullable=True),
        sa.Column('band', sa.String(length=24), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('factors', sa.JSON(), nullable=False),
        sa.Column('reasoning', sa.String(), nullable=False),
        sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('needs_review', sa.Boolean(), nullable=False),
        sa.Column('profile_hash', sa.String(length=64), nullable=True),
        sa.Column('evidence_set_hash', sa.String(length=64), nullable=False),
        sa.Column('prompt_version', sa.String(length=20), nullable=False),
        sa.Column('model_used', sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(
            ['organization_id'], ['organizations.id'],
            name='fk_opportunity_offering_matches_organization_id',
        ),
        sa.ForeignKeyConstraint(
            ['company_opportunity_id'], ['company_opportunities.id'],
            name='fk_opportunity_offering_matches_company_opportunity_id',
        ),
        sa.ForeignKeyConstraint(
            ['product_id'], ['products.id'], name='fk_opportunity_offering_matches_product_id'
        ),
        sa.ForeignKeyConstraint(
            ['assessment_id'], ['opportunity_assessments.id'],
            name='fk_opportunity_offering_matches_assessment_id',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_opportunity_offering_matches_organization_id'),
        'opportunity_offering_matches', ['organization_id'],
    )
    op.create_index(
        op.f('ix_opportunity_offering_matches_company_opportunity_id'),
        'opportunity_offering_matches', ['company_opportunity_id'],
    )
    op.create_index(
        op.f('ix_opportunity_offering_matches_product_id'),
        'opportunity_offering_matches', ['product_id'],
    )

    op.create_table(
        'contact_opportunity_relevance',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('company_opportunity_id', sa.Uuid(), nullable=False),
        sa.Column('contact_id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=True),
        sa.Column('source', sa.String(length=8), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('function', sa.String(length=120), nullable=True),
        sa.Column('reasoning', sa.String(), nullable=False),
        sa.Column('confidence', sa.String(length=8), nullable=True),
        sa.Column('needs_review', sa.Boolean(), nullable=False),
        sa.Column('note', sa.String(length=500), nullable=True),
        sa.Column('assessment_id', sa.Uuid(), nullable=True),
        sa.Column('profile_hash', sa.String(length=64), nullable=True),
        sa.Column('contact_hash', sa.String(length=64), nullable=True),
        sa.Column('prompt_version', sa.String(length=20), nullable=True),
        sa.Column('model_used', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(
            ['organization_id'], ['organizations.id'],
            name='fk_contact_opportunity_relevance_organization_id',
        ),
        sa.ForeignKeyConstraint(
            ['company_opportunity_id'], ['company_opportunities.id'],
            name='fk_contact_opportunity_relevance_company_opportunity_id',
        ),
        sa.ForeignKeyConstraint(
            ['contact_id'], ['contacts.id'], name='fk_contact_opportunity_relevance_contact_id'
        ),
        sa.ForeignKeyConstraint(
            ['product_id'], ['products.id'], name='fk_contact_opportunity_relevance_product_id'
        ),
        sa.ForeignKeyConstraint(
            ['assessment_id'], ['opportunity_assessments.id'],
            name='fk_contact_opportunity_relevance_assessment_id',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_contact_opportunity_relevance_organization_id'),
        'contact_opportunity_relevance', ['organization_id'],
    )
    op.create_index(
        op.f('ix_contact_opportunity_relevance_company_opportunity_id'),
        'contact_opportunity_relevance', ['company_opportunity_id'],
    )
    op.create_index(
        op.f('ix_contact_opportunity_relevance_contact_id'),
        'contact_opportunity_relevance', ['contact_id'],
    )

    # Recommendations and drafts can say which opportunity they were written for.
    op.add_column(
        'recommendations', sa.Column('company_opportunity_id', sa.Uuid(), nullable=True)
    )
    op.add_column(
        'recommendations', sa.Column('opportunity_assessment_id', sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        'fk_recommendations_company_opportunity_id', 'recommendations',
        'company_opportunities', ['company_opportunity_id'], ['id'],
    )
    op.create_foreign_key(
        'fk_recommendations_opportunity_assessment_id', 'recommendations',
        'opportunity_assessments', ['opportunity_assessment_id'], ['id'],
    )
    op.create_index(
        op.f('ix_recommendations_company_opportunity_id'), 'recommendations',
        ['company_opportunity_id'],
    )
    # One recommendation per opportunity, offering and assessment version: a double click or a
    # reopened page cannot create a duplicate. Rows with no opportunity are unaffected (NULLs are
    # distinct), so every existing recommendation stays valid.
    op.create_unique_constraint(
        'uq_recommendations_opportunity_assessment', 'recommendations',
        ['company_opportunity_id', 'product_id', 'opportunity_assessment_id'],
    )
    op.add_column('drafts', sa.Column('company_opportunity_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'fk_drafts_company_opportunity_id', 'drafts',
        'company_opportunities', ['company_opportunity_id'], ['id'],
    )
    op.create_index(op.f('ix_drafts_company_opportunity_id'), 'drafts', ['company_opportunity_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_drafts_company_opportunity_id'), table_name='drafts')
    op.drop_constraint('fk_drafts_company_opportunity_id', 'drafts', type_='foreignkey')
    op.drop_column('drafts', 'company_opportunity_id')
    op.drop_constraint(
        'uq_recommendations_opportunity_assessment', 'recommendations', type_='unique'
    )
    op.drop_index(
        op.f('ix_recommendations_company_opportunity_id'), table_name='recommendations'
    )
    op.drop_constraint(
        'fk_recommendations_opportunity_assessment_id', 'recommendations', type_='foreignkey'
    )
    op.drop_constraint(
        'fk_recommendations_company_opportunity_id', 'recommendations', type_='foreignkey'
    )
    op.drop_column('recommendations', 'opportunity_assessment_id')
    op.drop_column('recommendations', 'company_opportunity_id')
    op.drop_index(
        op.f('ix_contact_opportunity_relevance_contact_id'),
        table_name='contact_opportunity_relevance',
    )
    op.drop_index(
        op.f('ix_contact_opportunity_relevance_company_opportunity_id'),
        table_name='contact_opportunity_relevance',
    )
    op.drop_index(
        op.f('ix_contact_opportunity_relevance_organization_id'),
        table_name='contact_opportunity_relevance',
    )
    op.drop_table('contact_opportunity_relevance')
    op.drop_index(
        op.f('ix_opportunity_offering_matches_product_id'),
        table_name='opportunity_offering_matches',
    )
    op.drop_index(
        op.f('ix_opportunity_offering_matches_company_opportunity_id'),
        table_name='opportunity_offering_matches',
    )
    op.drop_index(
        op.f('ix_opportunity_offering_matches_organization_id'),
        table_name='opportunity_offering_matches',
    )
    op.drop_table('opportunity_offering_matches')
