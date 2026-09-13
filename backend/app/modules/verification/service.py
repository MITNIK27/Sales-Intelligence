import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contacts.models import (
    CHANNEL_TYPE_EMAIL,
    CHANNEL_TYPE_PHONE,
    VERIFICATION_UNVERIFIED,
    Contact,
    ContactChannel,
)
from app.modules.jobs.models import Job
from app.modules.jobs.service import enqueue_job
from app.modules.verification.providers.base import (
    EmailVerificationProvider,
    PhoneVerificationProvider,
)
from app.modules.verification.providers.dns_smtp import DnsSmtpEmailVerificationProvider
from app.modules.verification.providers.format_check import PatternPhoneVerificationProvider

JOB_TYPE_VERIFY_CONTACTS = "verify_contacts"

# One job verifies up to this many channels — each SMTP probe can take several seconds (up to
# the provider's own timeout), so this is bounded to keep a single job run reasonable, not
# because verification itself needs a per-item job like scraping does.
BULK_VERIFY_LIMIT = 200

ProgressCallback = Callable[[int, int], Awaitable[None]]


async def _get_channel_for_org(
    session: AsyncSession, organization_id: uuid.UUID, channel_id: uuid.UUID
) -> ContactChannel | None:
    stmt = (
        select(ContactChannel)
        .join(Contact, Contact.id == ContactChannel.contact_id)
        .where(Contact.organization_id == organization_id, ContactChannel.id == channel_id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _apply_verification(
    channel: ContactChannel,
    email_provider: EmailVerificationProvider,
    phone_provider: PhoneVerificationProvider,
) -> None:
    if channel.channel_type == CHANNEL_TYPE_EMAIL:
        result = await email_provider.verify_email(channel.value)
    elif channel.channel_type == CHANNEL_TYPE_PHONE:
        result = await phone_provider.verify_phone(channel.value)
    else:
        return
    channel.verification_status = result.status


async def verify_channel(
    session: AsyncSession,
    organization_id: uuid.UUID,
    channel_id: uuid.UUID,
    email_provider: EmailVerificationProvider,
    phone_provider: PhoneVerificationProvider,
) -> ContactChannel | None:
    """Single-channel, on-demand verification — called inline (a probe is a few seconds, the
    same "fast enough to not need a job" reasoning as Phase 3's recommendation generation)."""
    channel = await _get_channel_for_org(session, organization_id, channel_id)
    if channel is None:
        return None
    await _apply_verification(channel, email_provider, phone_provider)
    await session.flush()
    return channel


async def start_bulk_verify(session: AsyncSession, organization_id: uuid.UUID) -> Job:
    """Enqueues one background job that verifies every still-`unverified` channel for the org,
    up to `BULK_VERIFY_LIMIT` — mirrors `enrichment/service.py::start_bulk_scrape`'s "act on
    what's outstanding" pattern, but as a single batch job rather than one job per item, since
    a channel probe (unlike a full company scrape) is cheap enough to loop over in one job."""
    return await enqueue_job(session, organization_id, JOB_TYPE_VERIFY_CONTACTS, {})


async def _run_bulk_verify(
    session: AsyncSession,
    job: Job,
    email_provider: EmailVerificationProvider,
    phone_provider: PhoneVerificationProvider,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    stmt = (
        select(ContactChannel)
        .join(Contact, Contact.id == ContactChannel.contact_id)
        .where(
            Contact.organization_id == job.organization_id,
            ContactChannel.verification_status == VERIFICATION_UNVERIFIED,
        )
        .limit(BULK_VERIFY_LIMIT)
    )
    channels = (await session.execute(stmt)).scalars().all()

    results: dict[str, int] = {"valid": 0, "invalid": 0, "unknown": 0}
    total = len(channels) or 1
    for i, channel in enumerate(channels, start=1):
        await _apply_verification(channel, email_provider, phone_provider)
        results[channel.verification_status] = results.get(channel.verification_status, 0) + 1
        if progress_callback:
            await progress_callback(i, total)
    await session.flush()

    return {"channels_verified": len(channels), **results}


async def process_verify_contacts_job(
    session: AsyncSession, job: Job, progress_callback: ProgressCallback | None = None
) -> dict[str, Any]:
    """Handler registered with the job worker — builds the real (network-calling) providers and
    delegates to `_run_bulk_verify`."""
    email_provider = DnsSmtpEmailVerificationProvider()
    phone_provider = PatternPhoneVerificationProvider()
    return await _run_bulk_verify(session, job, email_provider, phone_provider, progress_callback)
