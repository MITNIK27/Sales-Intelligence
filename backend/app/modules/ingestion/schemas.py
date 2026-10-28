import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CsvIngestionStarted(BaseModel):
    ingestion_run_id: uuid.UUID
    job_id: uuid.UUID


class MarketDiscoveryParseRequest(BaseModel):
    raw_input: str


class MarketDiscoveryParsed(BaseModel):
    ingestion_run_id: uuid.UUID
    parsed_fields: dict[str, Any]


class MarketFitCriterionIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class MarketDiscoveryConfirmRequest(BaseModel):
    industry_keywords: list[str] = []
    location: str | None = None
    employee_size_range: str | None = None
    # Which product(s) the auto-pipeline's drafting stage may pitch. Optional — empty (and the org
    # doesn't have exactly one product to default to) means the pipeline still discovers,
    # qualifies, and classifies roles, but the drafting stage reports itself skipped rather than
    # guessing which product to pitch. More than one product means the draft generator itself picks
    # whichever single product best fits each company/contact — never more than one per email.
    product_ids: list[uuid.UUID] = []
    # Hard requirements for THIS search (e.g. "operates in logistics"), judged for every company
    # alongside the organization's saved criteria. Not stored as org settings.
    market_fit_criteria: list[MarketFitCriterionIn] = []


class MarketDiscoveryStarted(BaseModel):
    job_id: uuid.UUID


class WorklistDraftOut(BaseModel):
    draft_id: uuid.UUID
    subject: str | None
    body: str
    status: str


class WorklistContactOut(BaseModel):
    contact_id: uuid.UUID
    full_name: str | None
    role_title: str | None
    category: str | None
    linkedin_url: str | None
    email: str | None
    needs_review: bool
    needs_review_reason: str | None
    draft: WorklistDraftOut | None
    confidence: float | None = None
    source: str | None = None


class WorklistCriterionOut(BaseModel):
    name: str
    status: str
    hard: bool
    scope: str
    reasoning: str | None
    evidence_quote: str | None
    source: str | None
    url: str | None
    confidence: float | None


class WorklistRowOut(BaseModel):
    company_id: uuid.UUID
    name: str
    domain: str | None
    industry: str | None
    employee_count_range: str | None
    description: str | None
    data_source: str
    verdict: str | None
    why: str | None
    candidates: list[WorklistContactOut]
    skip_reason: str | None
    criteria: list[WorklistCriterionOut] = []
    confidence: float | None = None
    priority_score: float | None = None
    score_breakdown: dict[str, Any] | None = None
    provenance: dict[str, Any] = {}


class MarketDiscoveryWorklistOut(BaseModel):
    ready: list[WorklistRowOut]
    not_shown: list[WorklistRowOut]


class MarketDiscoveryRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    raw_input: str | None
    parsed_fields: dict[str, Any] | None
    confirmed_at: datetime | None
    summary: dict[str, Any] | None
    error: str | None
