import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class CurrentOffering(BaseModel):
    """What the live offering says today, shown next to a proposed change."""

    name: str
    description: str | None
    kind: str


class ProposalOut(BaseModel):
    id: uuid.UUID
    change: str  # "new" | "changed" | "removed"
    status: str
    kind: str
    name: str
    description: str | None
    source_url: str
    product_id: uuid.UUID | None
    detected_at: datetime
    current: CurrentOffering | None = None
    # "site" | "extra" | "post"; blog-post finds are suggestions.
    origin: str = "site"
    # The start of the page the description came from, and anything in the description the page
    # does not back up, so a reviewer can check it on the spot.
    source_excerpt: str | None = None
    grounding_flags: list[str] | None = None
    # A live offering or another waiting proposal this may be the same thing as.
    possible_duplicate: str | None = None


class ProposalList(BaseModel):
    items: list[ProposalOut]
    total: int


class SyncStarted(BaseModel):
    job_id: uuid.UUID


class SyncStatus(BaseModel):
    running: bool
    job_id: uuid.UUID | None
    progress: dict[str, Any] | None
    last_checked_at: datetime | None
    last_result: dict[str, Any] | None
    last_error: str | None
    pending_count: int


class BulkDecisionRequest(BaseModel):
    proposal_ids: list[uuid.UUID]
    decision: Literal["approve", "reject"]


class BulkDecisionResult(BaseModel):
    decided: int
    not_found: int


class CoveragePage(BaseModel):
    url: str
    title: str | None
    lane: str
    verdict: str  # "offering" | "not_offering" | "failed"
    reason: str | None
    lastmod: datetime | None
    last_checked_at: datetime | None
    force_extract: bool


class CoverageMenuItem(BaseModel):
    group: str
    label: str
    url: str
    # "covered" | "judged_not_offering" | "unreadable" | "missing"
    status: str


class CoverageOut(BaseModel):
    summary: dict[str, int]
    pages: list[CoveragePage]
    # None until a sync has read the website menu.
    menu: list[CoverageMenuItem] | None
    menu_error: str | None


class CheckPageRequest(BaseModel):
    url: str
