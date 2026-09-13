import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.products.schemas import ProductCreate, ProductList, ProductOut, ProductUpdate
from app.modules.products.service import (
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
        session, DEFAULT_ORGANIZATION_ID, name=body.name, description=body.description
    )
    await session.commit()
    return ProductOut.model_validate(product)


@router.get("", response_model=ProductList)
async def list_products_endpoint(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> ProductList:
    products, total = await list_products(session, DEFAULT_ORGANIZATION_ID, limit, offset)
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


@router.delete("/{product_id}", status_code=204)
async def delete_product_endpoint(
    product_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> None:
    deleted = await delete_product(session, DEFAULT_ORGANIZATION_ID, product_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="product not found")
    await session.commit()
