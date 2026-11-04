import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class CompanyCriterionIn(BaseModel):
    """One thing to find out about a company, typed by the person."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    must_have: bool = False


class CompanyCriterionOut(CompanyCriterionIn):
    pass


class CompanyCriteriaUpdate(BaseModel):
    """The company's whole list of criteria; it replaces what was stored."""

    criteria: list[CompanyCriterionIn] = Field(default_factory=list, max_length=10)


class AdhocQualificationCheckRequest(BaseModel):
    # What the person typed: a company name or its website, in one field. `name` and `domain`
    # remain accepted for older callers.
    company: str | None = None
    # Optional area to judge fit around (e.g. a technology area); empty means a general judgment.
    focus: str | None = Field(default=None, max_length=200)
    # Offerings to judge fit for. Empty means: judge only the single best match.
    product_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    name: str | None = None
    domain: str | None = None

    @model_validator(mode="after")
    def _require_identifier(self) -> Self:
        if not (self.company and self.company.strip()) and not (self.name or self.domain):
            raise ValueError("Provide a company name or website.")
        return self
