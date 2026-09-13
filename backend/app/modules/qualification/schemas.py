import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator


class CriterionCreate(BaseModel):
    name: str
    description: str | None = None
    is_disqualifying: bool = False
    is_active: bool = True


class CriterionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_disqualifying: bool | None = None
    is_active: bool | None = None


class CriterionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    is_disqualifying: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CriterionList(BaseModel):
    items: list[CriterionOut]
    total: int
    limit: int
    offset: int


class QualificationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    overall_verdict: str
    # Read-only snapshot data ({criterion_id, criterion_name, is_disqualifying, verdict,
    # reasoning} per entry) — plain JSON passthrough, no need for a nested Pydantic model since
    # this is never written back through the API.
    criteria_results: list[dict[str, object]]
    model_used: str
    created_at: datetime


class AdhocQualificationCheckRequest(BaseModel):
    name: str | None = None
    domain: str | None = None

    @model_validator(mode="after")
    def _require_identifier(self) -> Self:
        if not (self.name or self.domain):
            raise ValueError("Provide a company name or domain.")
        return self
