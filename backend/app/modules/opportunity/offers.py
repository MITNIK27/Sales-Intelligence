"""What we could offer a company as a whole, with no area chosen. The company is researched in the
areas our offerings are sold into (news, open jobs, the web), the evidence is kept on the company's
general opportunity, and every active offering is judged against it, not only the ones that share a
word with the company. The result is the same cited offering fit the Brief already shows."""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.llm.structured import StructuredLLM
from app.modules.opportunity.analysis import AnalysisResult, active_offerings, analyse_opportunity
from app.modules.opportunity.assessment import assess_opportunity
from app.modules.opportunity.discovery import offering_areas
from app.modules.opportunity.models import ORIGIN_MANUAL, CompanyOpportunity
from app.modules.opportunity.research.collect import collect_area_evidence
from app.modules.opportunity.research.types import ResearchSources, SourceReport
from app.modules.opportunity.service import evidence_records_for, get_or_create_opportunity
from app.modules.usage.context import usage_scope

AREA_TAGS_IN_SEARCH = 6
FALLBACK_AREA = "technology modernisation"


@dataclass
class OffersResult:
    opportunity: CompanyOpportunity
    reports: list[SourceReport] = field(default_factory=list)
    analysis: AnalysisResult = field(default_factory=AnalysisResult)


async def research_company_offers(
    session: AsyncSession,
    llm: StructuredLLM,
    company: Company,
    sources: ResearchSources,
    *,
    force: bool = False,
    now: datetime | None = None,
) -> OffersResult:
    general, _ = await get_or_create_opportunity(session, company, None, ORIGIN_MANUAL)
    tags = await offering_areas(session, company.organization_id)
    area = " ".join(tags[:AREA_TAGS_IN_SEARCH]) or FALLBACK_AREA
    with usage_scope(company_id=company.id, opportunity_id=general.id):
        reports = await collect_area_evidence(
            session, company, general, sources, now=now, force=force, area=area
        )
        records = await evidence_records_for(session, general)
        # The company as a whole, written up from what was found (news, hiring, web) with each
        # finding quoted; this is what the Overall view opens with, before any offering is named.
        await assess_opportunity(session, llm, company, general, records, force=force)
        catalog = await active_offerings(session, company.organization_id)
        analysis = await analyse_opportunity(
            session,
            llm,
            company,
            general,
            records,
            chosen_ids={p.id for p in catalog},  # every offering, not a word-match shortlist
            with_contacts=False,
            force=force,
        )
    return OffersResult(opportunity=general, reports=reports, analysis=analysis)
