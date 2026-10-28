import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ScrapeJobStarted(BaseModel):
    job_id: uuid.UUID


class ScrapeAllStarted(BaseModel):
    enqueued_count: int


class BulkConfirmRequest(BaseModel):
    company_ids: list[uuid.UUID] = []
    contact_ids: list[uuid.UUID] = []
    # Which product(s) to pitch when a bulk-confirmed company's drafting stage resumes — same
    # optionality as the auto-pipeline's own product_ids (empty means drafting is skipped for
    # that company, discovery/role-classification still happen).
    product_ids: list[uuid.UUID] = []


class BulkConfirmStarted(BaseModel):
    job_id: uuid.UUID


class NeedsReviewItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_type: str  # "company" | "contact"
    company_id: uuid.UUID
    company_name: str
    contact_id: uuid.UUID | None
    contact_name: str | None
    reason: str
    flagged_at: datetime
    contact_title: str | None = None
    contact_email: str | None = None
    contact_linkedin: str | None = None
    contact_source: str | None = None
    contact_confidence: float | None = None
    company_domain: str | None = None


class SignalItem(BaseModel):
    signal_type: str  # "news" | "job_posting"
    text: str
    url: str
    date: str | None
    fetched_at: datetime
    summary: str | None = None
    provider: str | None = None  # "contextdev" | "scraper:companysite"
