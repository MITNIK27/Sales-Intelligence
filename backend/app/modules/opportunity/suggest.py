"""Suggest opportunity areas for a company from the evidence already on file. Suggesting is one
model call, so it is done once: asking again returns the areas already suggested."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.llm.structured import StructuredLLM
from app.modules.opportunity.discovery import offering_areas, save_suggestions, suggest_areas
from app.modules.opportunity.models import ORIGIN_MANUAL, STATUS_SUGGESTED, CompanyOpportunity
from app.modules.opportunity.service import (
    evidence_records_for,
    get_or_create_opportunity,
    list_opportunities,
)
from app.modules.usage.context import usage_scope


async def suggest_for_company(
    session: AsyncSession, llm: StructuredLLM, company: Company
) -> list[CompanyOpportunity]:
    existing = [
        o
        for o in await list_opportunities(session, company.organization_id, company.id)
        if o.status == STATUS_SUGGESTED
    ]
    if existing:
        return existing
    general, _ = await get_or_create_opportunity(session, company, None, ORIGIN_MANUAL)
    with usage_scope(company_id=company.id, opportunity_id=general.id):
        records = await evidence_records_for(session, general)
        areas = await offering_areas(session, company.organization_id)
        found = await suggest_areas(llm, company, records, areas, general.industry_context)
    return await save_suggestions(session, company, found)
