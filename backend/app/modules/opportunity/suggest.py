"""Suggest opportunity areas for a company from the evidence already on file. Suggesting is one
model call, so by default it is done once: asking again returns the areas already suggested. A
refresh is an explicit second look: it calls the model again and replaces the suggestions."""

import uuid

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.modules.companies.models import Company
from app.modules.llm.structured import StructuredLLM
from app.modules.opportunity.areas import normalize_area_key
from app.modules.opportunity.discovery import offering_areas, save_suggestions, suggest_areas
from app.modules.opportunity.models import ORIGIN_MANUAL, STATUS_SUGGESTED, CompanyOpportunity
from app.modules.opportunity.service import (
    evidence_records_for,
    get_or_create_opportunity,
    list_opportunities,
)
from app.modules.usage.context import usage_scope


async def _in_use(session: AsyncSession, opportunity_id: uuid.UUID) -> bool:
    """Whether anything (an assessment, a match, a draft, evidence...) points at this opportunity.
    Read from the database's own foreign keys, so a table added later is covered."""
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            if fk.column.table.name == CompanyOpportunity.__tablename__:
                found = await session.scalar(
                    select(exists().where(table.c[fk.parent.name] == opportunity_id))
                )
                if found:
                    return True
    return False


async def suggest_for_company(
    session: AsyncSession, llm: StructuredLLM, company: Company, refresh: bool = False
) -> list[CompanyOpportunity]:
    existing = [
        o
        for o in await list_opportunities(session, company.organization_id, company.id)
        if o.status == STATUS_SUGGESTED
    ]
    if existing and not refresh:
        return existing
    general, _ = await get_or_create_opportunity(session, company, None, ORIGIN_MANUAL)
    with usage_scope(company_id=company.id, opportunity_id=general.id):
        records = await evidence_records_for(session, general)
        areas = await offering_areas(session, company.organization_id)
        found = await suggest_areas(llm, company, records, areas, general.industry_context)
    if refresh and not found:
        # Nothing supported: keep what was suggested before rather than leave the person with none.
        return existing
    saved = await save_suggestions(session, company, found)
    if refresh:
        # A new reason replaces the old one, and suggestions this look did not return are dropped
        # unless a person (or the system) has already built something on them.
        reasons = {normalize_area_key(s.label): s.reason for s in found}
        keep = {o.id for o in saved}
        for opportunity in saved:
            if opportunity.status == STATUS_SUGGESTED and opportunity.area_key in reasons:
                opportunity.suggestion_reason = reasons[opportunity.area_key]
        stale = [o for o in existing if o.id not in keep and not await _in_use(session, o.id)]
        if stale:
            await session.execute(
                delete(CompanyOpportunity).where(CompanyOpportunity.id.in_([o.id for o in stale]))
            )
        saved = [o for o in saved if o.status == STATUS_SUGGESTED]
    return saved
