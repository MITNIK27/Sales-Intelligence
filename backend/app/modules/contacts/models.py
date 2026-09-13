import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UpdatedAtMixin, new_uuid

if TYPE_CHECKING:
    from app.modules.companies.models import Company

CHANNEL_TYPE_EMAIL = "email"
CHANNEL_TYPE_PHONE = "phone"

VERIFICATION_UNVERIFIED = "unverified"
VERIFICATION_VALID = "valid"
VERIFICATION_INVALID = "invalid"
VERIFICATION_UNKNOWN = "unknown"

# Outreach-tracking status for a Contact — deliberately minimal (see Phase 1.5 in the plan):
# replaces the sales rep's manual Excel tracker for "have I contacted this person, and when do
# I need to follow up," not a full CRM pipeline/stage system.
TRACKING_STATUS_NOT_CONTACTED = "not_contacted"
TRACKING_STATUS_CONTACTED = "contacted"
TRACKING_STATUS_FOLLOW_UP_SCHEDULED = "follow_up_scheduled"
TRACKING_STATUS_RESPONDED = "responded"
TRACKING_STATUS_NOT_A_FIT = "not_a_fit"
TRACKING_STATUSES = (
    TRACKING_STATUS_NOT_CONTACTED,
    TRACKING_STATUS_CONTACTED,
    TRACKING_STATUS_FOLLOW_UP_SCHEDULED,
    TRACKING_STATUS_RESPONDED,
    TRACKING_STATUS_NOT_A_FIT,
)

# email | linkedin only — Abhas was explicit in the meeting: no cold calling for international
# (EU/US) contacts ("they don't appreciate cold call... he'll block me and blacklist our
# company"). Kept as the single source of truth for "which channel" across both a contact's
# scheduled next touch and an actual logged OutreachActivity (see outreach/models.py).
FOLLOW_UP_CHANNEL_EMAIL = "email"
FOLLOW_UP_CHANNEL_LINKEDIN = "linkedin"
FOLLOW_UP_CHANNELS = (FOLLOW_UP_CHANNEL_EMAIL, FOLLOW_UP_CHANNEL_LINKEDIN)


class Contact(Base, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    role_title: Mapped[str | None] = mapped_column(String(255))
    seniority: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), default=TRACKING_STATUS_NOT_CONTACTED)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    next_follow_up_channel: Mapped[str | None] = mapped_column(String(20))
    # IANA name, e.g. "Europe/Berlin" — nullable, since most contacts won't have one set; Phase C's
    # cadence math (outreach/cadence.py) falls back to settings.default_timezone when absent.
    timezone: Mapped[str | None] = mapped_column(String(64))

    # --- Phase 2a: scraper-sourced contacts with an ambiguous match get flagged, never blocked ---
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_review_reason: Mapped[str | None] = mapped_column(String(255))

    company: Mapped["Company"] = relationship(back_populates="contacts")
    channels: Mapped[list["ContactChannel"]] = relationship(back_populates="contact")


class ContactChannel(Base, TimestampMixin):
    __tablename__ = "contact_channels"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    contact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contacts.id"), index=True)
    channel_type: Mapped[str] = mapped_column(String(20))
    value: Mapped[str] = mapped_column(String(255))
    verification_status: Mapped[str] = mapped_column(String(20), default=VERIFICATION_UNVERIFIED)
    source: Mapped[str | None] = mapped_column(String(100))

    contact: Mapped[Contact] = relationship(back_populates="channels")
