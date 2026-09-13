import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.ai_recommendation.gemini_client import GeminiClientError
from app.modules.ai_recommendation.recommendation_generator import GeminiRecommendationGenerator
from app.modules.ai_recommendation.schemas import RecommendationGenerateRequest, RecommendationOut
from app.modules.ai_recommendation.service import (
    CompanyNotFoundError,
    ProductNotFoundError,
    generate_recommendation,
    list_recommendations,
)

# Mounted under the companies prefix for locality — a recommendation always belongs to a company.
router = APIRouter(prefix="/companies", tags=["recommendations"])


@router.post(
    "/{company_id}/recommendations", response_model=RecommendationOut, status_code=201
)
async def generate_recommendation_endpoint(
    company_id: uuid.UUID,
    body: RecommendationGenerateRequest,
    session: AsyncSession = Depends(get_db),
) -> RecommendationOut:
    generator = GeminiRecommendationGenerator(get_settings())
    try:
        recommendation = await generate_recommendation(
            session,
            DEFAULT_ORGANIZATION_ID,
            company_id,
            body.product_id,
            body.contact_id,
            generator,
        )
    except (CompanyNotFoundError, ProductNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GeminiClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    await session.commit()
    return RecommendationOut.model_validate(recommendation)


@router.get("/{company_id}/recommendations", response_model=list[RecommendationOut])
async def list_recommendations_endpoint(
    company_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> list[RecommendationOut]:
    recommendations = await list_recommendations(session, DEFAULT_ORGANIZATION_ID, company_id)
    return [RecommendationOut.model_validate(r) for r in recommendations]
