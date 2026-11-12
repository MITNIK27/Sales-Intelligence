import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.contacts.schemas import ContactOut
from app.modules.review.service import NOT_A_FIT_REASONS


class CompanyListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    domain: str | None
    industry: str | None
    contact_count: int
    enrichment_status: str
    needs_review: bool
    qualification_verdict: str | None
    created_at: datetime
    last_enriched_at: datetime | None
    dismissed_at: datetime | None = None
    dismissed_reason: str | None = None


class CompanyList(BaseModel):
    items: list[CompanyListItem]
    total: int
    limit: int
    offset: int


class CompanyDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    domain: str | None
    industry: str | None
    employee_count_range: str | None
    description: str | None
    enrichment_status: str
    needs_review: bool
    needs_review_reason: str | None
    last_enriched_at: datetime | None
    enrichment_error: str | None
    criteria: list[dict[str, object]] = []
    dismissed_at: datetime | None = None
    dismissed_reason: str | None = None
    dismissed_note: str | None = None
    contacts: list[ContactOut]


class CompanyDismissRequest(BaseModel):
    reason: str
    note: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def _known_reason(cls, value: str) -> str:
        if value not in NOT_A_FIT_REASONS:
            raise ValueError(f"reason must be one of {NOT_A_FIT_REASONS}")
        return value


class CompanyBulkDismissRequest(CompanyDismissRequest):
    company_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class CompanyBulkDismissResult(BaseModel):
    dismissed: int
    already_dismissed: int
    not_found: list[uuid.UUID]


class CompanyConfirmRequest(BaseModel):
    product_ids: list[uuid.UUID] = []


class CompanyConfirmResult(BaseModel):
    """Result of confirming a company: it's no longer `needs_review`, and — since that's exactly
    what was blocking it — role classification and drafting have already been (re-)attempted for
    it as part of the same call, not left as a separate manual step."""

    company: CompanyDetail
    role_classification: dict[str, Any]
    drafting: dict[str, Any]
