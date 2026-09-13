import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.ai_recommendation.gemini_client import GeminiClientError
from app.modules.role_relevance.role_relevance_generator import GeminiRoleRelevanceGenerator
from app.modules.role_relevance.schemas import (
    RoleCategoryCreate,
    RoleCategoryList,
    RoleCategoryOut,
    RoleCategoryUpdate,
    RoleRelevanceResultOut,
)
from app.modules.role_relevance.service import (
    CompanyNotFoundError,
    NoCategoriesConfiguredError,
    NoContactsError,
    create_category,
    delete_category,
    get_category,
    list_categories,
    list_latest_role_relevance,
    run_role_relevance_check,
    update_category,
)

category_router = APIRouter(prefix="/role-categories", tags=["role-relevance"])

# Mounted under the companies prefix for locality — same reasoning as api/v1/qualification.py's
# company_router.
company_router = APIRouter(prefix="/companies", tags=["role-relevance"])


@category_router.post("", response_model=RoleCategoryOut, status_code=201)
async def create_category_endpoint(
    body: RoleCategoryCreate, session: AsyncSession = Depends(get_db)
) -> RoleCategoryOut:
    category = await create_category(
        session,
        DEFAULT_ORGANIZATION_ID,
        name=body.name,
        description=body.description,
        is_primary_target=body.is_primary_target,
        is_active=body.is_active,
        framing_style=body.framing_style,
    )
    await session.commit()
    return RoleCategoryOut.model_validate(category)


@category_router.get("", response_model=RoleCategoryList)
async def list_categories_endpoint(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> RoleCategoryList:
    categories, total = await list_categories(session, DEFAULT_ORGANIZATION_ID, limit, offset)
    items = [RoleCategoryOut.model_validate(c) for c in categories]
    return RoleCategoryList(items=items, total=total, limit=limit, offset=offset)


@category_router.get("/{category_id}", response_model=RoleCategoryOut)
async def get_category_endpoint(
    category_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> RoleCategoryOut:
    category = await get_category(session, DEFAULT_ORGANIZATION_ID, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="role category not found")
    return RoleCategoryOut.model_validate(category)


@category_router.patch("/{category_id}", response_model=RoleCategoryOut)
async def update_category_endpoint(
    category_id: uuid.UUID, body: RoleCategoryUpdate, session: AsyncSession = Depends(get_db)
) -> RoleCategoryOut:
    category = await update_category(
        session, DEFAULT_ORGANIZATION_ID, category_id, body.model_dump(exclude_unset=True)
    )
    if category is None:
        raise HTTPException(status_code=404, detail="role category not found")
    await session.commit()
    return RoleCategoryOut.model_validate(category)


@category_router.delete("/{category_id}", status_code=204)
async def delete_category_endpoint(
    category_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> None:
    deleted = await delete_category(session, DEFAULT_ORGANIZATION_ID, category_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="role category not found")
    await session.commit()


@company_router.post(
    "/{company_id}/role-relevance", response_model=list[RoleRelevanceResultOut], status_code=201
)
async def run_role_relevance_check_endpoint(
    company_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> list[RoleRelevanceResultOut]:
    generator = GeminiRoleRelevanceGenerator(get_settings())
    try:
        results = await run_role_relevance_check(
            session, DEFAULT_ORGANIZATION_ID, company_id, generator
        )
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (NoContactsError, NoCategoriesConfiguredError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GeminiClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    await session.commit()
    return [RoleRelevanceResultOut.model_validate(r) for r in results]


@company_router.get(
    "/{company_id}/role-relevance", response_model=list[RoleRelevanceResultOut]
)
async def list_role_relevance_endpoint(
    company_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> list[RoleRelevanceResultOut]:
    latest = await list_latest_role_relevance(session, DEFAULT_ORGANIZATION_ID, company_id)
    return [RoleRelevanceResultOut.model_validate(r) for r in latest.values()]
