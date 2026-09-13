import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RecommendationGenerateRequest(BaseModel):
    product_id: uuid.UUID
    contact_id: uuid.UUID | None = None


class RecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    contact_id: uuid.UUID | None
    product_id: uuid.UUID
    pitch_summary: str
    why_this_company: str
    talking_points: list[str]
    model_used: str
    created_at: datetime
