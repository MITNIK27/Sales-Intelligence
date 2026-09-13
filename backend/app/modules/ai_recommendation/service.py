import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_recommendation.models import Recommendation
from app.modules.ai_recommendation.recommendation_generator import RecommendationGenerator
from app.modules.companies.service import get_company_detail
from app.modules.enrichment.service import list_company_signals
from app.modules.products.service import get_product


class CompanyNotFoundError(Exception):
    """Raised by `generate_recommendation` when the company doesn't exist or belongs to a
    different organization — the router surfaces this as a 404."""


class ProductNotFoundError(Exception):
    """Raised by `generate_recommendation` when the product doesn't exist or belongs to a
    different organization — the router surfaces this as a 404."""


async def generate_recommendation(
    session: AsyncSession,
    organization_id: uuid.UUID,
    company_id: uuid.UUID,
    product_id: uuid.UUID,
    contact_id: uuid.UUID | None,
    generator: RecommendationGenerator,
) -> Recommendation:
    """Loads the company (+ its contacts), its recent signals, and the target product, then
    calls the given generator and persists a new `Recommendation` row. Append-only: regenerating
    creates a new row rather than updating an existing one, so history is preserved."""
    company = await get_company_detail(session, organization_id, company_id)
    if company is None:
        raise CompanyNotFoundError(f"company {company_id} not found")

    product = await get_product(session, organization_id, product_id)
    if product is None:
        raise ProductNotFoundError(f"product {product_id} not found")

    signals = await list_company_signals(session, organization_id, company_id)

    result = await generator.generate(company, company.contacts, signals, product)

    recommendation = Recommendation(
        organization_id=organization_id,
        company_id=company_id,
        contact_id=contact_id,
        product_id=product_id,
        pitch_summary=result.pitch_summary,
        why_this_company=result.why_this_company,
        talking_points=result.talking_points,
        model_used=generator.model_name,
    )
    session.add(recommendation)
    await session.flush()
    return recommendation


async def list_recommendations(
    session: AsyncSession, organization_id: uuid.UUID, company_id: uuid.UUID
) -> list[Recommendation]:
    stmt = (
        select(Recommendation)
        .where(
            Recommendation.organization_id == organization_id,
            Recommendation.company_id == company_id,
        )
        .order_by(Recommendation.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())
