import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.contacts.models import (
    TRACKING_STATUS_FOLLOW_UP_SCHEDULED,
    TRACKING_STATUS_RESPONDED,
    Contact,
)
from app.modules.draft.service import DraftNotFoundError, mark_draft_sent
from app.modules.outreach.cadence import next_send_window_slot
from app.modules.outreach.models import (
    ACTIVITY_RESPONSE_RECEIVED,
    ACTIVITY_SENT,
    OUTCOME_NOT_NOW,
    OUTCOME_OUT_OF_OFFICE,
    OutreachActivity,
)

# Business days until the next follow-up when a reply asks to wait and the rep gave no number.
DEFAULT_NOT_NOW_BUSINESS_DAYS = 20
DEFAULT_OUT_OF_OFFICE_BUSINESS_DAYS = 5


class ContactNotFoundError(Exception):
    pass


async def log_outreach_activity(
    session: AsyncSession,
    organization_id: uuid.UUID,
    contact_id: uuid.UUID,
    channel: str,
    activity_type: str,
    template_variant: str | None = None,
    notes: str | None = None,
    urgent: bool = False,
    draft_id: uuid.UUID | None = None,
    occurred_at: datetime | None = None,
    outcome: str | None = None,
    follow_up_in_business_days: int | None = None,
) -> tuple[OutreachActivity, Contact]:
    """Logs one outreach event and derives the contact's tracker state from it — the "auto-update
    after a send/response" replacement for manually retyping `next_follow_up_at` every time.
    Manual override stays available via the existing `PATCH /contacts/{id}/tracking` for anything
    this doesn't cover (marking not_a_fit, hand-adjusting a date), same layering the append-only
    history + manual-override decision already used for Phase A3.

    When `draft_id` is given (a Phase B draft was approved and sent), `template_variant` defaults
    to that draft's type when the caller didn't supply one explicitly, and the draft is marked
    sent after the activity is created. The draft must be this contact's and still a draft, so one
    message cannot be logged twice.

    `occurred_at` is when it really happened (omitted means now). The contact's follow-up is only
    moved when this is the newest thing logged for them, so logging an older message later does
    not undo a newer state. A reply's `outcome` decides what follows: interested, referred and not
    interested end the follow-ups; not now and out of office schedule one further out."""
    stmt = (
        select(Contact)
        .where(Contact.organization_id == organization_id, Contact.id == contact_id)
        .options(selectinload(Contact.channels))
    )
    contact = (await session.execute(stmt)).scalar_one_or_none()
    if contact is None:
        raise ContactNotFoundError(f"contact {contact_id} not found")

    if draft_id is not None:
        draft = await mark_draft_sent(session, organization_id, draft_id, contact_id)
        if draft is None:
            raise DraftNotFoundError(f"draft {draft_id} not found")
        if template_variant is None:
            template_variant = draft.draft_type

    activity = OutreachActivity(
        organization_id=organization_id,
        contact_id=contact_id,
        channel=channel,
        activity_type=activity_type,
        template_variant=template_variant,
        notes=notes,
        draft_id=draft_id,
        outcome=outcome,
    )
    if occurred_at is not None:
        activity.occurred_at = occurred_at
    else:
        activity.occurred_at = datetime.now(UTC)
    newest_before = (
        await session.execute(
            select(func.max(OutreachActivity.occurred_at)).where(
                OutreachActivity.organization_id == organization_id,
                OutreachActivity.contact_id == contact_id,
            )
        )
    ).scalar_one_or_none()
    is_newest = newest_before is None or _aware(activity.occurred_at) >= _aware(newest_before)
    session.add(activity)
    await session.flush()

    if not is_newest:
        return activity, contact
    if activity_type == ACTIVITY_SENT:
        contact.status = TRACKING_STATUS_FOLLOW_UP_SCHEDULED
        contact.next_follow_up_at = next_send_window_slot(
            activity.occurred_at, contact.timezone, urgent=urgent
        )
        contact.next_follow_up_channel = channel
    elif activity_type == ACTIVITY_RESPONSE_RECEIVED:
        wait = _wait_for(outcome, follow_up_in_business_days)
        if wait is not None:
            # They asked to wait (or are away): still being followed, just later.
            contact.status = TRACKING_STATUS_FOLLOW_UP_SCHEDULED
            contact.next_follow_up_at = next_send_window_slot(
                activity.occurred_at, contact.timezone, gap_business_days=wait
            )
            contact.next_follow_up_channel = channel
        else:
            contact.status = TRACKING_STATUS_RESPONDED
            contact.next_follow_up_at = None
            contact.next_follow_up_channel = None

    await session.flush()
    return activity, contact


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _wait_for(outcome: str | None, requested: int | None) -> int | None:
    """Business days until the next follow-up for a reply that asks to wait; None when the reply
    ends the follow-ups."""
    if outcome == OUTCOME_NOT_NOW:
        return requested or DEFAULT_NOT_NOW_BUSINESS_DAYS
    if outcome == OUTCOME_OUT_OF_OFFICE:
        return requested or DEFAULT_OUT_OF_OFFICE_BUSINESS_DAYS
    return None


async def snooze_follow_up(
    session: AsyncSession,
    organization_id: uuid.UUID,
    contact_id: uuid.UUID,
    business_days: int,
    urgent: bool = False,
) -> Contact:
    """Move a contact's next follow-up `business_days` business days from now, landing in the same
    send window as any other follow-up (Monday to Wednesday, 11:00 local). The channel is kept."""
    stmt = (
        select(Contact)
        .where(Contact.organization_id == organization_id, Contact.id == contact_id)
        .options(selectinload(Contact.channels))
    )
    contact = (await session.execute(stmt)).scalar_one_or_none()
    if contact is None:
        raise ContactNotFoundError(f"contact {contact_id} not found")
    contact.next_follow_up_at = next_send_window_slot(
        datetime.now(UTC), contact.timezone, urgent=urgent, gap_business_days=business_days
    )
    if contact.next_follow_up_channel is None:
        contact.next_follow_up_channel = "email"
    contact.status = TRACKING_STATUS_FOLLOW_UP_SCHEDULED
    await session.flush()
    return contact


async def sent_summaries(
    session: AsyncSession, organization_id: uuid.UUID, contact_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, datetime | None]]:
    """For each contact, how many messages were logged as sent and when the last one went out."""
    if not contact_ids:
        return {}
    rows = await session.execute(
        select(
            OutreachActivity.contact_id,
            func.count(OutreachActivity.id),
            func.max(OutreachActivity.occurred_at),
        )
        .where(
            OutreachActivity.organization_id == organization_id,
            OutreachActivity.contact_id.in_(contact_ids),
            OutreachActivity.activity_type == ACTIVITY_SENT,
        )
        .group_by(OutreachActivity.contact_id)
    )
    return {cid: (count, _aware(last) if last else None) for cid, count, last in rows.all()}


async def list_outreach_activities(
    session: AsyncSession, organization_id: uuid.UUID, contact_id: uuid.UUID
) -> list[OutreachActivity]:
    """Append-only history for one contact, newest first — the audit trail of what was actually
    sent/heard back on and when. A small per-contact list, so a plain ordered query is enough; no
    window-function "latest per X" needed here (that's only worth it for a paginated multi-row
    list like the companies-list qualification column)."""
    stmt = (
        select(OutreachActivity)
        .where(
            OutreachActivity.organization_id == organization_id,
            OutreachActivity.contact_id == contact_id,
        )
        .order_by(OutreachActivity.occurred_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())
