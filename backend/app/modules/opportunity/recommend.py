"""A recommendation written for one opportunity and one offering, grounded in what has been verified
about the company in that area. Made when somebody opens the brief for that pair (not only when a
draft is wanted), and only once per assessment version: asking again returns the one that exists."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_recommendation.models import Recommendation
from app.modules.ai_recommendation.recommendation_generator import RecommendationGenerator
from app.modules.ai_recommendation.service import generate_recommendation
from app.modules.companies.models import Company
from app.modules.opportunity.fit import latest_matches
from app.modules.opportunity.models import (
    CompanyOpportunity,
    OpportunityAssessment,
)
from app.modules.opportunity.service import latest_assessment
from app.modules.products.models import Product

_MAX_FINDINGS = 6


def build_opportunity_context(
    opportunity: CompanyOpportunity,
    assessment: OpportunityAssessment | None,
    fit_reasoning: str | None,
) -> str:
    """What the recommendation is told about the area: only things that were verified against
    evidence, each with its source, so it cannot pitch an initiative nobody found."""
    lines = [f"Business area under discussion: {opportunity.area_label}"]
    findings = list((assessment.findings if assessment else [])[:_MAX_FINDINGS])
    if findings:
        lines.append(
            "Verified about this company in this area (use only these, do not invent more):"
        )
        for finding in findings:
            evidence = finding.get("evidence", {})
            source = evidence.get("url") or "company profile"
            lines.append(
                f'- {finding["statement"]} (source: {source}; "{evidence.get("quote", "")}")'
            )
    else:
        lines.append(
            "Nothing specific has been verified about this company in this area; do not claim "
            "any initiative, hiring or intent."
        )
    if fit_reasoning:
        lines.append(f"Why this offering fits (checked): {fit_reasoning}")
    return "\n".join(lines)


async def _existing(
    session: AsyncSession,
    opportunity_id: uuid.UUID,
    product_id: uuid.UUID,
    assessment_id: uuid.UUID | None,
) -> Recommendation | None:
    stmt = select(Recommendation).where(
        Recommendation.company_opportunity_id == opportunity_id,
        Recommendation.product_id == product_id,
        (
            Recommendation.opportunity_assessment_id == assessment_id
            if assessment_id is not None
            else Recommendation.opportunity_assessment_id.is_(None)
        ),
    )
    return (
        (await session.execute(stmt.order_by(Recommendation.created_at.desc()))).scalars().first()
    )


async def ensure_recommendation(
    session: AsyncSession,
    generator: RecommendationGenerator,
    company: Company,
    opportunity: CompanyOpportunity,
    product: Product,
    force: bool = False,
) -> tuple[Recommendation, bool]:
    """The recommendation for this opportunity, offering and assessment version, made now only if
    there is none (or `force`). Returns it and whether it was newly made. Two requests at once
    cannot both create one: the database refuses the second and the first one's result is
    returned."""
    assessment = await latest_assessment(session, opportunity.id)
    assessment_id = assessment.id if assessment else None
    if not force:
        found = await _existing(session, opportunity.id, product.id, assessment_id)
        if found is not None:
            return found, False

    match = (await latest_matches(session, opportunity.id)).get(product.id)
    context = build_opportunity_context(opportunity, assessment, match.reasoning if match else None)
    try:
        async with session.begin_nested():
            recommendation = await generate_recommendation(
                session,
                opportunity.organization_id,
                company.id,
                product.id,
                None,
                generator,
                opportunity_id=opportunity.id,
                assessment_id=assessment_id,
                opportunity_context=context,
            )
    except IntegrityError:
        found = await _existing(session, opportunity.id, product.id, assessment_id)
        if found is None:
            raise
        return found, False
    return recommendation, True


async def list_opportunity_recommendations(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> list[Recommendation]:
    stmt = (
        select(Recommendation)
        .where(Recommendation.company_opportunity_id == opportunity_id)
        .order_by(Recommendation.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())
