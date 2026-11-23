"""The opportunity step of a Quick Check. With an area typed, assess it. Without one, look for
areas the evidence supports and offer them as suggestions the person can choose from. A failure
here never fails the check: the qualification verdict is already worth having, so the step reports
what went wrong and carries on."""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.enrichment.providers.search_contacts import ContactSearchProvider
from app.modules.jobs.errors import friendly_error
from app.modules.llm.structured import StructuredLLM
from app.modules.opportunity.analysis import (
    AnalysisResult,
    analyse_opportunity,
    outcome_message,
)
from app.modules.opportunity.assessment import assess_opportunity
from app.modules.opportunity.discovery import (
    area_knowledge,
    offering_areas,
    save_suggestions,
    suggest_areas,
)
from app.modules.opportunity.fit import latest_matches
from app.modules.opportunity.models import (
    ORIGIN_QUICK_CHECK,
    STATUS_SUGGESTED,
    CompanyOpportunity,
)
from app.modules.opportunity.research.collect import collect_area_evidence
from app.modules.opportunity.research.types import ResearchSources
from app.modules.opportunity.service import (
    evidence_records_for,
    get_or_create_opportunity,
    list_opportunities,
)
from app.modules.opportunity.shortlist import SHORTLIST_SIZE
from app.modules.usage.context import usage_scope

logger = logging.getLogger(__name__)


def _assessment_summary(result: Any) -> dict[str, Any]:
    assessment = result.assessment
    return {
        "assessment_id": str(assessment.id),
        "verdict": assessment.verdict,
        "version": assessment.version,
        "cache_hit": result.cache_hit,
    }


def _fit_summary(analysis: AnalysisResult) -> list[dict[str, Any]]:
    return [
        {
            "product_id": str(m.product_id),
            "product_name": analysis.product_names.get(m.product_id, ""),
            "band": m.band,
            "score": m.score,
        }
        for m in analysis.matches
    ]


async def _fit_step(
    session: AsyncSession,
    llm: StructuredLLM,
    company: Company,
    opportunity: CompanyOpportunity,
    records: list[Any],
    with_contacts: bool,
    contact_search: ContactSearchProvider | None,
    out: dict[str, Any],
    chosen_ids: set[Any] | None = None,
) -> None:
    """Which offerings fit, and (with an area) who matters for the best one. A failure here is
    reported on its own and never loses the assessment or the suggestions already made."""
    try:
        with usage_scope(company_id=company.id, opportunity_id=opportunity.id):
            analysis = await analyse_opportunity(
                session,
                llm,
                company,
                opportunity,
                records,
                chosen_ids=chosen_ids or None,
                max_unchosen=SHORTLIST_SIZE,  # nothing chosen: judge the best few
                with_contacts=with_contacts,
                contact_search=contact_search,
            )
        out["fit"] = _fit_summary(analysis)
        out["contacts_found"] = analysis.contacts_found
        out["fit_notice"] = outcome_message(analysis.reason)
    except Exception as exc:  # noqa: BLE001 - reported separately, the rest is kept
        logger.warning("fit step failed for %s: %s", company.id, exc)
        out["fit_error"] = f"Which offerings fit could not be worked out. {friendly_error(exc)}"


async def run_quick_check_opportunity(
    session: AsyncSession,
    llm: StructuredLLM,
    company: Company,
    area_opportunity: CompanyOpportunity | None,
    sources: ResearchSources | None = None,
    contact_search: ContactSearchProvider | None = None,
    chosen_ids: set[Any] | None = None,
) -> dict[str, Any]:
    """`area_opportunity` is the opportunity for the area the person typed, or None when they
    typed none. With sources, the typed area is researched (news, job boards, the web) before it
    is assessed."""
    out: dict[str, Any] = {
        "opportunity_id": None,
        "area_label": None,
        "assessment": None,
        "suggestions": [],
        "error": None,
    }
    try:
        if area_opportunity is not None:
            out["opportunity_id"] = str(area_opportunity.id)
            out["area_label"] = area_opportunity.area_label
            with usage_scope(company_id=company.id, opportunity_id=area_opportunity.id):
                if sources is not None:
                    reports = await collect_area_evidence(
                        session, company, area_opportunity, sources
                    )
                    out["research"] = [
                        {"kind": r.kind, "found": r.found, "skipped": r.skipped, "error": r.error}
                        for r in reports
                    ]
                records = await evidence_records_for(session, area_opportunity)
                result = await assess_opportunity(session, llm, company, area_opportunity, records)
            out["assessment"] = _assessment_summary(result)
            await _fit_step(
                session,
                llm,
                company,
                area_opportunity,
                records,
                True,
                contact_search,
                out,
                chosen_ids,
            )
            return out

        general, _ = await get_or_create_opportunity(
            session, company, None, origin=ORIGIN_QUICK_CHECK
        )
        out["opportunity_id"] = str(general.id)
        out["area_label"] = general.area_label
        known = [
            o
            for o in await list_opportunities(session, company.organization_id, company.id)
            if o.status == STATUS_SUGGESTED
        ]
        # Areas are suggested once; asking again would spend a model call to say the same thing.
        if not known:
            with usage_scope(company_id=company.id, opportunity_id=general.id):
                records = await evidence_records_for(session, general)
                areas = await offering_areas(session, company.organization_id)
                knowledge = await area_knowledge(session, company, general.industry_context)
                found = await suggest_areas(
                    llm, company, records, areas, general.industry_context, knowledge=knowledge
                )
            known = await save_suggestions(session, company, found)
        # Which offerings fit the company at all; people wait for an area. Run it the first time,
        # whenever offerings were chosen (a repeat check must judge them), and when nothing has
        # been judged yet.
        if chosen_ids or not await latest_matches(session, general.id):
            await _fit_step(
                session,
                llm,
                company,
                general,
                await evidence_records_for(session, general),
                False,
                None,
                out,
                chosen_ids,
            )
        out["suggestions"] = [
            {
                "opportunity_id": str(o.id),
                "label": o.area_label,
                "reason": o.suggestion_reason,
            }
            for o in known
        ]
    except Exception as exc:  # noqa: BLE001 - the verdict is kept even if this step fails
        logger.warning("opportunity step failed for %s: %s", company.id, exc)
        out["error"] = f"The opportunity research could not be completed. {friendly_error(exc)}"
    return out
