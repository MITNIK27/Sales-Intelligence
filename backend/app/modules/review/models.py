import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class ReviewDecision(Base, TimestampMixin):
    """What a person decided about something the system flagged for review (docs/ai-governance.md,
    G4). Append-only. These are the labels a later quality check or judge is measured against: the
    system said "needs a person to look", and this is what the person concluded.

    The ids are plain UUID columns with no foreign keys on purpose, like `api_usage`: the subject
    may be deleted (that is one of the decisions) and the log must outlive it. `snapshot` keeps
    what the person was shown, because the row it came from may be gone. It never holds names or
    email addresses."""

    __tablename__ = "review_decisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(index=True)
    subject_type: Mapped[str] = mapped_column(String(20))  # company | contact
    subject_id: Mapped[uuid.UUID] = mapped_column(index=True)
    # The company the subject belongs to (the subject itself for a company).
    company_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    decision: Mapped[str] = mapped_column(String(20))  # confirmed | deleted
    # Whether the system had flagged it. A deletion of something never flagged is still recorded,
    # but is a different signal from rejecting a flagged one.
    was_flagged: Mapped[bool] = mapped_column(Boolean)
    flag_reason: Mapped[str | None] = mapped_column(String(255))
    # For not_a_fit (and the restore that undoes it): the reason picked from a short fixed list,
    # and an optional free-text note. The note is typed by a person and may mention people, so
    # it only goes to a model through a chain cleared for personal data.
    reason_code: Mapped[str | None] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(String(500))
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
