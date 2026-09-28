import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CsvIngestionStarted(BaseModel):
    ingestion_run_id: uuid.UUID
    job_id: uuid.UUID


class MarketDiscoveryParseRequest(BaseModel):
    raw_input: str


class MarketDiscoveryParsed(BaseModel):
    ingestion_run_id: uuid.UUID
    parsed_fields: dict[str, Any]


class MarketDiscoveryConfirmRequest(BaseModel):
    industry_keywords: list[str] = []
    location: str | None = None
    employee_size_range: str | None = None
    # Which product the auto-pipeline's drafting stage should pitch. Optional — omitted (and the
    # org doesn't have exactly one product to default to) means the pipeline still discovers,
    # qualifies, and classifies roles, but the drafting stage reports itself skipped rather than
    # guessing which product to pitch.
    product_id: uuid.UUID | None = None


class MarketDiscoveryStarted(BaseModel):
    job_id: uuid.UUID


class MarketDiscoveryRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    raw_input: str | None
    parsed_fields: dict[str, Any] | None
    confirmed_at: datetime | None
    summary: dict[str, Any] | None
    error: str | None
