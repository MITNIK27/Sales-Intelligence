import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.llm.structured import LLMError, build_structured_llm
from app.modules.offerings.profile import (
    PROFILE_EDITED,
    PROFILE_GENERATED,
    BuyerProfile,
    apply_profile,
    generate_buyer_profile,
)
from app.modules.products.models import SOURCE_MANUAL, STATUS_ACTIVE
from app.modules.products.schemas import ProductCreate, ProductList, ProductOut, ProductUpdate
from app.modules.products.service import (
    ProductInUseError,
    create_product,
    delete_product,
    get_product,
    list_products,
    update_product,
)

router = APIRouter(prefix="/products", tags=["products"])


@router.post("", response_model=ProductOut, status_code=201)
async def create_product_endpoint(
    body: ProductCreate, session: AsyncSession = Depends(get_db)
) -> ProductOut:
    product = await create_product(
        session,
        DEFAULT_ORGANIZATION_ID,
        name=body.name,
        description=body.description,
        kind=body.kind,
    )
    await session.commit()
    return ProductOut.model_validate(product)


@router.get("", response_model=ProductList)
async def list_products_endpoint(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    kind: Literal["service", "product"] | None = Query(None),
    include_archived: bool = Query(False),
    session: AsyncSession = Depends(get_db),
) -> ProductList:
    products, total = await list_products(
        session,
        DEFAULT_ORGANIZATION_ID,
        limit,
        offset,
        kind=kind,
        status=None if include_archived else STATUS_ACTIVE,
    )
    items = [ProductOut.model_validate(p) for p in products]
    return ProductList(items=items, total=total, limit=limit, offset=offset)


@router.get("/{product_id}", response_model=ProductOut)
async def get_product_endpoint(
    product_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> ProductOut:
    product = await get_product(session, DEFAULT_ORGANIZATION_ID, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")
    return ProductOut.model_validate(product)


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product_endpoint(
    product_id: uuid.UUID, body: ProductUpdate, session: AsyncSession = Depends(get_db)
) -> ProductOut:
    product = await update_product(
        session, DEFAULT_ORGANIZATION_ID, product_id, body.model_dump(exclude_unset=True)
    )
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")
    await session.commit()
    return ProductOut.model_validate(product)


@router.put("/{product_id}/buyer-profile", response_model=ProductOut)
async def save_buyer_profile_endpoint(
    product_id: uuid.UUID, body: BuyerProfile, session: AsyncSession = Depends(get_db)
) -> ProductOut:
    """A person's own version of the profile. It is theirs from now on: regenerating is a
    deliberate action, never automatic."""
    product = await get_product(session, DEFAULT_ORGANIZATION_ID, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")
    apply_profile(product, body, PROFILE_EDITED)
    await session.commit()
    return ProductOut.model_validate(product)


@router.post("/{product_id}/buyer-profile/generate", response_model=ProductOut)
async def generate_buyer_profile_endpoint(
    product_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> ProductOut:
    product = await get_product(session, DEFAULT_ORGANIZATION_ID, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")
    try:
        profile = await generate_buyer_profile(build_structured_llm(get_settings()), product)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    apply_profile(product, profile, PROFILE_GENERATED)
    await session.commit()
    return ProductOut.model_validate(product)


@router.delete("/{product_id}", status_code=204)
async def delete_product_endpoint(
    product_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> None:
    existing = await get_product(session, DEFAULT_ORGANIZATION_ID, product_id)
    if existing is not None and existing.source != SOURCE_MANUAL:
        raise HTTPException(
            status_code=409,
            detail="this offering came from the website; archive it instead of deleting it",
        )
    try:
        deleted = await delete_product(session, DEFAULT_ORGANIZATION_ID, product_id)
    except ProductInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="product not found")
    await session.commit()
