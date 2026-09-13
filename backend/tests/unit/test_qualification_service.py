import uuid

from app.modules.qualification.service import (
    create_criterion,
    delete_criterion,
    get_criterion,
    list_criteria,
    update_criterion,
)


async def test_create_and_get_criterion(db_session, organization_id) -> None:
    criterion = await create_criterion(
        db_session,
        organization_id,
        name="Minimum IT spend",
        description="Company should show evidence of significant annual IT spend.",
        is_disqualifying=True,
        is_active=True,
    )
    await db_session.commit()

    fetched = await get_criterion(db_session, organization_id, criterion.id)
    assert fetched is not None
    assert fetched.name == "Minimum IT spend"
    assert fetched.description == "Company should show evidence of significant annual IT spend."
    assert fetched.is_disqualifying is True
    assert fetched.is_active is True


async def test_create_criterion_defaults(db_session, organization_id) -> None:
    criterion = await create_criterion(
        db_session,
        organization_id,
        name="Digital transformation maturity",
        description=None,
        is_disqualifying=False,
        is_active=True,
    )
    await db_session.commit()

    assert criterion.is_disqualifying is False
    assert criterion.is_active is True
    assert criterion.description is None


async def test_get_criterion_returns_none_for_wrong_org(db_session, organization_id) -> None:
    criterion = await create_criterion(
        db_session, organization_id, name="Minimum IT spend", description=None,
        is_disqualifying=False, is_active=True,
    )
    await db_session.commit()

    other_org = uuid.uuid4()
    assert await get_criterion(db_session, other_org, criterion.id) is None


async def test_get_criterion_returns_none_when_missing(db_session, organization_id) -> None:
    assert await get_criterion(db_session, organization_id, uuid.uuid4()) is None


async def test_list_criteria_scopes_by_organization_and_paginates(
    db_session, organization_id
) -> None:
    other_org = uuid.uuid4()
    from app.modules.auth.models import Organization

    db_session.add(Organization(id=other_org, name="Other Org"))
    await db_session.commit()

    await create_criterion(
        db_session, organization_id, name="Alpha", description=None,
        is_disqualifying=False, is_active=True,
    )
    await create_criterion(
        db_session, organization_id, name="Beta", description=None,
        is_disqualifying=False, is_active=True,
    )
    await create_criterion(
        db_session, other_org, name="Gamma", description=None,
        is_disqualifying=False, is_active=True,
    )
    await db_session.commit()

    criteria, total = await list_criteria(db_session, organization_id, limit=1, offset=0)
    assert total == 2
    assert [c.name for c in criteria] == ["Alpha"]

    criteria, total = await list_criteria(db_session, organization_id, limit=1, offset=1)
    assert total == 2
    assert [c.name for c in criteria] == ["Beta"]


async def test_update_criterion_only_touches_provided_fields(
    db_session, organization_id
) -> None:
    criterion = await create_criterion(
        db_session, organization_id, name="Minimum IT spend", description="Original description",
        is_disqualifying=False, is_active=True,
    )
    await db_session.commit()

    updated = await update_criterion(
        db_session, organization_id, criterion.id, {"is_disqualifying": True}
    )
    assert updated is not None
    assert updated.is_disqualifying is True
    assert updated.name == "Minimum IT spend"
    assert updated.description == "Original description"

    cleared = await update_criterion(
        db_session, organization_id, criterion.id, {"description": None}
    )
    assert cleared is not None
    assert cleared.description is None


async def test_update_criterion_returns_none_for_wrong_org_or_missing(
    db_session, organization_id
) -> None:
    criterion = await create_criterion(
        db_session, organization_id, name="Widget", description=None,
        is_disqualifying=False, is_active=True,
    )
    await db_session.commit()

    other_org = uuid.uuid4()
    assert (
        await update_criterion(db_session, other_org, criterion.id, {"name": "Hacked"}) is None
    )
    assert (
        await update_criterion(db_session, organization_id, uuid.uuid4(), {"name": "x"}) is None
    )


async def test_delete_criterion_removes_row_and_is_org_scoped(
    db_session, organization_id
) -> None:
    criterion = await create_criterion(
        db_session, organization_id, name="Widget", description=None,
        is_disqualifying=False, is_active=True,
    )
    await db_session.commit()

    other_org = uuid.uuid4()
    assert await delete_criterion(db_session, other_org, criterion.id) is False

    assert await delete_criterion(db_session, organization_id, criterion.id) is True
    assert await get_criterion(db_session, organization_id, criterion.id) is None
    assert await delete_criterion(db_session, organization_id, criterion.id) is False
