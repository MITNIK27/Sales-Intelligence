import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UpdatedAtMixin, new_uuid

FRAMING_STYLE_BUSINESS = "business"
FRAMING_STYLE_TECHNICAL = "technical"
FRAMING_STYLES = (FRAMING_STYLE_BUSINESS, FRAMING_STYLE_TECHNICAL)


class RoleCategory(Base, TimestampMixin, UpdatedAtMixin):
    """An org-defined function a contact can be classified against (e.g. "Vendor / IT
    Procurement"), mirroring `QualificationCriterion`'s shape exactly."""

    __tablename__ = "role_categories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String)

    # Explicit, not inferred from wording at judgment time — same guardrail reasoning as
    # QualificationCriterion.is_disqualifying. A category flagged primary is one that should be
    # surfaced first (vendor/procurement/tech-evaluation-adjacent); non-primary categories are
    # still tracked but deprioritized for a first cold reach.
    is_primary_target: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Which register Phase B's draft generator should write in for a contact matched to this
    # category (outcome/cost-savings language vs technical/KPI language) — explicit, same
    # reasoning as is_primary_target: the LLM writes within the register Python already picked,
    # it never infers the register itself from the category's name/description.
    framing_style: Mapped[str] = mapped_column(String(20), default=FRAMING_STYLE_BUSINESS)


class RoleRelevanceResult(Base, TimestampMixin):
    """A point-in-time role-relevance classification for a single Contact (Phase A3). Append-only,
    same spirit as `QualificationResult`: re-classifying creates a new row rather than
    overwriting, so history is preserved.

    `priority` is computed deterministically in `service.py` from the matched category's
    `is_primary_target` flag — never decided by the LLM. The LLM's only job is matching a contact
    to the best-fitting category (or none)."""

    __tablename__ = "role_relevance_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    # Denormalized from contact_id's owning company — cheap "all results for this company's
    # contacts" queries without a join, same locality reasoning as QualificationResult.company_id.
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contacts.id"), index=True)

    # Nullable — null means "no configured category genuinely fits this contact," a valid and
    # expected outcome, not a failure of the judgment.
    matched_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("role_categories.id")
    )
    # Snapshot AS JUDGED, not a live reference — a later rename/delete of the RoleCategory must
    # never rewrite this row's history.
    matched_category_name: Mapped[str | None] = mapped_column(String(255))
    is_primary_target: Mapped[bool] = mapped_column(Boolean)
    # Snapshot AS JUDGED, same reasoning as matched_category_name/is_primary_target above — a
    # later change to the category's framing_style must never rewrite this row's history. Null
    # only when there was no match at all (matched_category_id is also null in that case).
    matched_category_framing_style: Mapped[str | None] = mapped_column(String(20))

    priority: Mapped[str] = mapped_column(String(20))  # "primary" | "secondary" | "not_relevant"
    reasoning: Mapped[str] = mapped_column(String)
    model_used: Mapped[str] = mapped_column(String(50))
