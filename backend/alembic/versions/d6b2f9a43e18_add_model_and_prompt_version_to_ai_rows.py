"""record which model and prompt version wrote each AI row

Revision ID: d6b2f9a43e18
Revises: c3a8e5f21d47
Create Date: 2026-11-04 15:05:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = 'd6b2f9a43e18'
down_revision: str | None = 'c3a8e5f21d47'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables that already record model_used and only need the prompt version.
_PROMPT_VERSION_ONLY = ('drafts', 'qualification_results', 'role_relevance_results', 'recommendations')
# Tables that record neither yet.
_BOTH = ('company_snapshots', 'offering_proposals')


def upgrade() -> None:
    # All nullable, no default: rows written before this keep "unknown" (empty) rather than a
    # guessed value, and no existing data is rewritten.
    for table in _PROMPT_VERSION_ONLY:
        op.add_column(table, sa.Column('prompt_version', sa.String(length=20), nullable=True))
    for table in _BOTH:
        op.add_column(table, sa.Column('model_used', sa.String(length=50), nullable=True))
        op.add_column(table, sa.Column('prompt_version', sa.String(length=20), nullable=True))


def downgrade() -> None:
    for table in _BOTH:
        op.drop_column(table, 'prompt_version')
        op.drop_column(table, 'model_used')
    for table in _PROMPT_VERSION_ONLY:
        op.drop_column(table, 'prompt_version')
