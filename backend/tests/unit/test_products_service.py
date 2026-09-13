import uuid

from app.modules.products.service import (
    create_product,
    delete_product,
    get_product,
    list_products,
    update_product,
)


async def test_create_and_get_product(db_session, organization_id) -> None:
    product = await create_product(
        db_session, organization_id, name="Widget Pro", description="The best widget."
    )
    await db_session.commit()

    fetched = await get_product(db_session, organization_id, product.id)
    assert fetched is not None
    assert fetched.name == "Widget Pro"
    assert fetched.description == "The best widget."


async def test_get_product_returns_none_for_wrong_org(db_session, organization_id) -> None:
    product = await create_product(
        db_session, organization_id, name="Widget Pro", description=None
    )
    await db_session.commit()

    other_org = uuid.uuid4()
    assert await get_product(db_session, other_org, product.id) is None


async def test_get_product_returns_none_when_missing(db_session, organization_id) -> None:
    assert await get_product(db_session, organization_id, uuid.uuid4()) is None


async def test_list_products_scopes_by_organization_and_paginates(
    db_session, organization_id
) -> None:
    other_org = uuid.uuid4()
    from app.modules.auth.models import Organization

    db_session.add(Organization(id=other_org, name="Other Org"))
    await db_session.commit()

    await create_product(db_session, organization_id, name="Alpha", description=None)
    await create_product(db_session, organization_id, name="Beta", description=None)
    await create_product(db_session, other_org, name="Gamma", description=None)
    await db_session.commit()

    products, total = await list_products(db_session, organization_id, limit=1, offset=0)
    assert total == 2
    assert [p.name for p in products] == ["Alpha"]

    products, total = await list_products(db_session, organization_id, limit=1, offset=1)
    assert total == 2
    assert [p.name for p in products] == ["Beta"]


async def test_update_product_only_touches_provided_fields(db_session, organization_id) -> None:
    product = await create_product(
        db_session, organization_id, name="Widget Pro", description="Original description"
    )
    await db_session.commit()

    updated = await update_product(
        db_session, organization_id, product.id, {"name": "Widget Pro Max"}
    )
    assert updated is not None
    assert updated.name == "Widget Pro Max"
    assert updated.description == "Original description"

    cleared = await update_product(
        db_session, organization_id, product.id, {"description": None}
    )
    assert cleared is not None
    assert cleared.description is None


async def test_update_product_returns_none_for_wrong_org_or_missing(
    db_session, organization_id
) -> None:
    product = await create_product(db_session, organization_id, name="Widget", description=None)
    await db_session.commit()

    other_org = uuid.uuid4()
    assert await update_product(db_session, other_org, product.id, {"name": "Hacked"}) is None
    assert await update_product(db_session, organization_id, uuid.uuid4(), {"name": "x"}) is None


async def test_delete_product_removes_row_and_is_org_scoped(db_session, organization_id) -> None:
    product = await create_product(db_session, organization_id, name="Widget", description=None)
    await db_session.commit()

    other_org = uuid.uuid4()
    assert await delete_product(db_session, other_org, product.id) is False

    assert await delete_product(db_session, organization_id, product.id) is True
    assert await get_product(db_session, organization_id, product.id) is None
    assert await delete_product(db_session, organization_id, product.id) is False
