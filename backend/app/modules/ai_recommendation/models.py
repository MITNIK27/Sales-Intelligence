import uuid

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid


class Recommendation(Base, TimestampMixin):
    """Internal sales-prep intelligence for a (Company, Product) pair — what to pitch, why, how.
    Append-only, same spirit as `EnrichmentRecord`: regenerating creates a new row rather than
    overwriting, so history is preserved and nothing needs an `updated_at`."""

    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    pitch_summary: Mapped[str] = mapped_column(String)
    why_this_company: Mapped[str] = mapped_column(String)
    talking_points: Mapped[list[str]] = mapped_column(JSON)
    model_used: Mapped[str] = mapped_column(String(50))
