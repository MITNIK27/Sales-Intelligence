"""quick check history: every check a person ran, with the answer they got

Revision ID: d4a7c2e9f150
Revises: c8f3a1d6e927
Create Date: 2026-11-25

`company_snapshots` keeps one answer per website and a refresh or a new focus replaces it, so a
person could not see what they had checked before. `quick_check_history` keeps each check with a
copy of its answer. Each person sees their own.

Backfill: one row per existing snapshot (its current answer, dated when it was written), with no
person, since nobody was recorded then; those rows are shown to everyone as checks made before
history was kept. New table only; no existing row changes. The downgrade drops the table.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4a7c2e9f150"
down_revision = "c8f3a1d6e927"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quick_check_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("asked", sa.String(length=255), nullable=True),
        sa.Column("focus", sa.String(length=200), nullable=True),
        sa.Column("criteria", postgresql.JSONB(), nullable=False),
        sa.Column("call", sa.String(length=20), nullable=False),
        sa.Column("summary", postgresql.JSONB(), nullable=False),
        sa.Column("sources", postgresql.JSONB(), nullable=False),
        sa.Column("cached", sa.Boolean(), nullable=False),
        sa.Column("refreshed", sa.Boolean(), nullable=False),
        sa.Column("model_used", sa.String(length=50), nullable=True),
        sa.Column("prompt_version", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quick_check_history")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_quick_check_history_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_quick_check_history_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["company_snapshots.id"],
            name=op.f("fk_quick_check_history_snapshot_id_company_snapshots"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_quick_check_history_org_user_created",
        "quick_check_history",
        ["organization_id", "user_id", "created_at"],
    )
    op.create_index(
        "ix_quick_check_history_org_domain", "quick_check_history", ["organization_id", "domain"]
    )
    op.create_index("ix_quick_check_history_user_id", "quick_check_history", ["user_id"])
    op.create_index("ix_quick_check_history_snapshot_id", "quick_check_history", ["snapshot_id"])

    # The answers already on file, as checks made before history was kept.
    op.execute(
        """
        INSERT INTO quick_check_history (
            id, organization_id, user_id, snapshot_id, domain, name, asked, focus, criteria,
            call, summary, sources, cached, refreshed, model_used, prompt_version, created_at
        )
        SELECT
            gen_random_uuid(), s.organization_id, NULL, s.id, s.domain, s.name, NULL,
            NULLIF(s.summary->>'focus', ''),
            COALESCE(jsonb_path_query_array(s.summary, '$.criteria[*].name'), '[]'::jsonb),
            COALESCE(NULLIF(s.summary->>'call', ''), 'unclear'),
            s.summary, COALESCE(s.sources, '[]'::jsonb), false, false,
            s.model_used, s.prompt_version, COALESCE(s.updated_at, s.created_at, now())
        FROM company_snapshots s
        """
    )


def downgrade() -> None:
    op.drop_index("ix_quick_check_history_snapshot_id", table_name="quick_check_history")
    op.drop_index("ix_quick_check_history_user_id", table_name="quick_check_history")
    op.drop_index("ix_quick_check_history_org_domain", table_name="quick_check_history")
    op.drop_index("ix_quick_check_history_org_user_created", table_name="quick_check_history")
    op.drop_table("quick_check_history")
