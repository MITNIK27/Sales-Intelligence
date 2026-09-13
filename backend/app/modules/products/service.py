import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.products.models import Product


async def create_product(
    session: AsyncSession, organization_id: uuid.UUID, name: str, description: str | None
) -> Product:
    product = Product(organization_id=organization_id, name=name, description=description)
    session.add(product)
    await session.flush()
    return product


async def list_products(
    session: AsyncSession, organization_id: uuid.UUID, limit: int = 50, offset: int = 0
) -> tuple[list[Product], int]:
    count_stmt = select(func.count()).select_from(Product).where(
        Product.organization_id == organization_id
    )
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = (
        select(Product)
        .where(Product.organization_id == organization_id)
        .order_by(Product.name)
        .limit(limit)
        .offset(offset)
    )
    products = (await session.execute(stmt)).scalars().all()
    return list(products), total


async def get_product(
    session: AsyncSession, organization_id: uuid.UUID, product_id: uuid.UUID
) -> Product | None:
    product = await session.get(Product, product_id)
    if product is None or product.organization_id != organization_id:
        return None
    return product


async def update_product(
    session: AsyncSession,
    organization_id: uuid.UUID,
    product_id: uuid.UUID,
    updates: dict[str, object],
) -> Product | None:
    """`updates` should already be limited to explicitly-provided fields (e.g. via
    `ProductUpdate.model_dump(exclude_unset=True)`) so an omitted field is left untouched
    while an explicit `null` still clears it."""
    product = await get_product(session, organization_id, product_id)
    if product is None:
        return None
    for field, value in updates.items():
        setattr(product, field, value)
    await session.flush()
    return product


async def delete_product(
    session: AsyncSession, organization_id: uuid.UUID, product_id: uuid.UUID
) -> bool:
    product = await get_product(session, organization_id, product_id)
    if product is None:
        return False
    await session.delete(product)
    await session.flush()
    return True
