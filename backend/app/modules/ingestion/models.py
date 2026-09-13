import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid

SOURCE_TYPE_CSV = "csv"
SOURCE_TYPE_MARKET_DISCOVERY = "market_discovery"

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
# Market Discovery only: the free-text input has been parsed into structured criteria and is
# waiting on the user to confirm (or correct) it — scraping never starts before this.
STATUS_AWAITING_CONFIRMATION = "awaiting_confirmation"


class IngestionRun(Base, TimestampMixin):
    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default=STATUS_PENDING)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String)

    # --- Phase 2c: Market Discovery ---
    raw_input: Mapped[str | None] = mapped_column(String)
    parsed_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
