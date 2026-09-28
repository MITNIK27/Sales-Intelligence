import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.contacts.schemas import (
    ContactChannelOut,
    ContactOut,
    ContactTrackingUpdate,
    FollowUpItem,
)
from app.modules.contacts.service import (
    ContactHasHistoryError,
    confirm_contact,
    delete_contact,
    list_due_follow_ups,
    update_contact_tracking,
)
from app.modules.enrichment.schemas import ScrapeJobStarted
from app.modules.verification.providers.dns_smtp import DnsSmtpEmailVerificationProvider
from app.modules.verification.providers.format_check import PatternPhoneVerificationProvider
from app.modules.verification.service import start_bulk_verify, verify_channel

router = APIRouter(prefix="/contacts", tags=["contacts"])

_email_provider = DnsSmtpEmailVerificationProvider()
_phone_provider = PatternPhoneVerificationProvider()


@router.get("/follow-ups", response_model=list[FollowUpItem])
async def list_follow_ups_endpoint(
    session: AsyncSession = Depends(get_db),
) -> list[FollowUpItem]:
    contacts = await list_due_follow_ups(session, DEFAULT_ORGANIZATION_ID, datetime.now(UTC))
    return [FollowUpItem.model_validate(c) for c in contacts]


@router.patch("/{contact_id}/tracking", response_model=ContactOut)
async def update_contact_tracking_endpoint(
    contact_id: uuid.UUID,
    update: ContactTrackingUpdate,
    session: AsyncSession = Depends(get_db),
) -> ContactOut:
    contact = await update_contact_tracking(
        session,
        DEFAULT_ORGANIZATION_ID,
        contact_id,
        status=update.status,
        next_follow_up_at=update.next_follow_up_at,
        next_follow_up_channel=update.next_follow_up_channel,
        timezone=update.timezone,
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="contact not found")
    await session.commit()
    return ContactOut.model_validate(contact)


@router.post("/{contact_id}/confirm", response_model=ContactOut)
async def confirm_contact_endpoint(
    contact_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> ContactOut:
    """A rep vouching for a contact the pipeline flagged `needs_review` (no verified email,
    search/scrape noise) — the only way that flag is cleared, unblocking drafting for this
    contact specifically (`draft.service.generate_draft` refuses to draft to a needs_review
    contact)."""
    contact = await confirm_contact(session, DEFAULT_ORGANIZATION_ID, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="contact not found")
    await session.commit()
    return ContactOut.model_validate(contact)


@router.delete("/{contact_id}", status_code=204)
async def delete_contact_endpoint(
    contact_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> None:
    try:
        deleted = await delete_contact(session, DEFAULT_ORGANIZATION_ID, contact_id)
    except ContactHasHistoryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="contact not found")
    await session.commit()


@router.post(
    "/{contact_id}/channels/{channel_id}/verify",
    response_model=ContactChannelOut,
)
async def verify_contact_channel_endpoint(
    contact_id: uuid.UUID,
    channel_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
) -> ContactChannelOut:
    channel = await verify_channel(
        session, DEFAULT_ORGANIZATION_ID, channel_id, _email_provider, _phone_provider
    )
    if channel is None or channel.contact_id != contact_id:
        raise HTTPException(status_code=404, detail="contact channel not found")
    await session.commit()
    return ContactChannelOut.model_validate(channel)


@router.post("/verify-all", response_model=ScrapeJobStarted, status_code=202)
async def verify_all_contacts_endpoint(
    session: AsyncSession = Depends(get_db),
) -> ScrapeJobStarted:
    job = await start_bulk_verify(session, DEFAULT_ORGANIZATION_ID)
    await session.commit()
    return ScrapeJobStarted(job_id=job.id)
