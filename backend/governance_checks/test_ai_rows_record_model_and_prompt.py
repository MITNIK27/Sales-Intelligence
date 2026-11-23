"""G9: every row an AI writes records which model and which prompt version wrote it, so a bad
answer can be traced and a prompt change can be told apart from a model change. A ratchet: the
gaps below are known, a new AI table with a gap fails, and a fixed gap must leave the list."""

from sqlalchemy.orm import DeclarativeBase

from app.modules.ai_recommendation.models import Recommendation
from app.modules.documents.models import DocumentAsset, DocumentSummary, KnowledgeCard
from app.modules.draft.models import Draft
from app.modules.offerings.models import OfferingProposal
from app.modules.opportunity.models import (
    ContactOpportunityRelevance,
    OpportunityAssessment,
    OpportunityOfferingMatch,
)
from app.modules.qualification.models import QualificationResult
from app.modules.quicklook.models import CompanySnapshot
from app.modules.role_relevance.models import RoleRelevanceResult

REQUIRED = {"model_used", "prompt_version"}

# Tables whose rows hold model-written content. Add a new AI table here when you create it.
AI_TABLES: list[type[DeclarativeBase]] = [
    CompanySnapshot,
    ContactOpportunityRelevance,
    DocumentAsset,
    DocumentSummary,
    Draft,
    KnowledgeCard,
    OfferingProposal,
    OpportunityAssessment,
    OpportunityOfferingMatch,
    QualificationResult,
    Recommendation,
    RoleRelevanceResult,
]

# What each table is still missing. Empty: every AI table has both columns. A table that cannot
# have them yet goes here with a reason, and leaves again when it is fixed.
KNOWN_GAPS: dict[str, set[str]] = {}


def _missing(model: type[DeclarativeBase]) -> set[str]:
    return REQUIRED - {column.name for column in model.__table__.columns}


def test_ai_tables_record_model_and_prompt_except_known_gaps() -> None:
    actual = {m.__name__: _missing(m) for m in AI_TABLES if _missing(m)}
    assert actual == KNOWN_GAPS, (
        "AI-written tables must record model_used and prompt_version (docs/ai-governance.md, G9). "
        f"Missing now: {actual}. Known gaps: {KNOWN_GAPS}. Fix the table, or if you fixed one, "
        "remove it from KNOWN_GAPS."
    )
