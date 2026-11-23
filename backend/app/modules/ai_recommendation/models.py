import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_uuid
from app.db.types import JsonB


class Recommendation(Base, TimestampMixin):
    """Internal sales-prep intelligence for a (Company, Product) pair — what to pitch, why, how.
    Append-only, same spirit as `EnrichmentRecord`: regenerating creates a new row rather than
    overwriting, so history is preserved and nothing needs an `updated_at`."""

    __tablename__ = "recommendations"
    # One recommendation per opportunity, offering and assessment version, so a double click or a
    # reopened page cannot create a duplicate. Rows with no opportunity are unaffected: NULLs are
    # distinct, so every recommendation written before opportunities existed stays valid.
    __table_args__ = (
        UniqueConstraint(
            "company_opportunity_id",
            "product_id",
            "opportunity_assessment_id",
            name="uq_recommendations_opportunity_assessment",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    pitch_summary: Mapped[str] = mapped_column(String)
    why_this_company: Mapped[str] = mapped_column(String)
    talking_points: Mapped[list[str]] = mapped_column(JsonB)
    model_used: Mapped[str] = mapped_column(String(50))
    prompt_version: Mapped[str | None] = mapped_column(String(20))
    # Passages from our own documents the model was shown (Phase 8d); see OpportunityOfferingMatch.
    knowledge_refs: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonB)
    # The opportunity (business area) this was written for and the assessment version it was
    # grounded in; both null for recommendations made before opportunities existed.
    company_opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("company_opportunities.id"), index=True
    )
    opportunity_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunity_assessments.id"), index=True
    )
