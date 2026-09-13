import uuid

from app.modules.role_relevance.service import (
    create_category,
    delete_category,
    get_category,
    list_active_categories,
    list_categories,
    update_category,
)


async def test_create_and_get_category(db_session, organization_id) -> None:
    category = await create_category(
        db_session,
        organization_id,
        name="Vendor / IT Procurement",
        description="Evaluates and selects technology vendors.",
        is_primary_target=True,
        is_active=True,
    )
    await db_session.commit()

    fetched = await get_category(db_session, organization_id, category.id)
    assert fetched is not None
    assert fetched.name == "Vendor / IT Procurement"
    assert fetched.is_primary_target is True
    assert fetched.is_active is True


async def test_create_category_defaults(db_session, organization_id) -> None:
    category = await create_category(
        db_session, organization_id, name="Product Management", description=None,
        is_primary_target=False, is_active=True,
    )
    await db_session.commit()

    assert category.is_primary_target is False
    assert category.description is None


async def test_get_category_returns_none_for_wrong_org(db_session, organization_id) -> None:
    category = await create_category(
        db_session, organization_id, name="Widget", description=None,
        is_primary_target=False, is_active=True,
    )
    await db_session.commit()

    other_org = uuid.uuid4()
    assert await get_category(db_session, other_org, category.id) is None


async def test_list_categories_scopes_by_organization_and_paginates(
    db_session, organization_id
) -> None:
    other_org = uuid.uuid4()
    from app.modules.auth.models import Organization

    db_session.add(Organization(id=other_org, name="Other Org"))
    await db_session.commit()

    await create_category(
        db_session, organization_id, name="Alpha", description=None,
        is_primary_target=False, is_active=True,
    )
    await create_category(
        db_session, organization_id, name="Beta", description=None,
        is_primary_target=False, is_active=True,
    )
    await create_category(
        db_session, other_org, name="Gamma", description=None,
        is_primary_target=False, is_active=True,
    )
    await db_session.commit()

    categories, total = await list_categories(db_session, organization_id, limit=1, offset=0)
    assert total == 2
    assert [c.name for c in categories] == ["Alpha"]


async def test_update_category_only_touches_provided_fields(db_session, organization_id) -> None:
    category = await create_category(
        db_session, organization_id, name="Widget", description="Original description",
        is_primary_target=False, is_active=True,
    )
    await db_session.commit()

    updated = await update_category(
        db_session, organization_id, category.id, {"is_primary_target": True}
    )
    assert updated is not None
    assert updated.is_primary_target is True
    assert updated.description == "Original description"


async def test_delete_category_removes_row_and_is_org_scoped(db_session, organization_id) -> None:
    category = await create_category(
        db_session, organization_id, name="Widget", description=None,
        is_primary_target=False, is_active=True,
    )
    await db_session.commit()

    other_org = uuid.uuid4()
    assert await delete_category(db_session, other_org, category.id) is False
    assert await delete_category(db_session, organization_id, category.id) is True
    assert await get_category(db_session, organization_id, category.id) is None


async def test_list_active_categories_excludes_inactive(db_session, organization_id) -> None:
    await create_category(
        db_session, organization_id, name="Active", description=None,
        is_primary_target=True, is_active=True,
    )
    await create_category(
        db_session, organization_id, name="Inactive", description=None,
        is_primary_target=True, is_active=False,
    )
    await db_session.commit()

    active = await list_active_categories(db_session, organization_id)
    assert [c.name for c in active] == ["Active"]
