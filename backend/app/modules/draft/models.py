import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UpdatedAtMixin, new_uuid
from app.db.types import JsonB

DRAFT_TYPE_FIRST_TOUCH = "first_touch"
# "follow_up" predates numbered follow-ups and keeps its meaning as the first one, so existing
# rows need no change.
DRAFT_TYPE_FOLLOW_UP = "follow_up"
DRAFT_TYPE_FOLLOW_UP_2 = "follow_up_2"
DRAFT_TYPE_FOLLOW_UP_3 = "follow_up_3"
DRAFT_TYPES = (
    DRAFT_TYPE_FIRST_TOUCH,
    DRAFT_TYPE_FOLLOW_UP,
    DRAFT_TYPE_FOLLOW_UP_2,
    DRAFT_TYPE_FOLLOW_UP_3,
)

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
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    # Nullable — grounding is a best-effort reuse of an existing Recommendation for this
    # (company, product) pair when one exists; a draft can still be generated without one.
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recommendations.id"), index=True
    )

    draft_type: Mapped[str] = mapped_column(String(20))  # DRAFT_TYPES
    channel: Mapped[str] = mapped_column(String(20))  # DRAFT_CHANNELS
    subject: Mapped[str | None] = mapped_column(String(255))  # email only
    body: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(20), default=DRAFT_STATUS_DRAFT)
    model_used: Mapped[str] = mapped_column(String(50))
    prompt_version: Mapped[str | None] = mapped_column(String(20))
    # Figures or past-work claims the finished text makes that the research did not contain
    # (draft/claims.py). Empty when none, and on drafts written before this check existed.
    grounding_flags: Mapped[list[str] | None] = mapped_column(JsonB)
    # The opportunity (business area) this was written for; null for drafts made without one.
    company_opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("company_opportunities.id"), index=True
    )
    # What the rep last asked for when rewriting this draft ("make it shorter"), and the versions
    # that were replaced, newest last: [{instruction, subject, body, grounding_flags, model_used,
    # prompt_version, saved_at}]. Kept so a rewrite can be undone and the history is auditable.
    instruction: Mapped[str | None] = mapped_column(String(600))
    revisions: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonB)

    @property
    def revision_count(self) -> int:
        return len(self.revisions or [])
