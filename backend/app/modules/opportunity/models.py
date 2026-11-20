import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UpdatedAtMixin, new_uuid
from app.db.types import JsonB

# `area_key` of the opportunity that means "no particular area": the company as a whole.
GENERAL_AREA_KEY = "general"

ORIGIN_QUICK_CHECK = "quick_check"
ORIGIN_MARKET_DISCOVERY = "market_discovery"
ORIGIN_SUGGESTED = "suggested"
ORIGIN_MANUAL = "manual"

# A suggested area has been proposed from evidence but nobody has chosen to look into it yet;
# nothing deep is researched for it until it is made active.
STATUS_SUGGESTED = "suggested"
STATUS_ACTIVE = "active"
STATUS_ARCHIVED = "archived"

# Why an area is in the suggested list: the person searched for the offering in Market Discovery,
# the evidence points to it near what they searched, or it is a next best area.
SOURCE_SEARCHED = "searched"
SOURCE_EVIDENCE = "evidence"
SOURCE_NEXT_BEST = "next_best"
SUGGESTION_SOURCES = (SOURCE_SEARCHED, SOURCE_EVIDENCE, SOURCE_NEXT_BEST)

VERDICT_SUPPORTED = "supported"
VERDICT_EMERGING = "emerging"
VERDICT_WEAK = "weak"
VERDICT_INSUFFICIENT = "insufficient_evidence"


class CompanyOpportunity(Base, TimestampMixin, UpdatedAtMixin):
    """A company seen through one business area (for example "cloud migration"). Mutable header:
    the judgments made about it are the append-only `OpportunityAssessment` rows. Unique per
    (organization, company, area_key), so asking for the same area twice finds the same row."""

    __tablename__ = "company_opportunities"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "company_id", "area_key", name="uq_company_opportunities_area"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    area_key: Mapped[str] = mapped_column(String(120))  # normalised slug, see areas.py
    area_label: Mapped[str] = mapped_column(String(200))  # as a person would read it
    origin: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(12), default=STATUS_ACTIVE)
    # The company's industry as it was when this opportunity was created, so a later change to the
    # company does not rewrite what an earlier judgment was based on.
    industry_context: Mapped[str | None] = mapped_column(String(255))
    # The Market Discovery run that first created it, if any. A company can appear in many runs;
    # run membership lives in `ingestion_run_companies`, not here.
    created_by_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_runs.id"), index=True
    )
    # Why an area was suggested (one sentence), kept with the suggestion.
    suggestion_reason: Mapped[str | None] = mapped_column(String(500))
    # Where a suggestion came from (SUGGESTION_SOURCES), its place in the list (lower is first), and
    # a fingerprint of the offerings it was made for, so a list made for others is not reused.
    suggestion_source: Mapped[str | None] = mapped_column(String(20))
    suggestion_rank: Mapped[int | None] = mapped_column(Integer)
    suggestion_focus: Mapped[str | None] = mapped_column(String(64))
    # What each collector (news, hiring, web) did last time: when, what it searched, how much it
    # found, any error, and for hiring the counts over time. It decides what is still fresh and is
    # the source of the plain "searched, found nothing" statements.
    research_log: Mapped[dict[str, Any] | None] = mapped_column(JsonB)


