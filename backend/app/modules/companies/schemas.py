import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.modules.contacts.schemas import ContactOut


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
    contacts: list[ContactOut]


class CompanyConfirmRequest(BaseModel):
    product_ids: list[uuid.UUID] = []


class CompanyConfirmResult(BaseModel):
    """Result of confirming a company: it's no longer `needs_review`, and — since that's exactly
    what was blocking it — role classification and drafting have already been (re-)attempted for
    it as part of the same call, not left as a separate manual step."""

    company: CompanyDetail
    role_classification: dict[str, Any]
    drafting: dict[str, Any]
