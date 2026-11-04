import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
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
    # What the rep chose when confirming the run (offerings to pitch, target roles, extra
    # requirements). It used to live only in the job payload, which is wiped with the test data and
    # can only be found by scanning jobs, so the company page could never know what a run was for.
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class IngestionRunCompany(Base, TimestampMixin):
    """A company a run is about. One company can belong to many runs, so this is a link table
    rather than a column on the company. See `membership.py` for how it is read and written."""

    __tablename__ = "ingestion_run_companies"
    __table_args__ = (
        UniqueConstraint("run_id", "company_id", name="uq_ingestion_run_companies_run_company"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion_runs.id"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    relation: Mapped[str] = mapped_column(String(10))  # created | reused | matched
