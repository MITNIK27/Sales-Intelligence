import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.contacts.models import (
    TRACKING_STATUS_FOLLOW_UP_SCHEDULED,
    TRACKING_STATUS_RESPONDED,
    Contact,
)
from app.modules.draft.service import DraftNotFoundError, mark_draft_sent
from app.modules.outreach.cadence import next_send_window_slot
from app.modules.outreach.models import ACTIVITY_RESPONSE_RECEIVED, ACTIVITY_SENT, OutreachActivity


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
) -> tuple[OutreachActivity, Contact]:
    """Logs one outreach event and derives the contact's tracker state from it — the "auto-update
    after a send/response" replacement for manually retyping `next_follow_up_at` every time.
    Manual override stays available via the existing `PATCH /contacts/{id}/tracking` for anything
    this doesn't cover (marking not_a_fit, hand-adjusting a date), same layering the append-only
    history + manual-override decision already used for Phase A3.

    When `draft_id` is given (a Phase B draft was approved and sent), `template_variant` defaults
    to that draft's type when the caller didn't supply one explicitly, and the draft is marked
    sent after the activity is created."""
    stmt = (
        select(Contact)
        .where(Contact.organization_id == organization_id, Contact.id == contact_id)
        .options(selectinload(Contact.channels))
    )
    contact = (await session.execute(stmt)).scalar_one_or_none()
    if contact is None:
        raise ContactNotFoundError(f"contact {contact_id} not found")

    if draft_id is not None:
        draft = await mark_draft_sent(session, organization_id, draft_id)
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
    )
    session.add(activity)
    await session.flush()

    if activity_type == ACTIVITY_SENT:
        contact.status = TRACKING_STATUS_FOLLOW_UP_SCHEDULED
        contact.next_follow_up_at = next_send_window_slot(
            activity.occurred_at, contact.timezone, urgent=urgent
        )
        contact.next_follow_up_channel = channel
    elif activity_type == ACTIVITY_RESPONSE_RECEIVED:
        contact.status = TRACKING_STATUS_RESPONDED
        contact.next_follow_up_at = None
        contact.next_follow_up_channel = None

    await session.flush()
    return activity, contact


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
