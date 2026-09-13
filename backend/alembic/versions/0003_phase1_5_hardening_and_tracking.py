"""phase 1.5: domain uniqueness, job progress, enrichment_records, contact tracking

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-01

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- A1: DB-level uniqueness on companies.domain (backstops the application-level dedup) ---
    op.drop_index("ix_companies_domain", table_name="companies")
    op.create_index(
        "uq_companies_org_domain",
        "companies",
        ["organization_id", "domain"],
        unique=True,
        postgresql_where=sa.text("domain IS NOT NULL"),
    )

    # --- A2: job progress tracking ---
    op.add_column("jobs", sa.Column("progress", sa.JSON()))

    # --- A3: enrichment_records (built now so Phase 2's scraper has it from day one) ---
    op.create_table(
        "enrichment_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_enrichment_records_organization_id", "enrichment_records", ["organization_id"]
    )
    op.create_index("ix_enrichment_records_entity_type", "enrichment_records", ["entity_type"])
    op.create_index("ix_enrichment_records_entity_id", "enrichment_records", ["entity_id"])

    # --- B: minimal follow-up/outreach tracking on Contact ---
    op.add_column(
        "contacts",
        sa.Column("status", sa.String(30), nullable=False, server_default="not_contacted"),
    )
    op.add_column("contacts", sa.Column("next_follow_up_at", sa.DateTime(timezone=True)))
    op.add_column("contacts", sa.Column("next_follow_up_channel", sa.String(20)))
    op.create_index(
        "ix_contacts_next_follow_up_at", "contacts", ["next_follow_up_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_contacts_next_follow_up_at", table_name="contacts")
    op.drop_column("contacts", "next_follow_up_channel")
    op.drop_column("contacts", "next_follow_up_at")
    op.drop_column("contacts", "status")

    op.drop_index("ix_enrichment_records_entity_id", table_name="enrichment_records")
    op.drop_index("ix_enrichment_records_entity_type", table_name="enrichment_records")
    op.drop_index("ix_enrichment_records_organization_id", table_name="enrichment_records")
    op.drop_table("enrichment_records")

    op.drop_column("jobs", "progress")

    op.drop_index("uq_companies_org_domain", table_name="companies")
    op.create_index("ix_companies_domain", "companies", ["domain"])
