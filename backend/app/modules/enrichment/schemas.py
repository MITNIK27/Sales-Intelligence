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
    # Which product to pitch when a bulk-confirmed company's drafting stage resumes — same
    # optionality as the auto-pipeline's own product_id (omitted means drafting is skipped for
    # that company, discovery/role-classification still happen).
    product_id: uuid.UUID | None = None


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


class SignalItem(BaseModel):
    signal_type: str  # "news" | "job_posting"
    text: str
    url: str
    date: str | None
    fetched_at: datetime
