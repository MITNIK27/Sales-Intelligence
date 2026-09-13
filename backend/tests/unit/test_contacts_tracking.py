from datetime import UTC, datetime, timedelta

from app.modules.companies.service import get_or_create_company
from app.modules.contacts.service import (
    get_or_create_contact,
    list_due_follow_ups,
    update_contact_tracking,
)


async def test_update_contact_tracking_sets_fields(db_session, organization_id) -> None:
    company, _ = await get_or_create_company(db_session, organization_id, "Acme", "acme.com")
    contact, _ = await get_or_create_contact(
        db_session, organization_id, company.id, "Jane Doe", "CEO", "jane@acme.com"
    )

    follow_up = datetime.now(UTC) + timedelta(days=1)
    updated = await update_contact_tracking(
        db_session,
        organization_id,
        contact.id,
        status="follow_up_scheduled",
        next_follow_up_at=follow_up,
        next_follow_up_channel="email",
    )

    assert updated is not None
    assert updated.status == "follow_up_scheduled"
    assert updated.next_follow_up_channel == "email"
    assert updated.next_follow_up_at == follow_up
    # channels must be eager-loaded by update_contact_tracking — a bare (non-eager) lazy
    # relationship raises MissingGreenlet on sync attribute access under AsyncSession.
    assert updated.channels == []


async def test_list_due_follow_ups_only_returns_due_or_overdue(db_session, organization_id) -> None:
    company, _ = await get_or_create_company(db_session, organization_id, "Acme", "acme.com")
    overdue_contact, _ = await get_or_create_contact(
        db_session, organization_id, company.id, "Overdue Guy", "CTO", "overdue@acme.com"
    )
    future_contact, _ = await get_or_create_contact(
        db_session, organization_id, company.id, "Future Guy", "VP", "future@acme.com"
    )
    no_follow_up_contact, _ = await get_or_create_contact(
        db_session, organization_id, company.id, "No Date Guy", "Eng", "nodate@acme.com"
    )

    now = datetime.now(UTC)
    await update_contact_tracking(
        db_session, organization_id, overdue_contact.id, None, now - timedelta(days=1), "email"
    )
    await update_contact_tracking(
        db_session, organization_id, future_contact.id, None, now + timedelta(days=5), "phone"
    )
    await update_contact_tracking(
        db_session, organization_id, no_follow_up_contact.id, None, None, None
    )

    due = await list_due_follow_ups(db_session, organization_id, now)
    due_ids = {c.id for c in due}

    assert overdue_contact.id in due_ids
    assert future_contact.id not in due_ids
    assert no_follow_up_contact.id not in due_ids
