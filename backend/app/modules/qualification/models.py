import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UpdatedAtMixin, new_uuid
from app.db.types import JsonB


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
    criteria_results: Mapped[list[dict[str, object]]] = mapped_column(JsonB)
    model_used: Mapped[str] = mapped_column(String(50))
    prompt_version: Mapped[str | None] = mapped_column(String(20))
    # The area a Quick Check was asked to judge fit around (e.g. a technology area). Null means a
    # general judgment, so a focused result is never mistaken for one.
    focus: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Priority Score 0-100 and its per-component breakdown, set by the auto pipeline's ranking step
    # (`ranking.py`). Null for results that were never ranked (single checks, older rows).
    priority_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_breakdown: Mapped[dict[str, object] | None] = mapped_column(JsonB, nullable=True)

    # The same judgments as `criteria_results`, one row per criterion (Phase 8a), so they can be
    # counted and filtered in SQL. Both are written together; `criteria_results` stays for one
    # release while readers move over, then it is dropped.
    criteria: Mapped[list["QualificationCriterionResult"]] = relationship(
        back_populates="result",
        cascade="all, delete-orphan",
        order_by="QualificationCriterionResult.position",
    )


class QualificationCriterionResult(Base, TimestampMixin):
    """One criterion as judged in a `QualificationResult`. A snapshot, like the result itself:
    `criterion_id` and `criterion_name` are copied, not a foreign key, because criteria defined
    for a single search are never saved as `QualificationCriterion` rows, and a later edit to a
    saved criterion must not rewrite past judgments."""

    __tablename__ = "qualification_criterion_results"
    __table_args__ = (
        UniqueConstraint("qualification_result_id", "position"),
        CheckConstraint("scope IN ('org', 'run')", name="scope"),
        CheckConstraint("verdict IN ('met', 'not_met', 'could_not_determine')", name="verdict"),
        CheckConstraint("status IN ('PASS', 'FAIL', 'UNKNOWN')", name="status"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    # Foreign keys named explicitly: the naming convention's names would pass Postgres' 63-character
    # limit for this table.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", name="fk_qual_criterion_results_organization"), index=True
    )
    qualification_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "qualification_results.id", name="fk_qual_criterion_results_result", ondelete="CASCADE"
        ),
        index=True,
    )
    # Order the criteria were judged in, as in `criteria_results`.
    position: Mapped[int] = mapped_column(SmallInteger)
    criterion_id: Mapped[uuid.UUID]
    criterion_name: Mapped[str] = mapped_column(String(255))
    is_disqualifying: Mapped[bool] = mapped_column(Boolean)
    # "run" = defined for one search on the confirm card, "org" = a saved criterion.
    scope: Mapped[str] = mapped_column(String(10))
    verdict: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(10))
    reasoning: Mapped[str | None] = mapped_column(Text)
    evidence_ref: Mapped[str | None] = mapped_column(String(100))
    evidence_quote: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String(100))
    url: Mapped[str | None] = mapped_column(Text)

    result: Mapped[QualificationResult] = relationship(back_populates="criteria")

    @classmethod
    def from_entry(
        cls, organization_id: uuid.UUID, position: int, entry: dict[str, Any]
    ) -> "QualificationCriterionResult":
        """The row for one `criteria_results` entry."""
        confidence = entry.get("confidence")
        return cls(
            organization_id=organization_id,
            position=position,
            criterion_id=uuid.UUID(str(entry["criterion_id"])),
            criterion_name=str(entry["criterion_name"])[:255],
            is_disqualifying=bool(entry["is_disqualifying"]),
            scope=str(entry.get("scope") or "org"),
            verdict=str(entry["verdict"]),
            status=str(entry["status"]),
            reasoning=entry.get("reasoning"),
            evidence_ref=entry.get("evidence_ref"),
            evidence_quote=entry.get("evidence_quote"),
            confidence=float(confidence) if confidence is not None else None,
            source=entry.get("source"),
            url=entry.get("url"),
        )
