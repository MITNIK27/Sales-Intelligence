"""Response shapes for the read-only dashboard. Plain-language field names where a rep sees them."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Kpis(BaseModel):
    searches: int
    companies: int
    fit: int  # qualified: meet every hard requirement
    needs_closer_look: int  # a hard requirement could not be verified
    rejected: int  # clearly failed a hard requirement
    contacts: int
    likely_decision_makers: int  # contacts at or above the "likely match" confidence
    drafts_to_review: int
    drafts_sent: int
    credits_used: int


class FunnelStage(BaseModel):
    key: str
    label: str
    count: int
    percent_of_previous: int | None  # None for the first stage


class RequirementResult(BaseModel):
    name: str
    scope: str  # "run" (set for one search) | "org" (saved criterion)
    hard: bool
    meets: int
    couldnt_verify: int
    doesnt_meet: int
    drafts_for_meeting: int  # companies that meet it AND have a draft


class TopCompany(BaseModel):
    company_id: uuid.UUID
    name: str
    domain: str | None
    score: float | None
    verdict: str | None
    reason: str | None


class AttentionItem(BaseModel):
    key: str  # ready_to_contact | drafts_to_review | follow_ups_due | needs_closer_look | searches
    label: str
    count: int
    href: str


class ActivityEvent(BaseModel):
    at: datetime
    kind: str  # search | draft | outreach | failure
    text: str
    run_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None


class Health(BaseModel):
    credits_used: int
    credit_ceiling: int | None
    budget_exhausted: bool
    companies_needing_no_paid_lookup: int
    enrichment_failed: int
    provider_errors: dict[str, int]
    notes: list[str]


class Setup(BaseModel):
    products: int
    active_criteria: int
    active_role_categories: int


class RunStats(BaseModel):
    run_id: uuid.UUID
    title: str  # the search as the rep wrote it
    summary: str  # parsed filters in a short line
    status: str
    created_at: datetime
    error: str | None
    companies: int
    fit: int
    needs_closer_look: int
    rejected: int
    contacts: int
    drafts: int
    top_score: float | None
    credits_used: int | None


class RunHeader(BaseModel):
    run_id: uuid.UUID
    title: str
    summary: str
    status: str
    created_at: datetime
    error: str | None
    data_source: str | None
    pipeline: dict[str, Any] | None  # the auto-pipeline job's stage outcomes, if there is one
    progress: dict[str, Any] | None


class SearchOption(BaseModel):
    run_id: uuid.UUID
    label: str
    created_at: datetime


class Overview(BaseModel):
    scope: str  # "all" | "search"
    period: str
    headline: str
    kpis: Kpis
    funnel: list[FunnelStage]
    requirements: list[RequirementResult]
    top_companies: list[TopCompany]
    attention: list[AttentionItem]
    activity: list[ActivityEvent]
    health: Health
    setup: Setup
    run: RunHeader | None
    searches: list[SearchOption]  # for the scope selector


class RunList(BaseModel):
    items: list[RunStats]
    total: int
    limit: int
    offset: int
