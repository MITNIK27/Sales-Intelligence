import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid
from app.db.types import JsonB

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    job_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(20), default=STATUS_PENDING, index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    # The run this job works on, copied out of `payload` by `enqueue_job` so "the job for this run"
    # is an indexed lookup instead of a scan of every job. Kept when the run is deleted (set null),
    # so job history survives.
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="SET NULL"), index=True
    )
    progress: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    result: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    error: Mapped[str | None] = mapped_column(String)
    # The person whose action queued it (Phase 9); empty for scheduled work and older jobs.
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
