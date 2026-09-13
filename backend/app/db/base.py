import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base. Import all module models here so Alembic
    autogenerate can discover them via Base.metadata."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class UpdatedAtMixin:
    """For entities that get mutated after creation (e.g. via dedup-and-update on
    re-ingestion). Must specify DateTime(timezone=True) explicitly — the tz-aware Python
    default returned by datetime.now(UTC) will not round-trip through a naive column."""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()
