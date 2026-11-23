"""Turns saved passages into vectors, as a background job separate from reading the file.

Reading must never fail because a model quota ran out, so embedding is its own job: the text is
saved and searchable by words first, and vectors follow. The job is safe to repeat: it only does
passages that have no vector yet (or one from a different model), saves after every batch, and an
hourly check in the worker queues it again for anything left over, so a quota that ran out mends
itself and documents read before this was switched on are caught up."""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

from sqlalchemy import ColumnElement, and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.modules.ai_recommendation.gemini_client import (
    EmbeddingResult,
    GeminiClientError,
    GeminiRateLimitedError,
    embed_texts,
)
from app.modules.documents.models import (
    EMBEDDING_DIMENSIONS,
    EVENT_OK,
    EVENT_WARNING,
    STATUS_READY,
    DocumentChunk,
    DocumentVersion,
)
from app.modules.documents.service import record_event
from app.modules.jobs.models import STATUS_DONE, STATUS_PENDING, STATUS_RUNNING, Job
from app.modules.jobs.service import enqueue_job

logger = logging.getLogger(__name__)

ProgressCallback = Callable[..., Awaitable[None]]

JOB_TYPE_EMBED_DOCUMENT = "embed_document"

# After a failed attempt, do not queue another for the same version for this long, so a spent
# daily quota does not produce a failed job every hour.
_RETRY_AFTER = timedelta(hours=1)
_RATE_ATTEMPTS = 4  # tries per batch when a per-minute limit is hit


async def _pause(seconds: float) -> None:
    await asyncio.sleep(seconds)  # a function so a test can skip the wait


class Embedder(Protocol):
    async def embed(self, texts: list[str], task: Literal["document", "query"]) -> EmbeddingResult:
        """One vector per text, in order. Raises `GeminiClientError` when it cannot."""
        ...


class GeminiEmbedder:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def embed(self, texts: list[str], task: Literal["document", "query"]) -> EmbeddingResult:
        return await embed_texts(
            api_key=self._settings.gemini_api_key or "",
            model=self._settings.documents_embedding_model,
            texts=texts,
            task=task,
            dimensions=EMBEDDING_DIMENSIONS,
        )


def make_embedder(settings: Settings) -> Embedder:
    """The embedder in use. A function so a test can swap it for a fake."""
    return GeminiEmbedder(settings)


def embeddings_available(settings: Settings) -> bool:
    return settings.documents_embeddings_enabled and bool(settings.gemini_api_key)


def needs_vector(model: str) -> ColumnElement[bool]:
    return or_(
        DocumentChunk.embedding.is_(None),
        DocumentChunk.embedding_model.is_(None),
        DocumentChunk.embedding_model != model,
    )


async def _embed_batch(
    embedder: Embedder, texts: list[str], wait_seconds: float
) -> EmbeddingResult:
    """One batch. A per-minute limit is waited out and retried here, so a large document finishes
    in one job instead of failing and waiting for the next hourly check."""
    for attempt in range(1, _RATE_ATTEMPTS + 1):
        try:
            return await embedder.embed(texts, "document")
        except GeminiRateLimitedError:
            if attempt == _RATE_ATTEMPTS:
                raise
            logger.info("embedding limit reached, waiting %ss", wait_seconds)
            await _pause(wait_seconds)
    raise AssertionError("unreachable")


async def process_embed_document_job(
    session: AsyncSession, job: Job, progress: ProgressCallback
) -> dict[str, Any]:
    settings = get_settings()
    version_id = uuid.UUID(str((job.payload or {})["version_id"]))
    version = await session.get(DocumentVersion, version_id)
    if version is None:
        return {"skipped": "the document was deleted"}
    if not embeddings_available(settings):
        return {"skipped": "meaning search is switched off or has no Gemini key"}

    model = settings.documents_embedding_model
    pending = (
        await session.execute(
            select(DocumentChunk.id, DocumentChunk.text)
            .where(DocumentChunk.version_id == version_id, needs_vector(model))
            .order_by(DocumentChunk.ordinal)
        )
    ).all()
    if not pending:
        return {"embedded": 0, "left": 0}

    embedder = make_embedder(settings)
    batch_size = max(1, settings.documents_embedding_batch)
    done = 0
    total = len(pending)
    await progress(0, total, stage="embed", detail=f"Indexing {total} passages")
    try:
        for start in range(0, total, batch_size):
            batch = pending[start : start + batch_size]
            result = await _embed_batch(
                embedder,
                [text for _, text in batch],
                settings.documents_embedding_rate_wait_seconds,
            )
            for (chunk_id, _), vector in zip(batch, result.vectors, strict=True):
                await session.execute(
                    update(DocumentChunk)
                    .where(DocumentChunk.id == chunk_id)
                    .values(embedding=vector, embedding_model=result.model)
                )
            done += len(batch)
            await session.commit()  # what is done stays done if a later batch fails
            await progress(done, total, stage="embed", detail=f"Indexed {done} of {total}")
    except GeminiClientError as exc:
        await session.rollback()
        version = await session.get(DocumentVersion, version_id)
        if version is not None:
            await record_event(
                session,
                version,
                "embed",
                f"Indexed {done} of {total} passages; {total - done} left ({exc})",
                EVENT_WARNING,
            )
            await session.commit()
        raise
    await record_event(
        session, version, "embed", f"Indexed {done} passages for meaning search", EVENT_OK
    )
    await session.commit()
    return {"embedded": done, "left": 0}


async def queue_missing_embeddings(session: AsyncSession) -> int:
    """Queues an embed job for each current version that has passages without a vector, unless one
    is already waiting or running, or a recent attempt failed. Called by the worker every hour."""
    settings = get_settings()
    if not embeddings_available(settings):
        return 0
    versions = (
        await session.execute(
            select(DocumentVersion.id, DocumentVersion.organization_id)
            .join(DocumentChunk, DocumentChunk.version_id == DocumentVersion.id)
            .where(
                DocumentVersion.is_current,
                DocumentVersion.status == STATUS_READY,
                needs_vector(settings.documents_embedding_model),
            )
            .group_by(DocumentVersion.id, DocumentVersion.organization_id)
        )
    ).all()
    cutoff = datetime.now(UTC) - _RETRY_AFTER
    queued = 0
    for version_id, organization_id in versions:
        busy = await session.scalar(
            select(func.count())
            .select_from(Job)
            .where(
                Job.job_type == JOB_TYPE_EMBED_DOCUMENT,
                Job.payload["version_id"].as_string() == str(version_id),
                or_(
                    Job.status.in_([STATUS_PENDING, STATUS_RUNNING]),
                    and_(Job.status != STATUS_DONE, Job.created_at > cutoff),
                ),
            )
        )
        if busy:
            continue
        await enqueue_job(
            session, organization_id, JOB_TYPE_EMBED_DOCUMENT, {"version_id": str(version_id)}
        )
        queued += 1
    return queued


async def queue_embedding(
    session: AsyncSession, organization_id: uuid.UUID, version_id: uuid.UUID
) -> None:
    """Queue the vectors for a version that has just been read (does nothing while off)."""
    if embeddings_available(get_settings()):
        await enqueue_job(
            session, organization_id, JOB_TYPE_EMBED_DOCUMENT, {"version_id": str(version_id)}
        )
