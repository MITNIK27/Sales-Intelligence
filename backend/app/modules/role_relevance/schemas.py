import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.modules.role_relevance.models import FRAMING_STYLES


class RoleCategoryCreate(BaseModel):
    name: str
    description: str | None = None
    is_primary_target: bool = False
    is_active: bool = True
    framing_style: str = "business"

    @field_validator("framing_style")
    @classmethod
    def validate_framing_style(cls, v: str) -> str:
        if v not in FRAMING_STYLES:
            raise ValueError(f"framing_style must be one of {FRAMING_STYLES}")
        return v


class RoleCategoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_primary_target: bool | None = None
    is_active: bool | None = None
    framing_style: str | None = None

    @field_validator("framing_style")
    @classmethod
    def validate_framing_style(cls, v: str | None) -> str | None:
        if v is not None and v not in FRAMING_STYLES:
            raise ValueError(f"framing_style must be one of {FRAMING_STYLES}")
        return v


class RoleCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    is_primary_target: bool
    is_active: bool
    framing_style: str
    created_at: datetime
    updated_at: datetime


class RoleCategoryList(BaseModel):
    items: list[RoleCategoryOut]
    total: int
    limit: int
    offset: int


class RoleRelevanceResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    contact_id: uuid.UUID
    matched_category_id: uuid.UUID | None
    matched_category_name: str | None
    is_primary_target: bool
    matched_category_framing_style: str | None
    priority: str
    reasoning: str
    model_used: str
    created_at: datetime
