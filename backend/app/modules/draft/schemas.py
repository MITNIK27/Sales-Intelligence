import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.modules.draft.models import DRAFT_TYPES


class DraftGenerateRequest(BaseModel):
    contact_id: uuid.UUID
    product_id: uuid.UUID
    draft_type: str

    @field_validator("draft_type")
    @classmethod
    def validate_draft_type(cls, v: str) -> str:
        if v not in DRAFT_TYPES:
            raise ValueError(f"draft_type must be one of {DRAFT_TYPES}")
        return v


class DraftUpdateRequest(BaseModel):
    subject: str | None = None
    body: str | None = None


class DraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    contact_id: uuid.UUID
    product_id: uuid.UUID
    recommendation_id: uuid.UUID | None
    draft_type: str
    channel: str
    subject: str | None
    body: str
    status: str
    model_used: str
    created_at: datetime
    updated_at: datetime
