import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UpdatedAtMixin, new_uuid

# Enrichment lifecycle for a Company, driven by the Phase 2a scraper. `pending` is set the
# moment a scrape job is enqueued (not when the worker picks it up) so the UI can show
# "in progress" immediately without polling the underlying job.
ENRICHMENT_STATUS_NEVER_ENRICHED = "never_enriched"
ENRICHMENT_STATUS_PENDING = "pending"
ENRICHMENT_STATUS_ENRICHED = "enriched"
ENRICHMENT_STATUS_FAILED = "failed"
ENRICHMENT_STATUSES = (
    ENRICHMENT_STATUS_NEVER_ENRICHED,
    ENRICHMENT_STATUS_PENDING,
    ENRICHMENT_STATUS_ENRICHED,
    ENRICHMENT_STATUS_FAILED,
)


class Company(Base, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "companies"
    __table_args__ = (
        # Backstops the application-level dedup in companies/service.py. Safe to be a NOOP today
        # (the worker processes one job at a time, strictly serially) but becomes load-bearing
        # the moment there's more than one worker or overlapping jobs touching the same domain.
        Index(
            "uq_companies_org_domain",
            "organization_id",
            "domain",
            unique=True,
            postgresql_where=text("domain IS NOT NULL"),
            sqlite_where=text("domain IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    domain: Mapped[str | None] = mapped_column(String(255))
    industry: Mapped[str | None] = mapped_column(String(255))
    employee_count_range: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String)
    source_ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_runs.id")
    )

    # --- Phase 2a: scraper enrichment tracking ---
    enrichment_status: Mapped[str] = mapped_column(
        String(20), default=ENRICHMENT_STATUS_NEVER_ENRICHED
    )
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_review_reason: Mapped[str | None] = mapped_column(String(255))
    last_enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enrichment_error: Mapped[str | None] = mapped_column(String)

    contacts: Mapped[list["Contact"]] = relationship(back_populates="company")


if TYPE_CHECKING:
    from app.modules.contacts.models import Contact
