import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UpdatedAtMixin, new_uuid
from app.db.types import JsonB


class CompanySnapshot(Base, TimestampMixin, UpdatedAtMixin):
    """The short answer a Quick Check gave about a company, kept so a repeat look-up is instant and
    free. It is not a company: nothing appears in the companies list until a person saves it. One
    snapshot per website; a refresh replaces it. `offerings_hash` fingerprints the offerings it was
    judged against, so changing the offerings makes it stale."""

    __tablename__ = "company_snapshots"
    __table_args__ = (Index("uq_snapshots_org_domain", "organization_id", "domain", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    domain: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    summary: Mapped[dict[str, Any]] = mapped_column(JsonB)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JsonB)
    offerings_hash: Mapped[str] = mapped_column(String(64))
    # Which model and prompt wrote the summary; empty on snapshots made before this was kept.
    model_used: Mapped[str | None] = mapped_column(String(50))
    prompt_version: Mapped[str | None] = mapped_column(String(20))


class QuickCheckEntry(Base, TimestampMixin):
    """One Quick Check a person ran, with a copy of the answer they got. The snapshot keeps only
    the latest answer per website (a refresh or a new focus replaces it); this keeps each check, so
    a person can see what they looked up and what it said at the time. Each person sees their own;
    rows without `user_id` were made before history was kept."""

    __tablename__ = "quick_check_history"
    __table_args__ = (
        Index(
            "ix_quick_check_history_org_user_created", "organization_id", "user_id", "created_at"
        ),
        Index("ix_quick_check_history_org_domain", "organization_id", "domain"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # The company's current answer; history goes with it when it is removed.
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("company_snapshots.id", ondelete="CASCADE"), index=True
    )
    domain: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    # What the person typed, when they typed a name rather than choosing from a list.
    asked: Mapped[str | None] = mapped_column(String(255))
    focus: Mapped[str | None] = mapped_column(String(200))
    # The criteria they asked about (their wording); the verdicts are in `summary`.
    criteria: Mapped[list[str]] = mapped_column(JsonB, default=list)
    call: Mapped[str] = mapped_column(String(20))
    summary: Mapped[dict[str, Any]] = mapped_column(JsonB)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JsonB)
    # A saved answer was shown (no new research), or the person asked for a fresh one.
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    refreshed: Mapped[bool] = mapped_column(Boolean, default=False)
    model_used: Mapped[str | None] = mapped_column(String(50))
    prompt_version: Mapped[str | None] = mapped_column(String(20))
