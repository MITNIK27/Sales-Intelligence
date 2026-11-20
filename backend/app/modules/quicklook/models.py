import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String
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
