"""add review decisions table

Revision ID: f2d8b5c91a37
Revises: e7c1a4d92b53
Create Date: 2026-11-05 11:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'f2d8b5c91a37'
down_revision: str | None = 'e7c1a4d92b53'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A new, empty log. Nothing existing is touched. The id columns deliberately have no foreign
    # keys, so a decision outlives the company or contact it was about (deleting a contact is one
    # of the decisions it records).
    op.create_table(
        'review_decisions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('subject_type', sa.String(length=20), nullable=False),
        sa.Column('subject_id', sa.Uuid(), nullable=False),
        sa.Column('company_id', sa.Uuid(), nullable=True),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('was_flagged', sa.Boolean(), nullable=False),
        sa.Column('flag_reason', sa.String(length=255), nullable=True),
        sa.Column('snapshot', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_review_decisions_organization_id'), 'review_decisions', ['organization_id']
    )
    op.create_index(op.f('ix_review_decisions_subject_id'), 'review_decisions', ['subject_id'])
    op.create_index(op.f('ix_review_decisions_company_id'), 'review_decisions', ['company_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_review_decisions_company_id'), table_name='review_decisions')
    op.drop_index(op.f('ix_review_decisions_subject_id'), table_name='review_decisions')
    op.drop_index(op.f('ix_review_decisions_organization_id'), table_name='review_decisions')
    op.drop_table('review_decisions')
