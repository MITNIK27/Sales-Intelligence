import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.ai_recommendation.recommendation_generator import GeminiRecommendationGenerator
from app.modules.companies.models import Company
from app.modules.enrichment.providers.search_contacts import SerperContactSearchProvider
from app.modules.enrichment.providers.search_serper import SerperSearchProvider
from app.modules.enrichment.providers.website_scraper import WebsiteScraperProvider
from app.modules.jobs.models import Job
from app.modules.llm.structured import build_structured_llm
from app.modules.opportunity.analysis import analyse_opportunity, outcome_message
from app.modules.opportunity.assessment import assess_opportunity
from app.modules.opportunity.models import (
    GENERAL_AREA_KEY,
    STATUS_ACTIVE,
    STATUS_SUGGESTED,
    CompanyOpportunity,
)
from app.modules.opportunity.offers import research_company_offers
from app.modules.opportunity.recommend import ensure_recommendation
from app.modules.opportunity.research.collect import collect_area_evidence
from app.modules.opportunity.research.sources import build_research_sources
from app.modules.opportunity.service import evidence_records_for, get_opportunity
from app.modules.opportunity.shortlist import SHORTLIST_SIZE
from app.modules.opportunity.suggest import suggest_with_notice
from app.modules.products.service import get_product
from app.modules.usage.context import usage_scope

logger = logging.getLogger(__name__)

JOB_TYPE_ASSESS_OPPORTUNITY = "assess_opportunity"

ProgressCallback = Callable[..., Awaitable[None]]


async def process_assess_opportunity_job(
    session: AsyncSession, job: Job, progress_callback: ProgressCallback | None = None
) -> dict[str, Any]:
    """Assess one company in one area. Choosing a suggested area is what makes it active; the
    assessment itself is skipped (no model call) when the evidence has not changed since the last
    one, unless a person asked for a fresh look."""
    payload = job.payload or {}
    opportunity = await get_opportunity(
        session, job.organization_id, uuid.UUID(payload["opportunity_id"])
    )
    if opportunity is None:
        raise ValueError("opportunity not found")
    company = await session.get(Company, opportunity.company_id)
    if company is None:
        raise ValueError("company not found")

    if progress_callback:
        await progress_callback(0, 2, detail=f"Researching {opportunity.area_label}")
    if opportunity.status == STATUS_SUGGESTED:
        opportunity.status = STATUS_ACTIVE

    settings = get_settings()
    force = bool(payload.get("force"))
    llm = build_structured_llm(settings, order=settings.opportunity_llm_order)
    scraper = WebsiteScraperProvider(settings)
    sources, closers = build_research_sources(settings, scraper)
    try:
        with usage_scope(company_id=company.id, opportunity_id=opportunity.id):
            # Look for fresh evidence first (each collector skips itself while its last results
            # are still fresh), then judge everything that is now on file.
            reports = await collect_area_evidence(
                session, company, opportunity, sources, force=force
            )
            if progress_callback:
                await progress_callback(1, 2, detail="Judging the evidence")
            records = await evidence_records_for(session, opportunity)
            result = await assess_opportunity(
                session, llm, company, opportunity, records, force=force
            )
            # Match our offerings straight away, so the Brief opens with a best offering and drafts
            # know what was researched. Best effort: a failure here never loses the research.
            fit_judged = 0
            if result.assessment.evidence_count > 0 and opportunity.area_key != GENERAL_AREA_KEY:
                try:
                    analysis = await analyse_opportunity(
                        session,
                        llm,
                        company,
                        opportunity,
                        records,
                        chosen_ids={uuid.UUID(p) for p in payload.get("product_ids") or []},
                        with_contacts=False,
                        max_unchosen=SHORTLIST_SIZE,
                        force=force,
                    )
                    fit_judged = len(analysis.matches)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("offering fit after research failed for %s: %s", company.id, exc)
    finally:
        await scraper.aclose()
        for closer in closers:
            await closer.aclose()
    if progress_callback:
        await progress_callback(2, 2, detail="Done")
    assessment = result.assessment
    return {
        "opportunity_id": str(opportunity.id),
        "assessment_id": str(assessment.id),
        "verdict": assessment.verdict,
        "version": assessment.version,
        "cache_hit": result.cache_hit,
        "offerings_judged": fit_judged,
        "research": [
            {"kind": r.kind, "found": r.found, "skipped": r.skipped, "error": r.error}
            for r in reports
        ],
    }


JOB_TYPE_ANALYSE_OPPORTUNITY = "analyse_opportunity"
JOB_TYPE_RECOMMEND_OPPORTUNITY = "recommend_opportunity"


async def _opportunity_and_company(
    session: AsyncSession, job: Job
) -> tuple[CompanyOpportunity, Company]:
    payload = job.payload or {}
    opportunity = await get_opportunity(
        session, job.organization_id, uuid.UUID(payload["opportunity_id"])
    )
    if opportunity is None:
        raise ValueError("opportunity not found")
    company = await session.get(Company, opportunity.company_id)
    if company is None:
        raise ValueError("company not found")
    return opportunity, company


