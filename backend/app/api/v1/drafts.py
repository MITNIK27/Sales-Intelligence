import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.ai_recommendation.gemini_client import GeminiClientError
from app.modules.draft.draft_generator import GeminiDraftGenerator
from app.modules.draft.schemas import DraftGenerateRequest, DraftOut, DraftUpdateRequest
from app.modules.draft.service import (
    CompanyNotFoundError,
    ContactNotFoundError,
    ProductNotFoundError,
    discard_draft,
    generate_draft,
    list_drafts,
    update_draft,
)

# Generation/listing are mounted under the companies prefix for locality, same as
# recommendations/qualification/role-relevance; edit/discard address a draft directly by id.
company_router = APIRouter(prefix="/companies", tags=["drafts"])
draft_router = APIRouter(prefix="/drafts", tags=["drafts"])


@company_router.post("/{company_id}/drafts", response_model=DraftOut, status_code=201)
async def generate_draft_endpoint(
    company_id: uuid.UUID,
    body: DraftGenerateRequest,
    session: AsyncSession = Depends(get_db),
) -> DraftOut:
    generator = GeminiDraftGenerator(get_settings())
    try:
        draft = await generate_draft(
            session,
            DEFAULT_ORGANIZATION_ID,
            company_id,
            body.contact_id,
            body.product_id,
            body.draft_type,
            generator,
        )
    except (CompanyNotFoundError, ContactNotFoundError, ProductNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GeminiClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    await session.commit()
    return DraftOut.model_validate(draft)


@company_router.get("/{company_id}/drafts", response_model=list[DraftOut])
async def list_drafts_endpoint(
    company_id: uuid.UUID,
    contact_id: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> list[DraftOut]:
    drafts = await list_drafts(session, DEFAULT_ORGANIZATION_ID, company_id, contact_id)
    return [DraftOut.model_validate(d) for d in drafts]


@draft_router.patch("/{draft_id}", response_model=DraftOut)
async def update_draft_endpoint(
    draft_id: uuid.UUID, body: DraftUpdateRequest, session: AsyncSession = Depends(get_db)
) -> DraftOut:
    draft = await update_draft(
        session, DEFAULT_ORGANIZATION_ID, draft_id, subject=body.subject, body=body.body
    )
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found")
    await session.commit()
    return DraftOut.model_validate(draft)


@draft_router.post("/{draft_id}/discard", response_model=DraftOut)
async def discard_draft_endpoint(
    draft_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> DraftOut:
    draft = await discard_draft(session, DEFAULT_ORGANIZATION_ID, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found")
    await session.commit()
    return DraftOut.model_validate(draft)
