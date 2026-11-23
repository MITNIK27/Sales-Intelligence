import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    verdict: str
    summary: str
    # [{kind, statement, evidence: {record_id, field, kind, url, date, fetched_at, content_hash,
    #   quote}}]: the citation is stored, so it can be shown without re-reading the source.
    findings: list[dict[str, Any]]
    not_found: list[str]
    dropped_count: int
    evidence_count: int
    model_used: str
    created_at: datetime


class OpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    area_key: str
    area_label: str
    origin: str
    status: str
    suggestion_reason: str | None
    suggestion_source: str | None = None
    suggestion_rank: int | None = None
    # Passages from our documents the suggestion cited (Phase 8d).
    suggestion_knowledge_refs: list[dict[str, Any]] | None = None
    industry_context: str | None
    created_at: datetime
    assessment: AssessmentOut | None = None
    # What the research collectors did last time (see research/report.py), for the screen.
    research: dict[str, Any] | None = None


class AssessRequest(BaseModel):
    # A fresh look even when the evidence has not changed since the last assessment.
    force: bool = False
    # Offerings to judge as soon as the research is done (the ones a search was about).
    product_ids: list[uuid.UUID] = []


class SuggestRequest(BaseModel):
    # An explicit second look: ask the model again and replace the suggestions, instead of
    # returning the ones already made.
    refresh: bool = False
    # Offerings the person has selected on the Brief. Areas near them are suggested after the ones
    # the company was searched for in Market Discovery, which the server finds on its own.
    offering_ids: list[uuid.UUID] = []


class AssessStarted(BaseModel):
    job_id: uuid.UUID


class FitMatchOut(BaseModel):
    """How well one offering fits the opportunity. The band is decided by rules from `factors`,
    and every item in `evidence` was checked to be a real quote from its source."""

    product_id: uuid.UUID
    product_name: str
    product_kind: str
    band: str
    score: int
    reasoning: str
    factors: dict[str, Any]
    evidence: list[dict[str, Any]]
    needs_review: bool
    # Passages from our documents the model was shown about this offering, with `cited` when its
    # reasoning names the label.
    knowledge_refs: list[dict[str, Any]] | None = None
    created_at: datetime


class ContactRelevanceOut(BaseModel):
    """A person and what part they play for this opportunity. `source` says whether the model or a
    person decided; when a person overrode the model, the model's own view is still here."""

    contact_id: uuid.UUID
    full_name: str | None
    role_title: str | None
    seniority: str | None
    contact_needs_review: bool
    role: str | None  # null until the person has been judged
    function: str | None = None
    reasoning: str | None = None
    confidence: str | None = None
    needs_review: bool = False
    source: str | None = None
    note: str | None = None
    model_role: str | None = None
    model_reasoning: str | None = None


class AnalyseRequest(BaseModel):
    # Offerings to judge; empty means "find the ones that fit".
    product_ids: list[uuid.UUID] = []
    with_contacts: bool = True
    force: bool = False


class RelevanceOverrideRequest(BaseModel):
    product_id: uuid.UUID | None = None
    role: str
    note: str | None = None


class RecommendRequest(BaseModel):
    product_id: uuid.UUID
    force: bool = False


class OpportunityCreateRequest(BaseModel):
    # The area to look into, in the person's own words; empty means the company overall.
    area_label: str | None = None