async def process_analyse_opportunity_job(
    session: AsyncSession, job: Job, progress_callback: ProgressCallback | None = None
) -> dict[str, Any]:
    """Which offerings fit this company in this area, and who matters for the best ones."""
    payload = job.payload or {}
    opportunity, company = await _opportunity_and_company(session, job)
    settings = get_settings()
    if progress_callback:
        await progress_callback(0, 1, detail="Judging which offerings fit")
    llm = build_structured_llm(settings, order=settings.opportunity_llm_order)
    contact_search = SerperContactSearchProvider(settings, SerperSearchProvider(settings))
    with usage_scope(company_id=company.id, opportunity_id=opportunity.id):
        records = await evidence_records_for(session, opportunity)
        result = await analyse_opportunity(
            session,
            llm,
            company,
            opportunity,
            records,
            chosen_ids={uuid.UUID(p) for p in payload.get("product_ids") or []},
            with_contacts=payload.get("with_contacts", True),
            contact_search=contact_search,
            force=bool(payload.get("force")),
            max_unchosen=SHORTLIST_SIZE,
        )
    if progress_callback:
        await progress_callback(1, 1, detail="Done")
    return {
        "opportunity_id": str(opportunity.id),
        "offerings_judged": len(result.matches),
        "contacts_found": result.contacts_found,
        # Set when nothing could be judged, so "done" never hides an empty result.
        "outcome": (
            {"reason": result.reason, "message": outcome_message(result.reason)}
            if result.reason
            else None
        ),
    }


async def process_recommend_opportunity_job(
    session: AsyncSession, job: Job, progress_callback: ProgressCallback | None = None
) -> dict[str, Any]:
    """The recommendation for this opportunity and offering, made once per assessment version."""
    payload = job.payload or {}
    opportunity, company = await _opportunity_and_company(session, job)
    product = await get_product(session, job.organization_id, uuid.UUID(payload["product_id"]))
    if product is None:
        raise ValueError("offering not found")
    if progress_callback:
        await progress_callback(0, 1, detail=f"Writing the recommendation for {product.name}")
    with usage_scope(company_id=company.id, opportunity_id=opportunity.id):
        recommendation, created = await ensure_recommendation(
            session,
            GeminiRecommendationGenerator(get_settings()),
            company,
            opportunity,
            product,
            force=bool(payload.get("force")),
        )
    if progress_callback:
        await progress_callback(1, 1, detail="Done")
    return {"recommendation_id": str(recommendation.id), "created": created}


JOB_TYPE_SUGGEST_AREAS = "suggest_areas"


async def process_suggest_areas_job(
    session: AsyncSession, job: Job, progress_callback: ProgressCallback | None = None
) -> dict[str, Any]:
    """Other opportunity areas this company's evidence points to, saved as suggestions."""
    company = await session.get(Company, uuid.UUID((job.payload or {})["company_id"]))
    if company is None:
        raise ValueError("company not found")
    if progress_callback:
        await progress_callback(0, 1, detail="Looking for other areas")
    settings = get_settings()
    llm = build_structured_llm(settings, order=settings.opportunity_llm_order)
    payload = job.payload or {}
    result = await suggest_with_notice(
        session,
        llm,
        company,
        refresh=bool(payload.get("refresh")),
        selected_ids=[uuid.UUID(p) for p in payload.get("offering_ids") or []],
    )
    if progress_callback:
        await progress_callback(1, 1, detail="Done")
    return {
        "company_id": str(company.id),
        "suggested": len(result.areas),
        "notice": result.notice,
    }


JOB_TYPE_COMPANY_OFFERS = "company_offers"


async def process_company_offers_job(
    session: AsyncSession, job: Job, progress_callback: ProgressCallback | None = None
) -> dict[str, Any]:
    """What we could offer this company as a whole: research it in the areas we sell in, then judge
    every active offering against what was found."""
    payload = job.payload or {}
    company = await session.get(Company, uuid.UUID(payload["company_id"]))
    if company is None or company.organization_id != job.organization_id:
        raise ValueError("company not found")
    settings = get_settings()
    if progress_callback:
        await progress_callback(0, 1, detail="Researching their news, hiring and work")
    scraper = WebsiteScraperProvider(settings)
    sources, closers = build_research_sources(settings, scraper)
    try:
        llm = build_structured_llm(settings, order=settings.opportunity_llm_order)
        result = await research_company_offers(
            session, llm, company, sources, force=bool(payload.get("force"))
        )
    finally:
        await scraper.aclose()
        for closer in closers:
            await closer.aclose()
    if progress_callback:
        await progress_callback(1, 1, detail="Done")
    return {
        "company_id": str(company.id),
        "opportunity_id": str(result.opportunity.id),
        "offerings_judged": len(result.analysis.matches),
        "research": [
            {"kind": r.kind, "found": r.found, "skipped": r.skipped, "error": r.error}
            for r in result.reports
        ],
        "outcome": (
            {
                "reason": result.analysis.reason,
                "message": outcome_message(result.analysis.reason),
            }
            if result.analysis.reason
            else None
        ),
    }
