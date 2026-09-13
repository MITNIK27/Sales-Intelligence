"""phase 2c: market discovery — raw_input/parsed_fields/confirmed_at on ingestion_runs

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-04

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ingestion_runs", sa.Column("raw_input", sa.String()))
    op.add_column("ingestion_runs", sa.Column("parsed_fields", sa.JSON()))
    op.add_column("ingestion_runs", sa.Column("confirmed_at", sa.DateTime(timezone=True)))
    # STATUS_AWAITING_CONFIRMATION ("awaiting_confirmation", 21 chars) doesn't fit the original
    # String(20) column — widen it before Market Discovery ever writes that value.
    op.alter_column("ingestion_runs", "status", type_=sa.String(30))


def downgrade() -> None:
    op.alter_column("ingestion_runs", "status", type_=sa.String(20))
    op.drop_column("ingestion_runs", "confirmed_at")
    op.drop_column("ingestion_runs", "parsed_fields")
    op.drop_column("ingestion_runs", "raw_input")
