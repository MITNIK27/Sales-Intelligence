import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.modules.contacts.schemas import ContactOut
from app.modules.outreach.models import ACTIVITY_TYPES, OUTREACH_CHANNELS


class LogOutreachActivityRequest(BaseModel):
    channel: str
    activity_type: str
    template_variant: str | None = None
    notes: str | None = None
    # Only meaningful for activity_type == "sent" — lets a genuinely time-sensitive touch use the
    # Thursday send-window slot that's otherwise excluded. Ignored for a logged response.
    urgent: bool = False
    # Set when this activity is logging an approved Phase B Draft being sent — links the two rows
    # and marks the draft "sent". Omitted for manual free-text logging.
    draft_id: uuid.UUID | None = None

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: str) -> str:
        if v not in OUTREACH_CHANNELS:
            raise ValueError(f"channel must be one of {OUTREACH_CHANNELS}")
        return v

    @field_validator("activity_type")
    @classmethod
    def validate_activity_type(cls, v: str) -> str:
        if v not in ACTIVITY_TYPES:
            raise ValueError(f"activity_type must be one of {ACTIVITY_TYPES}")
        return v


class OutreachActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contact_id: uuid.UUID
    draft_id: uuid.UUID | None
    channel: str
    activity_type: str
    template_variant: str | None
    notes: str | None
    occurred_at: datetime
    created_at: datetime


class LogOutreachActivityResponse(BaseModel):
    activity: OutreachActivityOut
    contact: ContactOut
