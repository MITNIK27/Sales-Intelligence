import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    focus: str | None = None
    created_at: datetime


class AdhocQualificationCheckRequest(BaseModel):
    # What the person typed: a company name or its website, in one field. `name` and `domain`
    # remain accepted for older callers.
    company: str | None = None
    # Optional area to judge fit around (e.g. a technology area); empty means a general judgment.
    focus: str | None = Field(default=None, max_length=200)
    name: str | None = None
    domain: str | None = None

    @model_validator(mode="after")
    def _require_identifier(self) -> Self:
        if not (self.company and self.company.strip()) and not (self.name or self.domain):
            raise ValueError("Provide a company name or website.")
        return self
