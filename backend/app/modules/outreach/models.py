import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid

CHANNEL_EMAIL = "email"
CHANNEL_LINKEDIN = "linkedin"
OUTREACH_CHANNELS = (CHANNEL_EMAIL, CHANNEL_LINKEDIN)

ACTIVITY_SENT = "sent"
ACTIVITY_RESPONSE_RECEIVED = "response_received"
ACTIVITY_TYPES = (ACTIVITY_SENT, ACTIVITY_RESPONSE_RECEIVED)


class OutreachActivity(Base, TimestampMixin):
    """A record of one outbound send or inbound response for a contact (Phase C). Append-only,
    same spirit as `QualificationResult`/`RoleRelevanceResult`: logging a new touch never
    overwrites a prior one — the tracker's derived state (`Contact.status`/`next_follow_up_at`)
    is recomputed from this event, not stored as an edit to it."""

    __tablename__ = "outreach_activities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contacts.id"), index=True)
    # Nullable — set only when this activity was logged from an approved Phase B Draft (vs. a
    # rep manually logging a send/response with free-typed channel/notes, which stays None).
    draft_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("drafts.id"))

    channel: Mapped[str] = mapped_column(String(20))  # OUTREACH_CHANNELS
    activity_type: Mapped[str] = mapped_column(String(30))  # ACTIVITY_TYPES
    # Free-text label, e.g. "cold-open-v2" — captured now so A/B data isn't lost once Phase B
    # (draft generation) exists and can start assigning real variant names; no aggregate
    # reporting on this yet, deliberately deferred until there's real variant data to report on.
    template_variant: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(String(500))

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
