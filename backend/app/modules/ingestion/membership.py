"""Which companies belong to which run.

A company can show up in many runs, so membership is its own table rather than a single column on
the company. Before it existed a run found its companies in two scattered ways (the run's
`summary["company_ids"]` and `Company.source_ingestion_run_id`, which only ever names the first
run to create the company); readers unioned them by hand and a company that already existed but
was not returned by the keyword index was lost from the run entirely. This module is now the one
place that answers the question, and still honours the old sources for runs older than the table.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.ingestion.models import IngestionRun, IngestionRunCompany

RELATION_CREATED = "created"  # this run found the company and created it
RELATION_REUSED = "reused"  # taken from the existing index instead of searching again
RELATION_MATCHED = "matched"  # found live, but the company already existed


async def link_company_to_run(
    session: AsyncSession,
    organization_id: uuid.UUID,
    run_id: uuid.UUID,
    company_id: uuid.UUID,
    relation: str,
) -> None:
    """Record that a run is about a company. Safe to call twice for the same pair."""
    existing = await session.execute(
        select(IngestionRunCompany.id).where(
            IngestionRunCompany.run_id == run_id, IngestionRunCompany.company_id == company_id
        )
    )
    if existing.first() is not None:
        return
    session.add(
        IngestionRunCompany(
            organization_id=organization_id,
            run_id=run_id,
            company_id=company_id,
            relation=relation,
        )
    )
    await session.flush()


async def list_company_ids_for_run(
    session: AsyncSession, organization_id: uuid.UUID, run_id: uuid.UUID
) -> list[uuid.UUID]:
    """Every company the run is about: the membership rows first, then anything the older
    sources know (companies the run created, and ids kept in its summary), without duplicates."""
    ids: dict[uuid.UUID, None] = {}

    linked = await session.execute(
        select(IngestionRunCompany.company_id)
        .where(
            IngestionRunCompany.organization_id == organization_id,
            IngestionRunCompany.run_id == run_id,
        )
        .order_by(IngestionRunCompany.created_at)
    )
    for company_id in linked.scalars():
        ids.setdefault(company_id, None)

    run = await session.get(IngestionRun, run_id)
    for raw in ((run.summary if run else None) or {}).get("company_ids", []):
        ids.setdefault(uuid.UUID(raw), None)

    created = await session.execute(
        select(Company.id).where(
            Company.organization_id == organization_id,
            Company.source_ingestion_run_id == run_id,
        )
    )
    for company_id in created.scalars():
        ids.setdefault(company_id, None)
    if not ids:
        return []
    dismissed = set(
        (
            await session.execute(
                select(Company.id).where(
                    Company.organization_id == organization_id,
                    Company.id.in_(list(ids)),
                    Company.dismissed_at.is_not(None),
                )
            )
        ).scalars()
    )
    return [company_id for company_id in ids if company_id not in dismissed]
