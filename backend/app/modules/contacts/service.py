import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.contacts.models import Contact, ContactChannel


def normalize_email(raw: str | None) -> str | None:
    if not raw:
        return None
    return raw.strip().lower() or None


def normalize_name(raw: str | None) -> str | None:
    if not raw:
        return None
    return " ".join(raw.strip().split()).lower() or None


def normalize_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    return raw.strip() or None


async def get_or_create_contact(
    session: AsyncSession,
    organization_id: uuid.UUID,
    company_id: uuid.UUID,
    full_name: str | None,
    role_title: str | None,
    email: str | None,
) -> tuple[Contact, bool]:
    """Get-or-create with dedup by (company_id, normalized email), falling back to
    (company_id, normalized full_name) when no email is given. Returns (contact, created)."""
    normalized_email = normalize_email(email)
    normalized_name = normalize_name(full_name)

    existing: Contact | None = None
    if normalized_email:
        stmt = (
            select(Contact)
            .join(ContactChannel, ContactChannel.contact_id == Contact.id)
            .where(
                Contact.company_id == company_id,
                ContactChannel.channel_type == "email",
                func.lower(ContactChannel.value) == normalized_email,
            )
        )
        existing = (await session.execute(stmt)).scalars().first()
    elif normalized_name:
        stmt = select(Contact).where(
            Contact.company_id == company_id,
            func.lower(Contact.full_name) == normalized_name,
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()

    if existing is not None:
        if not existing.role_title and role_title:
            existing.role_title = role_title
        await session.flush()
        return existing, False

    contact = Contact(
        organization_id=organization_id,
        company_id=company_id,
        full_name=full_name,
        role_title=role_title,
    )
    session.add(contact)
    await session.flush()
    return contact, True


async def upsert_contact_channel(
    session: AsyncSession,
    contact_id: uuid.UUID,
    channel_type: str,
    value: str | None,
    source: str | None = None,
) -> ContactChannel | None:
    if channel_type == "phone":
        normalized_value = normalize_phone(value)
    else:
        normalized_value = normalize_email(value)
    if not normalized_value:
        return None

    stmt = select(ContactChannel).where(
        ContactChannel.contact_id == contact_id,
        ContactChannel.channel_type == channel_type,
        func.lower(ContactChannel.value) == normalized_value.lower(),
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    channel = ContactChannel(
        contact_id=contact_id,
        channel_type=channel_type,
        value=normalized_value,
        source=source,
    )
    session.add(channel)
    await session.flush()
    return channel


async def update_contact_tracking(
    session: AsyncSession,
    organization_id: uuid.UUID,
    contact_id: uuid.UUID,
    status: str | None,
    next_follow_up_at: datetime | None,
    next_follow_up_channel: str | None,
    timezone: str | None = None,
) -> Contact | None:
    stmt = (
        select(Contact)
        .where(Contact.organization_id == organization_id, Contact.id == contact_id)
        .options(selectinload(Contact.channels))
    )
    contact = (await session.execute(stmt)).scalar_one_or_none()
    if contact is None:
        return None
    if status is not None:
        contact.status = status
    contact.next_follow_up_at = next_follow_up_at
    contact.next_follow_up_channel = next_follow_up_channel
    if timezone is not None:
        contact.timezone = timezone
    await session.flush()
    return contact


async def list_due_follow_ups(
    session: AsyncSession, organization_id: uuid.UUID, as_of: datetime
) -> list[Contact]:
    """Contacts with a next-follow-up date at or before `as_of` — the "due today / overdue"
    list that replaces the sales rep's manual daily Excel check."""
    stmt = (
        select(Contact)
        .where(
            Contact.organization_id == organization_id,
            Contact.next_follow_up_at.is_not(None),
            Contact.next_follow_up_at <= as_of,
        )
        .options(selectinload(Contact.company))
        .order_by(Contact.next_follow_up_at)
    )
    return list((await session.execute(stmt)).scalars().all())
