"""add company snapshots table

Revision ID: e2f7a9c14b68
Revises: d1e5b7a93f62
Create Date: 2026-11-02 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e2f7a9c14b68"
down_revision: str | None = "d1e5b7a93f62"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A new, empty table for Quick Check answers. Nothing existing is touched.
    op.create_table(
        "company_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("offerings_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_company_snapshots_organization_id"), "company_snapshots", ["organization_id"]
    )
    op.create_index(
        "uq_snapshots_org_domain", "company_snapshots", ["organization_id", "domain"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_snapshots_org_domain", table_name="company_snapshots")
    op.drop_index(op.f("ix_company_snapshots_organization_id"), table_name="company_snapshots")
    op.drop_table("company_snapshots")
