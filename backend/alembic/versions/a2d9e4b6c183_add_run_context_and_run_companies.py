"""add run context and run-company membership

Revision ID: a2d9e4b6c183
Revises: f1a6c2d84e57
Create Date: 2026-11-01 12:00:00.000000

"""
import json
import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = 'a2d9e4b6c183'
down_revision: str | None = 'f1a6c2d84e57'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def plan_backfill(
    created: Iterable[tuple[uuid.UUID, uuid.UUID, uuid.UUID]],
    runs: Iterable[tuple[uuid.UUID, uuid.UUID, Any]],
    existing_company_ids: set[uuid.UUID],
) -> list[dict[str, Any]]:
    """Which membership rows to insert for runs that already exist.

    `created` is (company_id, organization_id, run_id) for every company that names a run as its
    source. `runs` is (run_id, organization_id, summary) and the summary's `company_ids` are the
    companies a run reused or matched. Pure so it can be tested; it only adds rows and never
    changes an existing one.
    """
    rows: list[dict[str, Any]] = []
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
    now = datetime.now(UTC)

    def add(run_id: uuid.UUID, company_id: uuid.UUID, org_id: uuid.UUID, relation: str) -> None:
        if (run_id, company_id) in seen:
            return
        seen.add((run_id, company_id))
        rows.append(
            {
                'id': uuid.uuid4(),
                'created_at': now,
                'organization_id': org_id,
                'run_id': run_id,
                'company_id': company_id,
                'relation': relation,
            }
        )

    for company_id, org_id, run_id in created:
        add(run_id, company_id, org_id, 'created')

    for run_id, org_id, summary in runs:
        if isinstance(summary, str):
            try:
                summary = json.loads(summary)
            except ValueError:
                continue
        for raw in (summary or {}).get('company_ids', []):
            try:
                company_id = uuid.UUID(str(raw))
            except ValueError:
                continue
            if company_id in existing_company_ids:
                add(run_id, company_id, org_id, 'reused')
    return rows


def upgrade() -> None:
    # What a rep chose when confirming a run. Nullable: existing runs simply have none.
    op.add_column('ingestion_runs', sa.Column('context', sa.JSON(), nullable=True))

    op.create_table(
        'ingestion_run_companies',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('run_id', sa.Uuid(), nullable=False),
        sa.Column('company_id', sa.Uuid(), nullable=False),
        sa.Column('relation', sa.String(length=10), nullable=False),
        sa.ForeignKeyConstraint(
            ['organization_id'], ['organizations.id'],
            name='fk_ingestion_run_companies_organization_id',
        ),
        sa.ForeignKeyConstraint(
            ['run_id'], ['ingestion_runs.id'], name='fk_ingestion_run_companies_run_id'
        ),
        sa.ForeignKeyConstraint(
            ['company_id'], ['companies.id'], name='fk_ingestion_run_companies_company_id'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', 'company_id', name='uq_ingestion_run_companies_run_company'),
    )
    op.create_index(
        op.f('ix_ingestion_run_companies_organization_id'),
        'ingestion_run_companies', ['organization_id'],
    )
    op.create_index(
        op.f('ix_ingestion_run_companies_run_id'), 'ingestion_run_companies', ['run_id']
    )
    op.create_index(
        op.f('ix_ingestion_run_companies_company_id'), 'ingestion_run_companies', ['company_id']
    )

    # Insert-only backfill from the two older sources, so existing runs show the same companies
    # through the new table as they did before. Nothing existing is changed.
    bind = op.get_bind()
    companies = sa.table(
        'companies',
        sa.column('id', sa.Uuid()),
        sa.column('organization_id', sa.Uuid()),
        sa.column('source_ingestion_run_id', sa.Uuid()),
    )
    runs = sa.table(
        'ingestion_runs',
        sa.column('id', sa.Uuid()),
        sa.column('organization_id', sa.Uuid()),
        sa.column('summary', sa.JSON()),
    )
    links = sa.table(
        'ingestion_run_companies',
        sa.column('id', sa.Uuid()),
        sa.column('created_at', sa.DateTime(timezone=True)),
        sa.column('organization_id', sa.Uuid()),
        sa.column('run_id', sa.Uuid()),
        sa.column('company_id', sa.Uuid()),
        sa.column('relation', sa.String()),
    )
    created = [
        (r[0], r[1], r[2])
        for r in bind.execute(
            sa.select(
                companies.c.id, companies.c.organization_id, companies.c.source_ingestion_run_id
            ).where(companies.c.source_ingestion_run_id.is_not(None))
        )
    ]
    run_rows = [
        (r[0], r[1], r[2])
        for r in bind.execute(sa.select(runs.c.id, runs.c.organization_id, runs.c.summary))
    ]
    existing = {r[0] for r in bind.execute(sa.select(companies.c.id))}
    rows = plan_backfill(created, run_rows, existing)
    if rows:
        bind.execute(sa.insert(links), rows)


def downgrade() -> None:
    op.drop_index(
        op.f('ix_ingestion_run_companies_company_id'), table_name='ingestion_run_companies'
    )
    op.drop_index(op.f('ix_ingestion_run_companies_run_id'), table_name='ingestion_run_companies')
    op.drop_index(
        op.f('ix_ingestion_run_companies_organization_id'), table_name='ingestion_run_companies'
    )
    op.drop_table('ingestion_run_companies')
    op.drop_column('ingestion_runs', 'context')
