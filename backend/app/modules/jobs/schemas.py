import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class JobStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_type: str
    status: str
    progress: dict[str, Any] | None
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
