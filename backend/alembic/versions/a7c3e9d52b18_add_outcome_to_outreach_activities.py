"""add outcome to outreach activities

Revision ID: a7c3e9d52b18
Revises: e3b9d5a14c70
Create Date: 2026-11-19

Nullable, so existing activities are untouched.
"""

import sqlalchemy as sa
from alembic import op

revision = "a7c3e9d52b18"
down_revision = "e3b9d5a14c70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("outreach_activities", sa.Column("outcome", sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column("outreach_activities", "outcome")
