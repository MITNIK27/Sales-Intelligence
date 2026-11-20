import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Predictable names for constraints and indexes created from now on (Phase 8a), so a migration can
# name exactly what it creates or drops. Constraints made before this keep their existing names.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Shared declarative base. Import all module models here so Alembic
    autogenerate can discover them via Base.metadata."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


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