class OpportunityAssessment(Base, TimestampMixin):
    """What the evidence says about a company in one area, at one point in time. Append-only,
    versioned per opportunity: a new assessment is a new row, never an edit of an old one.

    Every finding cites evidence by a stable record id (not a position in a prompt) with the exact
    quote, source address, fetch time and a hash of the text it was found in, so a past judgment
    can be re-checked later even after the evidence has been re-fetched. `evidence_set_hash`
    fingerprints everything the model was shown; together with `prompt_version` it is the cache
    key, so an unchanged evidence set is never judged twice."""

    __tablename__ = "opportunity_assessments"
    __table_args__ = (
        UniqueConstraint(
            "company_opportunity_id", "version", name="uq_opportunity_assessments_version"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    company_opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("company_opportunities.id"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    verdict: Mapped[str] = mapped_column(String(24))
    summary: Mapped[str] = mapped_column(String)
    # [{kind, statement, evidence: {record_id|field, url, fetched_at, quote, content_hash}}]
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JsonB)
    # What was looked for and not found, in the model's words, shown so a gap is never silent.
    not_found: Mapped[list[str]] = mapped_column(JsonB)
    # Findings the model produced that failed verification and were therefore dropped.
    dropped_count: Mapped[int] = mapped_column(Integer, default=0)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    evidence_set_hash: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(20))
    model_used: Mapped[str] = mapped_column(String(50))


BAND_STRONG = "strong"
BAND_POTENTIAL = "potential"
BAND_WEAK = "weak"
BAND_INSUFFICIENT = "insufficient_evidence"

ROLE_DECISION_MAKER = "decision_maker"
ROLE_INFLUENCER = "influencer"
ROLE_USER = "user"
ROLE_NOT_RELEVANT = "not_relevant"
ROLES = (ROLE_DECISION_MAKER, ROLE_INFLUENCER, ROLE_USER, ROLE_NOT_RELEVANT)
# A human row with this role withdraws the person's earlier override, so the model's judgment
# applies again. Rows are never deleted: the history of overrides is kept.
ROLE_REVERT = "revert"

SOURCE_MODEL = "model"
SOURCE_HUMAN = "human"


class OpportunityOfferingMatch(Base, TimestampMixin):
    """How well one InfoBeans offering fits a company in one area, at one point in time.
    Append-only. The band and score are computed in code from explicit `factors` (how much verified
    evidence, whether the offering belongs to the area, how many of its profile keywords the
    evidence uses, what the opportunity's verdict is), never taken from the model; the model only
    explains the fit and cites evidence, and every citation is verified. The cache key is the
    opportunity's latest assessment, the offering's buyer-profile hash, the evidence fingerprint
    and the prompt version: unchanged, it is not judged again."""

    __tablename__ = "opportunity_offering_matches"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    company_opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("company_opportunities.id"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunity_assessments.id"), index=True
    )
    band: Mapped[str] = mapped_column(String(24))
    score: Mapped[int] = mapped_column(Integer)  # 0-100, from the factors
    factors: Mapped[dict[str, Any]] = mapped_column(JsonB)
    reasoning: Mapped[str] = mapped_column(String)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JsonB)  # verified citations
    needs_review: Mapped[bool] = mapped_column(default=False)
    profile_hash: Mapped[str | None] = mapped_column(String(64))
    evidence_set_hash: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(20))
    model_used: Mapped[str] = mapped_column(String(50))


class ContactOpportunityRelevance(Base, TimestampMixin):
    """Whether a contact matters for an opportunity (and, optionally, one offering). Append-only,
    and a model's judgment and a person's override are different rows told apart by `source`: on
    read, the latest human row wins and the model's row stays visible beneath it. A contact can be
    relevant to one opportunity and not to another. `contact_hash` fingerprints the title and
    seniority judged, so a changed title is judged again."""

    __tablename__ = "contact_opportunity_relevance"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    company_opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("company_opportunities.id"), index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contacts.id"), index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id"), index=True)
    source: Mapped[str] = mapped_column(String(8))  # model | human
    role: Mapped[str] = mapped_column(String(16))  # ROLES, or "revert" on a human row
    function: Mapped[str | None] = mapped_column(String(120))  # the function the title implies
    reasoning: Mapped[str] = mapped_column(String)
    confidence: Mapped[str | None] = mapped_column(String(8))  # low | medium | high (model rows)
    needs_review: Mapped[bool] = mapped_column(default=False)
    note: Mapped[str | None] = mapped_column(String(500))  # why a person overrode it
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunity_assessments.id"), index=True
    )
    profile_hash: Mapped[str | None] = mapped_column(String(64))
    contact_hash: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(20))
    model_used: Mapped[str | None] = mapped_column(String(50))
