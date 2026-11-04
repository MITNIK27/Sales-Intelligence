"""The light fit stage of a Market Discovery run: once companies are ranked, queue one background
job each to judge which of the run's chosen offerings fit the company overall. It is separate from
the pipeline's own stages on purpose: a slow or failed fit judgment never holds up or fails the
run, and each judgment is cached, so repeating it costs nothing."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.jobs.service import enqueue_job
from app.modules.opportunity.jobs import JOB_TYPE_ANALYSE_OPPORTUNITY
from app.modules.opportunity.models import ORIGIN_MARKET_DISCOVERY
from app.modules.opportunity.service import get_or_create_opportunity


async def queue_run_fit(
    session: AsyncSession,
    organization_id: uuid.UUID,
    run_id: uuid.UUID,
    company_ids: list[uuid.UUID],
    product_ids: list[uuid.UUID],
    limit: int,
) -> int:
    """Queue fit judgments for the first `limit` companies against the run's offerings; returns how
    many were queued. With no offerings chosen there is nothing to judge, so nothing is queued."""
    if not product_ids:
        return 0
    queued = 0
    for company_id in company_ids[:limit]:
        company = await session.get(Company, company_id)
        if company is None or company.organization_id != organization_id:
            continue
        opportunity, _ = await get_or_create_opportunity(
            session, company, None, ORIGIN_MARKET_DISCOVERY, created_by_run_id=run_id
        )
        await enqueue_job(
            session,
            organization_id,
            JOB_TYPE_ANALYSE_OPPORTUNITY,
            {
                "opportunity_id": str(opportunity.id),
                "product_ids": [str(p) for p in product_ids],
                "with_contacts": False,
                "force": False,
            },
        )
        queued += 1
    return queued
