import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.modules.draft.models import DRAFT_TYPES

MAX_INSTRUCTION_CHARS = 600


class DraftGenerateRequest(BaseModel):
    contact_id: uuid.UUID
    product_id: uuid.UUID
    draft_type: str
    # The opportunity (business area) the draft is for, when it was started from one.
    opportunity_id: uuid.UUID | None = None

    @field_validator("draft_type")
    @classmethod
    def validate_draft_type(cls, v: str) -> str:
        if v not in DRAFT_TYPES:
            raise ValueError(f"draft_type must be one of {DRAFT_TYPES}")
        return v


class DraftUpdateRequest(BaseModel):
    subject: str | None = None
    body: str | None = None


class RefineRequest(BaseModel):
    """Rewrite this draft the way the rep describes. `subject` and `body` are the text as the rep
    has it on screen (hand edits included), so that is what gets rewritten."""

    instruction: str
    subject: str | None = None
    body: str

    @field_validator("instruction")
    @classmethod
    def tidy_instruction(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("describe the change in a few words")
        if len(v) > MAX_INSTRUCTION_CHARS:
            raise ValueError(f"keep the request under {MAX_INSTRUCTION_CHARS} characters")
        return v

    @field_validator("body")
    @classmethod
    def body_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("the draft is empty")
        return v


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
    grounding_flags: list[str] | None = None
    # What the rep last asked for, and how many earlier versions can be restored.
    instruction: str | None = None
    revision_count: int = 0
    created_at: datetime
    updated_at: datetime


class DraftListItem(BaseModel):
    """One draft with enough context (who, where) to review it without opening the company."""

    id: uuid.UUID
    company_id: uuid.UUID
    company_name: str
    contact_id: uuid.UUID
    contact_name: str | None
    contact_role: str | None
    draft_type: str
    channel: str
    subject: str | None
    body: str
    status: str
    model_used: str
    grounding_flags: list[str] | None = None
    created_at: datetime
    updated_at: datetime


class DraftListOut(BaseModel):
    items: list[DraftListItem]
    total: int  # matching the status filter
    limit: int
    offset: int
    counts: dict[str, int]  # per status, always all three, regardless of the filter
