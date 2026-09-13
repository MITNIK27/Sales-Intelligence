import uuid
from datetime import UTC, datetime

import pytest

from app.modules.companies.models import Company
from app.modules.contacts.models import (
    TRACKING_STATUS_FOLLOW_UP_SCHEDULED,
    TRACKING_STATUS_NOT_CONTACTED,
    TRACKING_STATUS_RESPONDED,
    Contact,
)
from app.modules.draft.mock import MockDraftGenerator
from app.modules.draft.models import DRAFT_STATUS_SENT, DRAFT_TYPE_FIRST_TOUCH
from app.modules.draft.service import DraftNotFoundError, generate_draft
from app.modules.outreach.models import ACTIVITY_RESPONSE_RECEIVED, ACTIVITY_SENT
from app.modules.outreach.service import (
    ContactNotFoundError,
    list_outreach_activities,
    log_outreach_activity,
)
from app.modules.products.models import Product


async def _make_contact(db_session, organization_id) -> Contact:
    company = Company(
        organization_id=organization_id, name="Acme", domain=f"acme-{uuid.uuid4()}.com"
    )
    db_session.add(company)
    await db_session.flush()
    contact = Contact(organization_id=organization_id, company_id=company.id, full_name="Jane")
    db_session.add(contact)
    await db_session.commit()
    return contact


async def test_log_outreach_activity_raises_for_missing_contact(
    db_session, organization_id
) -> None:
    with pytest.raises(ContactNotFoundError):
        await log_outreach_activity(
            db_session, organization_id, uuid.uuid4(), channel="email", activity_type=ACTIVITY_SENT
        )


async def test_sent_activity_schedules_follow_up_and_sets_channel(
    db_session, organization_id
) -> None:
    contact = await _make_contact(db_session, organization_id)
    assert contact.status == TRACKING_STATUS_NOT_CONTACTED

    activity, updated = await log_outreach_activity(
        db_session, organization_id, contact.id, channel="email", activity_type=ACTIVITY_SENT
    )
    await db_session.commit()

    assert activity.activity_type == ACTIVITY_SENT
    assert updated.status == TRACKING_STATUS_FOLLOW_UP_SCHEDULED
    assert updated.next_follow_up_at is not None
    assert updated.next_follow_up_channel == "email"


async def test_response_received_clears_follow_up_and_marks_responded(
    db_session, organization_id
) -> None:
    contact = await _make_contact(db_session, organization_id)
    await log_outreach_activity(
        db_session, organization_id, contact.id, channel="email", activity_type=ACTIVITY_SENT
    )
    await db_session.commit()

    _, updated = await log_outreach_activity(
        db_session,
        organization_id,
        contact.id,
        channel="email",
        activity_type=ACTIVITY_RESPONSE_RECEIVED,
    )
    await db_session.commit()

    assert updated.status == TRACKING_STATUS_RESPONDED
    assert updated.next_follow_up_at is None
    assert updated.next_follow_up_channel is None


async def test_activity_log_is_append_only(db_session, organization_id) -> None:
    # occurred_at is pinned explicitly (rather than relying on two back-to-back
    # datetime.now(UTC) calls landing in different microseconds) so "newest first" ordering below
    # is deterministic, not a coin flip on timestamp resolution.
    contact = await _make_contact(db_session, organization_id)
    first, _ = await log_outreach_activity(
        db_session, organization_id, contact.id, channel="email", activity_type=ACTIVITY_SENT
    )
    first.occurred_at = datetime(2024, 1, 1, tzinfo=UTC)
    await db_session.commit()
    second, _ = await log_outreach_activity(
        db_session,
        organization_id,
        contact.id,
        channel="linkedin",
        activity_type=ACTIVITY_RESPONSE_RECEIVED,
    )
    second.occurred_at = datetime(2024, 1, 2, tzinfo=UTC)
    await db_session.commit()

    history = await list_outreach_activities(db_session, organization_id, contact.id)

    assert len(history) == 2  # both events preserved, nothing overwritten
    assert history[0].activity_type == ACTIVITY_RESPONSE_RECEIVED  # newest first
    assert history[1].activity_type == ACTIVITY_SENT


async def test_urgent_flag_is_honored_in_scheduling(db_session, organization_id) -> None:
    contact = await _make_contact(db_session, organization_id)

    _, non_urgent = await log_outreach_activity(
        db_session, organization_id, contact.id, channel="email", activity_type=ACTIVITY_SENT,
        urgent=False,
    )
    await db_session.commit()
    non_urgent_slot = non_urgent.next_follow_up_at

    contact2 = await _make_contact(db_session, organization_id)
    _, urgent = await log_outreach_activity(
        db_session, organization_id, contact2.id, channel="email", activity_type=ACTIVITY_SENT,
        urgent=True,
    )
    await db_session.commit()

    # Both are scheduled, and since one may allow a Thursday slot the other rolls past, the urgent
    # slot should never land later than the non-urgent one.
    assert urgent.next_follow_up_at is not None
    assert non_urgent_slot is not None
    assert urgent.next_follow_up_at <= non_urgent_slot


async def test_log_outreach_activity_raises_for_missing_draft(db_session, organization_id) -> None:
    contact = await _make_contact(db_session, organization_id)
    with pytest.raises(DraftNotFoundError):
        await log_outreach_activity(
            db_session,
            organization_id,
            contact.id,
            channel="email",
            activity_type=ACTIVITY_SENT,
            draft_id=uuid.uuid4(),
        )


async def test_logging_with_draft_id_marks_draft_sent_and_defaults_template_variant(
    db_session, organization_id
) -> None:
    contact = await _make_contact(db_session, organization_id)
    product = Product(organization_id=organization_id, name="Widget Pro", description="d")
    db_session.add(product)
    await db_session.commit()

    draft = await generate_draft(
        db_session,
        organization_id,
        contact.company_id,
        contact.id,
        product.id,
        DRAFT_TYPE_FIRST_TOUCH,
        MockDraftGenerator(),
    )
    await db_session.commit()

    activity, _updated = await log_outreach_activity(
        db_session,
        organization_id,
        contact.id,
        channel="email",
        activity_type=ACTIVITY_SENT,
        draft_id=draft.id,
    )
    await db_session.commit()

    assert activity.draft_id == draft.id
    assert activity.template_variant == DRAFT_TYPE_FIRST_TOUCH  # defaulted from the draft
    await db_session.refresh(draft)
    assert draft.status == DRAFT_STATUS_SENT
