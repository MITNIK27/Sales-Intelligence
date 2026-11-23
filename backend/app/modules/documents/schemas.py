import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OfferingRef(BaseModel):
    id: uuid.UUID
    name: str


class AssetCounts(BaseModel):
    described: int = 0
    skipped: int = 0
    failed: int = 0


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    original_filename: str
    media_type: str
    size_bytes: int
    status: str
    error: str | None
    page_count: int | None
    chunk_count: int
    is_current: bool
    created_at: datetime
    processed_at: datetime | None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step: str
    status: str
    message: str
    duration_ms: int | None
    created_at: datetime


class DocumentOut(BaseModel):
    """One row of the library: the document, with the state of its newest version."""

    id: uuid.UUID
    name: str
    original_filename: str
    media_type: str
    size_bytes: int
    status: str
    error: str | None
    page_count: int | None
    chunk_count: int
    # Passages of the newest version that have a vector (meaning search). Fewer than chunk_count
    # while they are being indexed, or when that is switched off.
    indexed_chunks: int
    version: int  # the newest version's number
    version_count: int
    # True once some version has been read and is the one search uses.
    is_searchable: bool
    offerings: list[OfferingRef]
    assets: AssetCounts
    # The uploaded file is still held (a failed read, or pictures that were not all described), so
    # processing can be run again without uploading it.
    can_reprocess: bool
    # Set on the response to an upload: the background job that is reading the file.
    job_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentOut):
    versions: list[VersionOut]
    events: list[EventOut]


class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    locator: str
    heading_path: str | None
    text: str


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    locator: str
    kind: str
    status: str
    description: str | None
    note: str | None
    provider: str | None
    model_used: str | None
    prompt_version: str | None
    est_cost_usd: float | None


class DocumentPages(BaseModel):
    version: int
    total: int
    pages: list[PageOut]
    assets: list[AssetOut]


class DocumentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    # None leaves the offerings as they are; a list (possibly empty) replaces them.
    product_ids: list[uuid.UUID] | None = None


class DocumentsStatus(BaseModel):
    enabled: bool
    max_upload_mb: int
    accepted_extensions: list[str]
    vision_enabled: bool
    # Passages are indexed by meaning as well as by words (needs the setting and a Gemini key).
    meaning_search_enabled: bool


class SearchHitOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    version: int
    locator: str
    heading_path: str | None
    text: str
    offerings: list[OfferingRef]
    score: float
    # Closeness to the question by meaning (0 to 1); None if it was found by words only.
    similarity: float | None
    word_match: bool
    about_offering: bool


class SearchOut(BaseModel):
    question: str
    mode: str  # meaning_and_words | words_only
    note: str | None
    indexed_passages: int
    total_passages: int
    hits: list[SearchHitOut]
