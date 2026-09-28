import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.contacts.models import Contact, ContactChannel


class ContactHasHistoryError(Exception):
    """Raised by `delete_contact` when the contact has outreach activity or drafts depending on
    it — real, deliberate rep actions (a message was actually sent, a draft was actually
    generated for review) recorded as append-only audit trails elsewhere in this codebase, so
    deleting the contact they reference would silently destroy real history rather than just
    removing a bad lead. The router surfaces this as a 409.

    Deliberately does NOT check RoleRelevanceResult: classification runs automatically for every
    contact at a company the instant "Classify Roles" is clicked, with no human action or review
    involved — treating it as blocking would mean a rep could never clean up a bad lead after
    running the very classification step the app pushes them to run first.

    Checked explicitly in Python rather than relying on the database's own FK enforcement to
    reject the delete — SQLite (used in tests) doesn't enforce foreign keys by default, so an
    implicit DB-level check would silently pass in tests while behaving differently in
    production. Same "explicit gate, not implicit" preference used throughout this codebase."""


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


async def confirm_contact(
    session: AsyncSession, organization_id: uuid.UUID, contact_id: uuid.UUID
) -> Contact | None:
    """Human-in-the-loop approval for a single contact: the only place `Contact.needs_review` is
    ever cleared. Unblocks drafting for this contact (`draft.service.generate_draft` refuses to
    draft to a needs_review contact) after a rep confirms it's a real person, not scraper/search
    noise."""
    stmt = (
        select(Contact)
        .where(Contact.organization_id == organization_id, Contact.id == contact_id)
        .options(selectinload(Contact.channels))
    )
    contact = (await session.execute(stmt)).scalar_one_or_none()
    if contact is None:
        return None
    contact.needs_review = False
    contact.needs_review_reason = None
    await session.flush()
    return contact


async def delete_contact(
    session: AsyncSession, organization_id: uuid.UUID, contact_id: uuid.UUID
) -> bool:
    """A rep's review/removal step for a contact that doesn't belong — e.g. a search- or
    scrape-derived contact that turned out to be a junior employee, or was just wrong. Same
    pattern as `RoleCategory`/`Product` deletion elsewhere in this codebase. Raises
    `ContactHasHistoryError` instead of letting a raw FK violation through when the contact has
    real outreach/draft history — deleting silently would destroy that history. Role-relevance
    classifications don't block deletion — see `ContactHasHistoryError`'s docstring."""
    stmt = select(Contact).where(
        Contact.organization_id == organization_id, Contact.id == contact_id
    )
    contact = (await session.execute(stmt)).scalar_one_or_none()
    if contact is None:
        return False

    # Late imports to avoid a module-load-time cycle (outreach/draft/role_relevance's own
    # service.py modules import from contacts.models, not the reverse) — only their leaf .models
    # modules are needed here.
    from app.modules.draft.models import Draft
    from app.modules.outreach.models import OutreachActivity
    from app.modules.role_relevance.models import RoleRelevanceResult

    for history_model in (OutreachActivity, Draft):
        exists = (
            await session.execute(
                select(history_model.id).where(history_model.contact_id == contact_id).limit(1)
            )
        ).scalar_one_or_none()
        if exists is not None:
            raise ContactHasHistoryError(
                "cannot delete a contact with existing outreach activity or drafts — "
                "those records depend on it"
            )

    # RoleRelevanceResult doesn't block deletion (see ContactHasHistoryError's docstring), but
    # Postgres still enforces its FK to contacts — unlike the checks above, this is a real
    # constraint the delete must satisfy, not an optional guard. Cascade-delete these rows
    # alongside the contact rather than orphaning a re-runnable classification artifact.
    role_relevance_results = (
        await session.execute(
            select(RoleRelevanceResult).where(RoleRelevanceResult.contact_id == contact_id)
        )
    ).scalars().all()
    for result in role_relevance_results:
        await session.delete(result)

    # ContactChannel rows are just the contact's own detail records (email/phone), not an audit
    # trail — deleting them alongside the contact is correct, unlike the history tables above.
    channels = (
        await session.execute(select(ContactChannel).where(ContactChannel.contact_id == contact_id))
    ).scalars().all()
    for channel in channels:
        await session.delete(channel)
    await session.delete(contact)
    await session.flush()
    return True


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
