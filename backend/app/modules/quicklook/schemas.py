import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class QuickLookRequest(BaseModel):
    """A company name or website in `company` (one field, like the rest of the app), or a website
    in `domain` when the person pasted one or chose a candidate. `avoid` lists websites already
    rejected with "not this one"."""

    company: str | None = Field(default=None, max_length=200)
    domain: str | None = Field(default=None, max_length=255)
    avoid: list[str] = Field(default_factory=list, max_length=20)
    refresh: bool = False
    # Show the candidates instead of picking one (the "not this one" flow).
    always_ask: bool = False
    # Optional extras. They never change the call: the focus is an area to research the company
    # around, and the criteria are the person's own questions, shown as a separate list.
    focus: str | None = Field(default=None, max_length=200)
    criteria: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("criteria")
    @classmethod
    def _clean_criteria(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            text = " ".join(item.split())[:200]
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned


class OfferingFitOut(BaseModel):
    product_id: str
    name: str
    band: str
    reason: str
    quote: str | None = None
    source_url: str | None = None
    source_kind: str | None = None  # site | news | hiring | search
    source_date: str | None = None
    # What we would offer them and which of their moves it builds on; only when proven.
    idea: str | None = None
    why_now: str | None = None


class WorkingOnOut(BaseModel):
    """Something the company is doing in an area we sell in, with the evidence behind it."""

    point: str
    quote: str
    source_url: str | None = None
    source_kind: str | None = None
    source_date: str | None = None


class CriterionResultOut(BaseModel):
    name: str
    verdict: str  # met | not_met | unknown
    reason: str
    quote: str | None = None
    source_url: str | None = None


class SnapshotOut(BaseModel):
    id: uuid.UUID
    domain: str
    name: str
    what_they_do: str | None
    industry: str | None
    size_hint: str | None
    relevance: str | None
    call: str
    call_reason: str
    offerings: list[OfferingFitOut]
    working_on: list[WorkingOnOut] = []
    focus: str | None = None
    criteria: list[CriterionResultOut] = []
    # Passages from our documents the model was shown (Phase 8d), `cited` when the answer names
    # them.
    knowledge: list[dict[str, Any]] = []
    sources: list[dict[str, Any]]
    updated_at: datetime
    cached: bool
    existing_company_id: uuid.UUID | None
    # Set when that company was marked not a fit: the reason the person gave.
    existing_company_dismissed_reason: str | None = None


class CandidateOut(BaseModel):
    name: str
    domain: str
    snippet: str


class QuickLookResponse(BaseModel):
    status: str  # ready | needs_choice | not_found
    snapshot: SnapshotOut | None = None
    candidates: list[CandidateOut] = []
    notes: list[str] = []


class CheckedCompanyOut(BaseModel):
    """A company in the person's Quick Check history: one row per website."""

    domain: str
    name: str
    last_checked_at: datetime
    checks: int
    last_call: str
    last_focus: str | None = None
    existing_company_id: uuid.UUID | None = None


class CheckedCompanyList(BaseModel):
    items: list[CheckedCompanyOut]
    total: int


class CheckEntryOut(BaseModel):
    """One check of a company: when, what was asked, and the call it got then."""

    id: uuid.UUID
    checked_at: datetime
    asked: str | None = None
    focus: str | None = None
    criteria: list[str] = []
    call: str
    call_reason: str = ""
    cached: bool
    refreshed: bool


class CompanyChecksOut(BaseModel):
    domain: str
    name: str
    entries: list[CheckEntryOut]


class CheckAnswerOut(BaseModel):
    """An earlier check's answer exactly as it was given. `answer.id` is the company's current
    snapshot, so saving it works as from a fresh look-up."""

    entry_id: uuid.UUID
    checked_at: datetime
    criteria: list[str] = []
    answer: SnapshotOut


class SaveRequest(BaseModel):
    snapshot_id: uuid.UUID
    go_deeper: bool = False


class SaveResponse(BaseModel):
    company_id: uuid.UUID
    created: bool
    job_id: uuid.UUID | None = None
