import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.modules.contacts.models import FOLLOW_UP_CHANNELS, TRACKING_STATUSES


class ContactChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel_type: str
    value: str
    verification_status: str


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str | None
    role_title: str | None
    status: str
    next_follow_up_at: datetime | None
    next_follow_up_channel: str | None
    timezone: str | None
    needs_review: bool
    needs_review_reason: str | None
    channels: list[ContactChannelOut]


class ContactTrackingUpdate(BaseModel):
    status: str | None = None
    next_follow_up_at: datetime | None = None
    next_follow_up_channel: str | None = None
    timezone: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in TRACKING_STATUSES:
            raise ValueError(f"status must be one of {TRACKING_STATUSES}")
        return v

    @field_validator("next_follow_up_channel")
    @classmethod
    def validate_channel(cls, v: str | None) -> str | None:
        if v is not None and v not in FOLLOW_UP_CHANNELS:
            raise ValueError(f"next_follow_up_channel must be one of {FOLLOW_UP_CHANNELS}")
        return v


class CompanySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    domain: str | None


class FollowUpItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str | None
    role_title: str | None
    status: str
    next_follow_up_at: datetime | None
    next_follow_up_channel: str | None
    company: CompanySummary
