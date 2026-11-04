import uuid

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UpdatedAtMixin, new_uuid


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
    summary: Mapped[dict] = mapped_column(JSON)
    sources: Mapped[list] = mapped_column(JSON)
    offerings_hash: Mapped[str] = mapped_column(String(64))
    # Which model and prompt wrote the summary; empty on snapshots made before this was kept.
    model_used: Mapped[str | None] = mapped_column(String(50))
    prompt_version: Mapped[str | None] = mapped_column(String(20))
