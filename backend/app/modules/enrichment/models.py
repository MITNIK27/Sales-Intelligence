import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid

ENTITY_TYPE_COMPANY = "company"
ENTITY_TYPE_CONTACT = "contact"


class EnrichmentRecord(Base, TimestampMixin):
    """Raw payload from a given source for a Company or Contact — kept for provenance and to
    allow re-processing when a source/provider changes. Not written to by anything yet; this
    table exists so Phase 2's scraper has it from day one instead of retrofitting provenance
    tracking after scraped data already exists. entity_id is polymorphic (points at either a
    Company or a Contact depending on entity_type), so it deliberately has no FK constraint."""

    __tablename__ = "enrichment_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(20), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    source: Mapped[str] = mapped_column(String(100))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
