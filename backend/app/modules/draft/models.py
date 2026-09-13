import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UpdatedAtMixin, new_uuid

DRAFT_TYPE_FIRST_TOUCH = "first_touch"
DRAFT_TYPE_FOLLOW_UP = "follow_up"
DRAFT_TYPES = (DRAFT_TYPE_FIRST_TOUCH, DRAFT_TYPE_FOLLOW_UP)

# LinkedIn drafting is deferred — the meeting's structure/length spec is email-specific.
DRAFT_CHANNEL_EMAIL = "email"
DRAFT_CHANNELS = (DRAFT_CHANNEL_EMAIL,)

DRAFT_STATUS_DRAFT = "draft"
DRAFT_STATUS_SENT = "sent"
DRAFT_STATUS_DISCARDED = "discarded"
DRAFT_STATUSES = (DRAFT_STATUS_DRAFT, DRAFT_STATUS_SENT, DRAFT_STATUS_DISCARDED)


class Draft(Base, TimestampMixin, UpdatedAtMixin):
    """A generated outreach message for one contact, reviewed and edited by a rep before it's
    sent. Unlike QualificationResult/RoleRelevanceResult/OutreachActivity (append-only event
    logs — a judgment or an event that already happened), a Draft is a work-in-progress document:
    mutable until sent, closer in spirit to RoleCategory/Product. Regenerating does not create a
    new row here the way re-judging qualification does — `service.py` always mutates or creates
    fresh depending on the caller's intent, and editing always mutates in place."""

    __tablename__ = "drafts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contacts.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    # Nullable — grounding is a best-effort reuse of an existing Recommendation for this
    # (company, product) pair when one exists; a draft can still be generated without one.
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recommendations.id"))

    draft_type: Mapped[str] = mapped_column(String(20))  # DRAFT_TYPES
    channel: Mapped[str] = mapped_column(String(20))  # DRAFT_CHANNELS
    subject: Mapped[str | None] = mapped_column(String(255))  # email only
    body: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(20), default=DRAFT_STATUS_DRAFT)
    model_used: Mapped[str] = mapped_column(String(50))
