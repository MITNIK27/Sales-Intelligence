import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UpdatedAtMixin, new_uuid

# What an offering is. The table keeps its original name (`products`) so existing foreign keys
# from drafts and recommendations stay untouched; "offering" is the user-facing word.
KIND_SERVICE = "service"
KIND_PRODUCT = "product"
KINDS = (KIND_SERVICE, KIND_PRODUCT)

# Where it came from. Imported offerings never overwrite manual ones.
SOURCE_MANUAL = "manual"
SOURCE_WEBSITE = "website"

# Archived offerings are hidden from pickers but kept, because drafts and recommendations
# reference them.
STATUS_ACTIVE = "active"
STATUS_ARCHIVED = "archived"


class Product(Base, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("organization_id", "source_url"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String(20), default=KIND_PRODUCT, server_default=KIND_PRODUCT)
    source: Mapped[str] = mapped_column(
        String(20), default=SOURCE_MANUAL, server_default=SOURCE_MANUAL
    )
    source_url: Mapped[str | None] = mapped_column(String(512))
    source_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(20), default=STATUS_ACTIVE, server_default=STATUS_ACTIVE
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
