import uuid

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class ApiUsage(Base, TimestampMixin):
    """One call (or one retry attempt) to an external service. Append-only operational log.

    The company, run, job and opportunity ids are plain UUID columns with no foreign keys on
    purpose: the log must survive a test-data wipe and must never block deleting what it
    describes. `est_cost_usd` is an estimate from published prices, not a bill."""

    __tablename__ = "api_usage"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column()
    # The person whose action led to the call (Phase 9), a plain id like the others.
    user_id: Mapped[uuid.UUID | None] = mapped_column(index=True)

    provider: Mapped[str] = mapped_column(String(20), index=True)  # gemini|groq|serper|contextdev
    kind: Mapped[str] = mapped_column(String(10))  # llm | search | credits | embedding
    model: Mapped[str | None] = mapped_column(String(100))
    task: Mapped[str] = mapped_column(String(60))  # job type, or "unspecified"
    status: Mapped[str] = mapped_column(String(10))  # ok | error

    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    units: Mapped[int | None] = mapped_column(Integer)  # search queries or context.dev credits
    # Part of tokens_in that the provider served from its cache. Thinking tokens are already
    # inside tokens_out and are shown separately here. Empty when the provider did not say.
    cached_tokens: Mapped[int | None] = mapped_column(Integer)
    thinking_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    est_cost_usd: Mapped[float | None] = mapped_column(Float)
    # Why a failed call failed, shortened and with anything key-like removed (recorder.short_error).
    error: Mapped[str | None] = mapped_column(String(200))
