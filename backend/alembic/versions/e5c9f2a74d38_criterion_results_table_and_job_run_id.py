"""qualification_criterion_results table, and jobs.ingestion_run_id

Revision ID: e5c9f2a74d38
Revises: d4b8e1f63c27
Create Date: 2026-11-20

Phase 8a, expand step (nothing is removed):
- `qualification_criterion_results`: one row per criterion per qualification result, filled from
  every existing `qualification_results.criteria_results` entry in its original order. The JSON
  column stays and is still written for one release; dropping it is a later, separate migration.
  The upgrade stops (and rolls back) if the row count does not equal the number of JSON entries.
- `jobs.ingestion_run_id`: the run a job works on, copied from `payload.ingestion_run_id` where
  that run still exists. `payload` is unchanged. Set to null if the run is deleted later.

Needs the JSONB migration (c3a7d9e52b16) first: the copy reads criteria_results as jsonb.
"""

import sqlalchemy as sa
from alembic import op

revision = "e5c9f2a74d38"
down_revision = "d4b8e1f63c27"
branch_labels = None
depends_on = None

TABLE = "qualification_criterion_results"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("qualification_result_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("criterion_id", sa.Uuid(), nullable=False),
        sa.Column("criterion_name", sa.String(length=255), nullable=False),
        sa.Column("is_disqualifying", sa.Boolean(), nullable=False),
        sa.Column("scope", sa.String(length=10), nullable=False),
        sa.Column("verdict", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("evidence_ref", sa.String(length=100), nullable=True),
        sa.Column("evidence_quote", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=f"pk_{TABLE}"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_qual_criterion_results_organization",
        ),
        sa.ForeignKeyConstraint(
            ["qualification_result_id"],
            ["qualification_results.id"],
            name="fk_qual_criterion_results_result",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "qualification_result_id", "position", name=f"uq_{TABLE}_qualification_result_id"
        ),
        sa.CheckConstraint("scope IN ('org', 'run')", name=op.f(f"ck_{TABLE}_scope")),
        sa.CheckConstraint(
            "verdict IN ('met', 'not_met', 'could_not_determine')", name=op.f(f"ck_{TABLE}_verdict")
        ),
        sa.CheckConstraint(
            "status IN ('PASS', 'FAIL', 'UNKNOWN')", name=op.f(f"ck_{TABLE}_status")
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f(f"ck_{TABLE}_confidence"),
        ),
    )
    op.create_index(f"ix_{TABLE}_organization_id", TABLE, ["organization_id"])
    op.create_index(f"ix_{TABLE}_qualification_result_id", TABLE, ["qualification_result_id"])

    op.execute(
        f"""
        INSERT INTO {TABLE} (
            id, organization_id, qualification_result_id, position, criterion_id, criterion_name,
            is_disqualifying, scope, verdict, status, reasoning, evidence_ref, evidence_quote,
            confidence, source, url, created_at
        )
        SELECT
            gen_random_uuid(), q.organization_id, q.id, (e.ord - 1)::smallint,
            (e.item->>'criterion_id')::uuid, left(e.item->>'criterion_name', 255),
            (e.item->>'is_disqualifying')::boolean,
            coalesce(e.item->>'scope', 'org'),
            e.item->>'verdict',
            coalesce(
                e.item->>'status',
                CASE e.item->>'verdict' WHEN 'met' THEN 'PASS' WHEN 'not_met' THEN 'FAIL'
                ELSE 'UNKNOWN' END
            ),
            e.item->>'reasoning', e.item->>'evidence_ref', e.item->>'evidence_quote',
            (e.item->>'confidence')::double precision, e.item->>'source', e.item->>'url',
            q.created_at
        FROM qualification_results q
        CROSS JOIN LATERAL jsonb_array_elements(q.criteria_results) WITH ORDINALITY AS e(item, ord)
        """
    )
    op.execute(
        f"""
        DO $$
        DECLARE copied bigint; expected bigint;
        BEGIN
            SELECT count(*) INTO copied FROM {TABLE};
            SELECT coalesce(sum(jsonb_array_length(criteria_results)), 0) INTO expected
                FROM qualification_results;
            IF copied <> expected THEN
                RAISE EXCEPTION 'criterion rows copied (%) <> JSON entries (%)', copied, expected;
            END IF;
        END $$;
        """
    )

    op.add_column("jobs", sa.Column("ingestion_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_jobs_ingestion_run_id_ingestion_runs",
        "jobs",
        "ingestion_runs",
        ["ingestion_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_jobs_ingestion_run_id", "jobs", ["ingestion_run_id"])
    op.execute(
        """
        UPDATE jobs j SET ingestion_run_id = r.id
        FROM ingestion_runs r
        WHERE j.payload->>'ingestion_run_id' = r.id::text
        """
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_ingestion_run_id", table_name="jobs")
    op.drop_constraint("fk_jobs_ingestion_run_id_ingestion_runs", "jobs", type_="foreignkey")
    op.drop_column("jobs", "ingestion_run_id")
    op.drop_index(f"ix_{TABLE}_qualification_result_id", table_name=TABLE)
    op.drop_index(f"ix_{TABLE}_organization_id", table_name=TABLE)
    op.drop_table(TABLE)
