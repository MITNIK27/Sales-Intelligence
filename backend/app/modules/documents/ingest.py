"""The background job that reads an uploaded file: parse, describe pictures (optional), cut into
passages, save, and swap the new version in as the one search uses.

Safe to run twice (a requeued job, or "read again"): it replaces whatever an earlier run saved for
the version. A failure is saved on the version with a message for the uploader, and the uploaded
file stays held (for a short time) so it can be run again. Parsing happens on a worker thread so
the loop stays responsive."""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.core.config import Settings, get_settings
from app.modules.documents.cards import queue_summary
from app.modules.documents.chunking import chunk_units
from app.modules.documents.embedding import queue_embedding
from app.modules.documents.models import (
    ASSET_DESCRIBED,
    ASSET_FAILED,
    ASSET_SKIPPED,
    EVENT_ERROR,
    EVENT_WARNING,
    MEDIA_PDF,
    MEDIA_PPTX,
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_READY,
    DocumentAsset,
    DocumentChunk,
    DocumentPage,
    DocumentSummary,
    DocumentUpload,
    DocumentVersion,
)
from app.modules.documents.parsers import read_document
from app.modules.documents.reading import (
    DocumentReadError,
    ParsedDocument,
    ParsedUnit,
    fill_placeholders,
)
from app.modules.documents.service import chunk_config, reader_config, record_event
from app.modules.documents.vision import (
    DescribeOutcome,
    GeminiImageDescriber,
    ImageDescriber,
    describe_images,
)
from app.modules.jobs.errors import friendly_error
from app.modules.jobs.models import Job

ProgressCallback = Callable[..., Awaitable[None]]


def make_describer(settings: Settings) -> ImageDescriber:
    """The picture describer in use. A function so a test can swap it for a fake."""
    return GeminiImageDescriber(settings)


def _unit_word(media_type: str) -> str:
    return {MEDIA_PDF: "page", MEDIA_PPTX: "slide"}.get(media_type, "section")


def _label(kind: str, text: str) -> str:
    """How a model's description appears inside the page text, so a reader can always tell which
    words were written by a model."""
    if kind == "image":
        return f"[IMAGE: {text}]"
    if kind == "table":
        return f"[TABLE: {text}]"
    return text  # a scanned page: the transcription is the page


