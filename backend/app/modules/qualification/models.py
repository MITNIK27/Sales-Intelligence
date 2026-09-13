import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UpdatedAtMixin, new_uuid


class QualificationCriterion(Base, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "qualification_criteria"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String)

    # Explicit, not inferred from `description` wording by a future judgment step: if a company
    # clearly fails this criterion, that's an automatic not-qualified verdict rather than one
    # input among many. Set by whoever defines the criterion, not guessed at judgment time.
    is_disqualifying: Mapped[bool] = mapped_column(Boolean, default=False)
    # Lets an org retire a criterion without deleting it (and without breaking any future
    # judgment history that references it) — same reasoning as Company.needs_review-style flags
    # elsewhere in this codebase preferring a flag over a hard delete.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class QualificationResult(Base, TimestampMixin):
    """A point-in-time qualification judgment for a Company (Phase A2.2). Append-only, same
    spirit as `Recommendation`: re-checking creates a new row rather than overwriting, so history
    (including "was this qualified before, and is it still now") is preserved.

    `overall_verdict` is computed deterministically in `service.py` from `criteria_results` —
    never decided by the LLM itself. The LLM only judges each criterion individually; the
    qualified/not_qualified/could_not_determine gate is auditable Python logic keyed off which
    criteria are `is_disqualifying`, not a model inferring intent from wording."""

    __tablename__ = "qualification_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    overall_verdict: Mapped[str] = mapped_column(String(30))
    # list[{criterion_id, criterion_name, is_disqualifying, verdict, reasoning}] — a snapshot of
    # each criterion AS JUDGED, not a live reference, so a later edit to a QualificationCriterion
    # never rewrites past judgment history.
    criteria_results: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    model_used: Mapped[str] = mapped_column(String(50))
