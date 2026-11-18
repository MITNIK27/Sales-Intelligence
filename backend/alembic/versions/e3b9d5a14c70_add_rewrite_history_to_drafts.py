"""add instruction and revisions to drafts

Revision ID: e3b9d5a14c70
Revises: c4d8e2f61a93
Create Date: 2026-11-17

Both columns are nullable, so existing drafts are untouched.
"""

import sqlalchemy as sa
from alembic import op

revision = "e3b9d5a14c70"
down_revision = "c4d8e2f61a93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("drafts", sa.Column("instruction", sa.String(length=600), nullable=True))
    op.add_column("drafts", sa.Column("revisions", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("drafts", "revisions")
    op.drop_column("drafts", "instruction")
