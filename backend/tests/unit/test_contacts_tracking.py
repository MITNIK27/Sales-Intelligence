import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.modules.companies.service import get_or_create_company
from app.modules.contacts.models import Contact, ContactChannel
from app.modules.contacts.service import (
    ContactHasHistoryError,
    confirm_contact,
    delete_contact,
    get_or_create_contact,
    list_due_follow_ups,
    update_contact_tracking,
    upsert_contact_channel,
)
from app.modules.outreach.models import ACTIVITY_SENT, CHANNEL_EMAIL, OutreachActivity
from app.modules.role_relevance.models import RoleRelevanceResult


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


async def test_confirm_contact_clears_needs_review_and_reason(
    db_session, organization_id
) -> None:
    company, _ = await get_or_create_company(db_session, organization_id, "Acme", "acme.com")
    contact, _ = await get_or_create_contact(
        db_session, organization_id, company.id, "Jane Doe", "CEO", None
    )
    contact.needs_review = True
    contact.needs_review_reason = "no verified email found"
    await db_session.commit()

    confirmed = await confirm_contact(db_session, organization_id, contact.id)
    await db_session.commit()

    assert confirmed is not None
    assert confirmed.needs_review is False
    assert confirmed.needs_review_reason is None


async def test_confirm_contact_returns_none_for_missing_contact(
    db_session, organization_id
) -> None:
    result = await confirm_contact(db_session, organization_id, uuid.uuid4())
    assert result is None


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


async def test_delete_contact_returns_false_for_missing_contact(
    db_session, organization_id
) -> None:
    deleted = await delete_contact(db_session, organization_id, uuid.uuid4())
    assert deleted is False


async def test_delete_contact_removes_contact_and_its_channels(db_session, organization_id) -> None:
    company, _ = await get_or_create_company(db_session, organization_id, "Acme", "acme.com")
    contact, _ = await get_or_create_contact(
        db_session, organization_id, company.id, "Jane Doe", "CEO", "jane@acme.com"
    )
    await upsert_contact_channel(db_session, contact.id, "email", "jane@acme.com")
    await db_session.commit()

    deleted = await delete_contact(db_session, organization_id, contact.id)
    await db_session.commit()

    assert deleted is True
    assert (
        await db_session.execute(select(Contact).where(Contact.id == contact.id))
    ).scalar_one_or_none() is None
    assert (
        await db_session.execute(
            select(ContactChannel).where(ContactChannel.contact_id == contact.id)
        )
    ).scalar_one_or_none() is None


async def test_delete_contact_succeeds_with_only_role_relevance_history(
    db_session, organization_id
) -> None:
    company, _ = await get_or_create_company(db_session, organization_id, "Acme", "acme.com")
    contact, _ = await get_or_create_contact(
        db_session, organization_id, company.id, "Jane Doe", "CEO", "jane@acme.com"
    )
    db_session.add(
        RoleRelevanceResult(
            organization_id=organization_id,
            company_id=company.id,
            contact_id=contact.id,
            matched_category_id=None,
            matched_category_name=None,
            is_primary_target=False,
            matched_category_framing_style=None,
            priority="not_relevant",
            reasoning="no configured category fits this contact",
            model_used="mock",
        )
    )
    await db_session.commit()

    deleted = await delete_contact(db_session, organization_id, contact.id)
    await db_session.commit()

    assert deleted is True
    assert (
        await db_session.execute(select(Contact).where(Contact.id == contact.id))
    ).scalar_one_or_none() is None
    # Cascade-deleted alongside the contact — SQLite (this test's DB) doesn't enforce the FK
    # either way, but Postgres does, so this row must actually be gone, not just unreferenced.
    assert (
        await db_session.execute(
            select(RoleRelevanceResult).where(RoleRelevanceResult.contact_id == contact.id)
        )
    ).scalar_one_or_none() is None


async def test_delete_contact_refuses_when_outreach_history_exists(
    db_session, organization_id
) -> None:
    company, _ = await get_or_create_company(db_session, organization_id, "Acme", "acme.com")
    contact, _ = await get_or_create_contact(
        db_session, organization_id, company.id, "Jane Doe", "CEO", "jane@acme.com"
    )
    db_session.add(
        OutreachActivity(
            organization_id=organization_id,
            contact_id=contact.id,
            channel=CHANNEL_EMAIL,
            activity_type=ACTIVITY_SENT,
        )
    )
    await db_session.commit()

    with pytest.raises(ContactHasHistoryError):
        await delete_contact(db_session, organization_id, contact.id)
