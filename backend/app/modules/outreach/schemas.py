import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.contacts.schemas import ContactOut
from app.modules.outreach.models import (
    ACTIVITY_RESPONSE_RECEIVED,
    ACTIVITY_TYPES,
    OUTREACH_CHANNELS,
    OUTREACH_OUTCOMES,
)

# A logged date may not be in the future (a little slack for clocks) or older than a year.
_CLOCK_SLACK = timedelta(minutes=5)
_MAX_AGE = timedelta(days=365)


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
    # When it was actually sent or heard back; omitted means now. Lets a rep log yesterday's send.
    occurred_at: datetime | None = None
    # What a reply said. Only for a logged response.
    outcome: str | None = None
    # For a reply that asks to wait ("not now", "out of office"): business days until the next
    # follow-up. Omitted uses a sensible default for that outcome.
    follow_up_in_business_days: int | None = Field(default=None, ge=1, le=60)

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        if v > now + _CLOCK_SLACK:
            raise ValueError("the date cannot be in the future")
        if v < now - _MAX_AGE:
            raise ValueError("the date cannot be more than a year ago")
        return v

    @field_validator("outcome")
    @classmethod
    def validate_outcome(cls, v: str | None) -> str | None:
        if v is not None and v not in OUTREACH_OUTCOMES:
            raise ValueError(f"outcome must be one of {OUTREACH_OUTCOMES}")
        return v

    @model_validator(mode="after")
    def outcome_belongs_to_a_response(self) -> "LogOutreachActivityRequest":
        if self.outcome is not None and self.activity_type != ACTIVITY_RESPONSE_RECEIVED:
            raise ValueError("an outcome can only be given for a response")
        return self

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


class SnoozeRequest(BaseModel):
    business_days: int = Field(ge=1, le=30)


class OutreachActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contact_id: uuid.UUID
    draft_id: uuid.UUID | None
    channel: str
    activity_type: str
    template_variant: str | None
    notes: str | None
    outcome: str | None
    occurred_at: datetime
    created_at: datetime


class LogOutreachActivityResponse(BaseModel):
    activity: OutreachActivityOut
    contact: ContactOut
