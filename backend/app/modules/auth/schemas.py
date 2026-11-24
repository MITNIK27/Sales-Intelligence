import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str | None
    role: str
    status: str
    last_sign_in_at: datetime | None
    invited_by: uuid.UUID | None
    created_at: datetime
    # False until the invited person signs in for the first time.
    has_signed_in: bool = False
    # The name (or email) of whoever invited them; empty for the first admin.
    invited_by_name: str | None = None


class MeOut(BaseModel):
    """Who is signed in and what they may do. `access` is "granted" with `user` and `actions`;
    "none" for a verified account with no invitation (`request_pending` says whether they asked);
    "disabled" for a switched-off account."""

    access: Literal["granted", "none", "disabled"]
    email: str
    name: str | None = None
    user: UserOut | None = None
    actions: list[str] = []
    request_pending: bool = False


class AccessRequestIn(BaseModel):
    message: str | None = Field(default=None, max_length=1000)


class AccessRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str | None
    message: str | None
    status: str
    requested_at: datetime
    decided_at: datetime | None


class AccessRequestResult(BaseModel):
    request: AccessRequestOut
    # True when they had already asked within the last 24 hours.
    already_waiting: bool


class InviteIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: str = "rep"


class UserUpdate(BaseModel):
    role: str | None = None
    status: str | None = None


class ApproveIn(BaseModel):
    role: str = "rep"


class PendingCount(BaseModel):
    pending: int
