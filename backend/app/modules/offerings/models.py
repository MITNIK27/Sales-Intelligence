import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid

CHANGE_NEW = "new"
CHANGE_CHANGED = "changed"
CHANGE_REMOVED = "removed"

PROPOSAL_PENDING = "pending"
PROPOSAL_APPROVED = "approved"
PROPOSAL_REJECTED = "rejected"

# Where a page came from: the main page sitemap, a named extra page, or a blog post.
LANE_SITE = "site"
LANE_EXTRA = "extra"
LANE_POST = "post"
# A link the company's own website menu names that the catalogue does not cover yet.
LANE_MENU = "menu"

# What the importer concluded about a page, remembered so it is not judged again until it changes.
VERDICT_OFFERING = "offering"
VERDICT_NOT_OFFERING = "not_offering"
VERDICT_FAILED = "failed"


class OfferingProposal(Base, TimestampMixin):
    """Something the website importer found that nobody has approved yet. The importer only ever
    writes these; a live offering is created or changed solely when a person approves one."""

    __tablename__ = "offering_proposals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    # Set for "changed" and "removed"; null for "new".
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id"), index=True)
    change: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=PROPOSAL_PENDING, index=True)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String)
    source_url: Mapped[str] = mapped_column(String(512))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Which lane found it ("site", "extra", "post"); blog-post finds are shown as suggestions.
    origin: Mapped[str] = mapped_column(String(10), default=LANE_SITE, server_default=LANE_SITE)
    # The start of the page the description was written from, so a reviewer can check it on the
    # spot, and any wording the grounding check could not find on the page.
    source_excerpt: Mapped[str | None] = mapped_column(String)
    grounding_flags: Mapped[list[str] | None] = mapped_column(JSON)


class OfferingPage(Base, TimestampMixin):
    """The importer's memory of every page it has considered, offering or not. It lets a later
    sync skip a page whose sitemap `lastmod` has not moved without scraping it or calling a model,
    and lets the coverage view show why any page is, or is not, in the catalogue."""

    __tablename__ = "offering_pages"
    __table_args__ = (UniqueConstraint("organization_id", "url"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    url: Mapped[str] = mapped_column(String(512))
    lane: Mapped[str] = mapped_column(String(10), default=LANE_SITE)
    title: Mapped[str | None] = mapped_column(String(512))
    lastmod: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    verdict: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(String(255))
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when a person asked for this page to be read as an offering despite the verdict.
    force_extract: Mapped[bool] = mapped_column(default=False, server_default="0")
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON)