def _millis(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


async def process_ingest_document_job(
    session: AsyncSession, job: Job, progress_callback: ProgressCallback
) -> dict[str, Any]:
    payload = job.payload or {}
    version_id = uuid.UUID(str(payload["version_id"]))
    version = await session.get(DocumentVersion, version_id)
    if version is None:
        raise LookupError("The document was deleted before it could be read.")
    if version.status == STATUS_READY:
        return {"version_id": str(version_id), "skipped": "already read"}

    upload = (
        await session.execute(
            select(DocumentUpload)
            .where(DocumentUpload.version_id == version_id)
            .options(undefer(DocumentUpload.content))
        )
    ).scalar_one_or_none()
    if upload is None:
        await _fail(session, version_id, "The uploaded file is no longer held. Upload it again.")
        raise DocumentReadError("The uploaded file is no longer held. Upload it again.")

    try:
        return await _run(
            session, version, upload, progress_callback, payload.get("describe_pictures")
        )
    except Exception as exc:
        await session.rollback()
        if (
            await session.scalar(select(DocumentVersion.id).where(DocumentVersion.id == version_id))
            is None
        ):
            # Deleted while it was being read: nothing to save, and nothing went wrong.
            return {"version_id": str(version_id), "skipped": "the document was deleted"}
        message = str(exc) if isinstance(exc, DocumentReadError) else friendly_error(exc)
        await _fail(session, version_id, message)
        raise


async def _fail(session: AsyncSession, version_id: uuid.UUID, message: str) -> None:
    version = await session.get(DocumentVersion, version_id)
    if version is None:
        return  # the document was deleted while it was being read
    version.status = STATUS_FAILED
    version.error = message[:500]
    version.processed_at = datetime.now(UTC)
    await record_event(session, version, "failed", message, EVENT_ERROR)
    await session.commit()


async def _run(
    session: AsyncSession,
    version: DocumentVersion,
    upload: DocumentUpload,
    progress: ProgressCallback,
    describe_pictures: bool | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    version_id, document_id = version.id, version.document_id
    organization_id = version.organization_id
    data = upload.content
    media_type = version.media_type

    version.status = STATUS_PROCESSING
    version.error = None
    await session.commit()

    # Allowed by the settings, and not declined for this upload.
    wanted = settings.documents_vision_enabled and describe_pictures is not False
    vision_on = wanted and bool(settings.gemini_api_key)
    if wanted and not vision_on:
        await record_event(
            session,
            version,
            "describe",
            "Image descriptions are switched on but no Gemini key is set, so pictures were not "
            "described.",
            EVENT_WARNING,
        )

    # 1. read
    await progress(0, 4, stage="read", detail=f"Reading {version.original_filename}")
    started = time.perf_counter()
    parsed = await asyncio.to_thread(
        read_document, media_type, data, reader_config(settings, collect_images=vision_on)
    )
    word = _unit_word(media_type)
    await record_event(
        session,
        version,
        "read",
        f"Read {len(parsed.units)} {word}{'' if len(parsed.units) == 1 else 's'} of text",
        duration_ms=_millis(started),
    )
    for note in parsed.notes:
        await record_event(session, version, "read", note, EVENT_WARNING)
    if not parsed.units and not parsed.images:
        raise DocumentReadError(_no_text_message(parsed))

    # 2. describe pictures (only when switched on and there are any)
    outcomes: list[DescribeOutcome] = []
    if parsed.images:
        await progress(1, 4, stage="describe", detail=f"Describing {len(parsed.images)} pictures")
        started = time.perf_counter()

        async def tick(done: int, total: int) -> None:
            await progress(1, 4, stage="describe", detail=f"Described {done} of {total} pictures")

        outcomes = await describe_images(
            parsed.images,
            make_describer(settings),
            settings.documents_vision_concurrency,
            on_done=tick,
        )
        described = sum(1 for o in outcomes if o.description)
        failed = len(outcomes) - described
        await record_event(
            session,
            version,
            "describe",
            f"Described {described} of {len(outcomes)} pictures"
            + (f"; {failed} could not be described" if failed else ""),
            EVENT_WARNING if failed else "ok",
            _millis(started),
        )

    # 3. assemble the pages and cut them into passages
    await progress(2, 4, stage="chunk", detail="Cutting the text into passages")
    replacements = {
        o.image.key: _label(o.image.kind, o.description.text) for o in outcomes if o.description
    }
    units = _filled_units(parsed.units, replacements)
    if not units:
        raise DocumentReadError(_no_text_message(parsed))
    chunks = chunk_units(units, chunk_config(settings))
    if len(chunks) > settings.documents_max_chunks:
        raise DocumentReadError(
            f"This file is too large to index: it would make {len(chunks)} passages and the "
            f"limit is {settings.documents_max_chunks}. Split it into smaller files."
        )

    # 4. save, and make this the version search uses
    await progress(3, 4, stage="save", detail="Saving")
    # Knowledge cards go with the passages they came from (the database cascades them).
    for model in (DocumentPage, DocumentChunk, DocumentAsset, DocumentSummary):
        await session.execute(delete(model).where(model.version_id == version_id))
    session.add_all(
        DocumentPage(
            document_id=document_id,
            version_id=version_id,
            position=unit.position,
            locator=unit.locator,
            heading_path=unit.heading_path,
            text=unit.text,
        )
        for unit in units
    )
    session.add_all(
        DocumentChunk(
            organization_id=organization_id,
            document_id=document_id,
            version_id=version_id,
            ordinal=c.ordinal,
            locator=c.locator,
            heading_path=c.heading_path,
            text=c.text,
            char_count=len(c.text),
        )
        for c in chunks
    )
    assets = _assets(organization_id, document_id, version_id, parsed, outcomes)
    session.add_all(assets)

    await session.execute(
        update(DocumentVersion)
        .where(DocumentVersion.document_id == document_id, DocumentVersion.is_current)
        .values(is_current=False)
    )
    version.is_current = True
    version.status = STATUS_READY
    version.error = None
    version.page_count = parsed.page_count
    version.chunk_count = len(chunks)
    version.processed_at = datetime.now(UTC)
    # The file is only kept while something is left to run again (a picture that failed).
    keep_file = any(a.status == ASSET_FAILED for a in assets)
    if not keep_file:
        await session.delete(upload)
    await record_event(
        session,
        version,
        "done",
        f"Ready: {len(chunks)} passages from {parsed.page_count} {word}"
        f"{'' if parsed.page_count == 1 else 's'}",
    )
    await queue_embedding(session, organization_id, version_id)
    await queue_summary(session, organization_id, version_id)
    await session.commit()
    if (
        await session.scalar(select(DocumentVersion.id).where(DocumentVersion.id == version_id))
        is None
    ):
        # Deleted while it was being read: what was saved went with it.
        return {"version_id": str(version_id), "skipped": "the document was deleted"}
    await progress(4, 4, stage="done", detail="Ready")
    return {
        "document_id": str(document_id),
        "version_id": str(version_id),
        "pages": len(units),
        "chunks": len(chunks),
        "pictures_described": sum(1 for a in assets if a.status == ASSET_DESCRIBED),
        "pictures_failed": sum(1 for a in assets if a.status == ASSET_FAILED),
    }


def _filled_units(units: list[ParsedUnit], replacements: dict[str, str]) -> list[ParsedUnit]:
    out: list[ParsedUnit] = []
    for unit in units:
        text = fill_placeholders(unit.text, replacements)
        if text:
            out.append(ParsedUnit(unit.position, unit.locator, text, unit.heading_path))
    return out


def _assets(
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    parsed: ParsedDocument,
    outcomes: list[DescribeOutcome],
) -> list[DocumentAsset]:
    now = datetime.now(UTC)
    rows: list[DocumentAsset] = []
    for outcome in outcomes:
        image, described = outcome.image, outcome.description
        rows.append(
            DocumentAsset(
                organization_id=organization_id,
                document_id=document_id,
                version_id=version_id,
                locator=image.locator,
                position=len(rows) + 1,
                kind=image.kind,
                status=ASSET_DESCRIBED if described else ASSET_FAILED,
                description=described.text if described else None,
                note=None if described else outcome.error,
                width=image.width,
                height=image.height,
                provider=described.provider if described else None,
                model_used=described.model if described else None,
                prompt_version=described.prompt_version if described else None,
                tokens_in=described.tokens_in if described else None,
                tokens_out=described.tokens_out if described else None,
                est_cost_usd=described.est_cost_usd if described else None,
                created_at=now,
            )
        )
    for skipped in parsed.skipped:
        rows.append(
            DocumentAsset(
                organization_id=organization_id,
                document_id=document_id,
                version_id=version_id,
                locator=skipped.locator,
                position=len(rows) + 1,
                kind=skipped.kind,
                status=ASSET_SKIPPED,
                note=skipped.note,
                width=skipped.width,
                height=skipped.height,
                created_at=now,
            )
        )
    return rows


def _no_text_message(parsed: ParsedDocument) -> str:
    if any(s.kind == "scanned_page" for s in parsed.skipped):
        return (
            "No readable text was found: this looks like a scan. Switch on image descriptions "
            "(DOCUMENTS_VISION_ENABLED=true with a Gemini key) and upload it again, or upload a "
            "version with selectable text."
        )
    return "No readable text was found in this file."
