"""The document library: uploading, adding a new version, listing, renaming, tying to offerings,
deleting. Reading the file happens later, in the background job (`ingest.py`).

No original file is kept. The bytes of an upload sit in a staging row (`DocumentUpload`) only until
the job has read them; everything the file said is stored as text."""

import hashlib
import re
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.modules.documents.chunking import ChunkConfig
from app.modules.documents.detect import detect_media_type
from app.modules.documents.models import (
    AUDIT_CARD_HIDDEN,
    AUDIT_CARD_SHOWN,
    AUDIT_DELETED,
    AUDIT_NEW_VERSION,
    AUDIT_READ_AGAIN,
    AUDIT_RENAMED,
    AUDIT_UPLOADED,
    EVENT_OK,
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_QUEUED,
    STATUS_READY,
    SUMMARY_DOCUMENT,
    SUMMARY_SECTION,
    Document,
    DocumentAsset,
    DocumentAudit,
    DocumentChunk,
    DocumentIngestionEvent,
    DocumentOffering,
    DocumentPage,
    DocumentSummary,
    DocumentUpload,
    DocumentVersion,
    KnowledgeCard,
)
from app.modules.documents.reading import DocumentReadError, ReaderConfig
from app.modules.documents.schemas import (
    AssetCounts,
    AssetOut,
    DocumentDetail,
    DocumentOut,
    DocumentPages,
    EventOut,
    KnowledgeCardOut,
    OfferingRef,
    PageOut,
    SummaryOut,
    VersionOut,
)
from app.modules.jobs.models import Job
from app.modules.jobs.service import enqueue_job
from app.modules.products.models import Product
from app.modules.usage.context import current_user_id

JOB_TYPE_INGEST_DOCUMENT = "ingest_document"

ACCEPTED_EXTENSIONS = [".pdf", ".pptx", ".docx", ".md", ".markdown", ".txt"]


class DocumentNotFoundError(LookupError):
    """No such document (or it belongs to another organisation)."""


class DuplicateDocumentError(Exception):
    """The same bytes were uploaded before."""

    def __init__(self, document_id: uuid.UUID, name: str, version: int) -> None:
        self.document_id = document_id
        self.name = name
        self.version = version
        super().__init__(
            f'This exact file is already in the library as "{name}" (version {version}).'
        )


class UnknownOfferingError(ValueError):
    """An offering id that does not exist (or is another organisation's)."""


class CannotReprocessError(ValueError):
    """There is nothing to run again: the file is no longer held, or it is being read now."""


class CardNotFoundError(LookupError):
    """No such knowledge card in that document."""


def cards_available(settings: Settings) -> bool:
    """Documents are summarised and knowledge cards drawn from them (Phase 8e)."""
    return settings.documents_cards_enabled and bool(settings.gemini_api_key)


def reader_config(settings: Settings, *, collect_images: bool) -> ReaderConfig:
    return ReaderConfig(
        max_pages=settings.documents_max_pages,
        collect_images=collect_images,
        max_images=settings.documents_vision_max_images,
        min_px=settings.documents_vision_min_px,
        max_banner_ratio=settings.documents_vision_max_banner_ratio,
    )


def chunk_config(settings: Settings) -> ChunkConfig:
    return ChunkConfig(
        target=settings.documents_chunk_chars,
        max_whole=settings.documents_chunk_max_chars,
        overlap=settings.documents_chunk_overlap_chars,
    )


def display_name(name: str | None, filename: str) -> str:
    """What the library calls a file: the name the uploader gave, or the file name without its
    extension and with underscores read as spaces."""
    chosen = (name or "").strip()
    if not chosen:
        stem = re.sub(r"\.[A-Za-z0-9]{1,8}$", "", filename.strip())
        chosen = re.sub(r"[_\s]+", " ", stem).strip() or "Untitled document"
    return chosen[:255]


def _check_file(filename: str, data: bytes, settings: Settings) -> str:
    limit = settings.documents_max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise DocumentReadError(
            f"This file is larger than the {settings.documents_max_upload_mb} MB limit."
        )
    return detect_media_type(data, filename, settings.documents_max_unpacked_mb * 1024 * 1024)


async def _refuse_duplicate(session: AsyncSession, organization_id: uuid.UUID, digest: str) -> None:
    row = (
        await session.execute(
            select(Document.id, Document.name, DocumentVersion.version)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .where(
                DocumentVersion.organization_id == organization_id,
                DocumentVersion.content_hash == digest,
            )
        )
    ).first()
    if row is not None:
        raise DuplicateDocumentError(row[0], row[1], row[2])


async def _offerings(
    session: AsyncSession, organization_id: uuid.UUID, product_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    wanted = list(dict.fromkeys(product_ids))
    if not wanted:
        return []
    found = set(
        (
            await session.execute(
                select(Product.id).where(
                    Product.organization_id == organization_id, Product.id.in_(wanted)
                )
            )
        )
        .scalars()
        .all()
    )
    missing = [str(p) for p in wanted if p not in found]
    if missing:
        raise UnknownOfferingError("That offering does not exist.")
    return wanted


async def record_event(
    session: AsyncSession,
    version: DocumentVersion,
    step: str,
    message: str,
    status: str = EVENT_OK,
    duration_ms: int | None = None,
) -> None:
    session.add(
        DocumentIngestionEvent(
            document_id=version.document_id,
            version_id=version.id,
            step=step,
            status=status,
            message=message[:500],
            duration_ms=duration_ms,
            created_at=datetime.now(UTC),
        )
    )


async def record_audit(
    session: AsyncSession,
    organization_id: uuid.UUID,
    document: Document,
    action: str,
    detail: str | None = None,
) -> None:
    """One line in the library history. It is not tied to the document, so it outlives a delete."""
    session.add(
        DocumentAudit(
            organization_id=organization_id,
            document_id=document.id,
            document_name=document.name[:255],
            action=action,
            detail=detail[:500] if detail else None,
            user_id=current_user_id(),  # the signed-in person (Phase 9)
            created_at=datetime.now(UTC),
        )
    )


def _size(num: int) -> str:
    return f"{num / 1024:.0f} KB" if num < 1024 * 1024 else f"{num / (1024 * 1024):.1f} MB"


async def _queue_version(
    session: AsyncSession,
    organization_id: uuid.UUID,
    document: Document,
    number: int,
    *,
    filename: str,
    media_type: str,
    digest: str,
    data: bytes,
    describe_pictures: bool | None = None,
) -> tuple[DocumentVersion, Job]:
    version = DocumentVersion(
        organization_id=organization_id,
        document_id=document.id,
        version=number,
        original_filename=filename[:255],
        media_type=media_type,
        content_hash=digest,
        size_bytes=len(data),
        status=STATUS_QUEUED,
    )
    session.add(version)
    await session.flush()
    session.add(DocumentUpload(version_id=version.id, content=data, created_at=datetime.now(UTC)))
    await record_event(session, version, "upload", f"Uploaded {filename} ({_size(len(data))})")
    job = await enqueue_job(
        session,
        organization_id,
        JOB_TYPE_INGEST_DOCUMENT,
        {
            "document_id": str(document.id),
            "version_id": str(version.id),
            "describe_pictures": describe_pictures,
        },
    )
    await session.flush()
    return version, job


async def create_document(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    filename: str,
    data: bytes,
    name: str | None = None,
    product_ids: list[uuid.UUID] | None = None,
    describe_pictures: bool | None = None,
) -> DocumentDetail:
    """Adds a new document and queues it to be read. Raises `DocumentReadError` for a file that
    cannot be used, `DuplicateDocumentError` for one already in the library."""
    settings = get_settings()
    media_type = _check_file(filename, data, settings)
    digest = hashlib.sha256(data).hexdigest()
    await _refuse_duplicate(session, organization_id, digest)
    offering_ids = await _offerings(session, organization_id, product_ids or [])

    document = Document(
        organization_id=organization_id,
        name=display_name(name, filename),
        uploaded_by=current_user_id(),
    )
    session.add(document)
    await session.flush()
    _, job = await _queue_version(
        session,
        organization_id,
        document,
        1,
        filename=filename,
        media_type=media_type,
        digest=digest,
        data=data,
        describe_pictures=describe_pictures,
    )
    session.add_all(DocumentOffering(document_id=document.id, product_id=p) for p in offering_ids)
    await record_audit(session, organization_id, document, AUDIT_UPLOADED, f"Uploaded {filename}")
    await session.flush()
    out = await get_document(session, organization_id, document.id)
    out.job_id = job.id
    return out


async def add_version(
    session: AsyncSession,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    filename: str,
    data: bytes,
    describe_pictures: bool | None = None,
) -> DocumentDetail:
    """Uploads a changed file as the next version of a document. The old version keeps being used
    until the new one is read; then it is archived."""
    document = await _document(session, organization_id, document_id)
    settings = get_settings()
    media_type = _check_file(filename, data, settings)
    digest = hashlib.sha256(data).hexdigest()
    await _refuse_duplicate(session, organization_id, digest)
    newest = await session.scalar(
        select(func.max(DocumentVersion.version)).where(DocumentVersion.document_id == document_id)
    )
    _, job = await _queue_version(
        session,
        organization_id,
        document,
        (newest or 0) + 1,
        filename=filename,
        media_type=media_type,
        digest=digest,
        data=data,
        describe_pictures=describe_pictures,
    )
    document.updated_at = datetime.now(UTC)
    await record_audit(
        session,
        organization_id,
        document,
        AUDIT_NEW_VERSION,
        f"Uploaded {filename} as a new version",
    )
    out = await get_document(session, organization_id, document_id)
    out.job_id = job.id
    return out


async def reprocess(
    session: AsyncSession,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    describe_pictures: bool = True,
) -> DocumentDetail:
    """Runs the newest version again from the file still held (a failed read, or pictures that
    were not all described, for example after a quota ran out)."""
    document = await _document(session, organization_id, document_id)
    version = await _newest_version(session, organization_id, document_id)
    if version.status in (STATUS_QUEUED, STATUS_PROCESSING):
        raise CannotReprocessError("This document is being read right now.")
    held = await session.scalar(
        select(func.count())
        .select_from(DocumentUpload)
        .where(DocumentUpload.version_id == version.id)
    )
    if not held:
        raise CannotReprocessError(
            "The uploaded file is no longer held (files are kept for a short time only). "
            "Upload it again."
        )
    version.status = STATUS_QUEUED
    version.error = None
    await record_event(session, version, "upload", "Queued to be read again")
    await record_audit(session, organization_id, document, AUDIT_READ_AGAIN)
    job = await enqueue_job(
        session,
        organization_id,
        JOB_TYPE_INGEST_DOCUMENT,
        {
            "document_id": str(document_id),
            "version_id": str(version.id),
            "describe_pictures": describe_pictures,
        },
    )
    await session.flush()
    out = await get_document(session, organization_id, document_id)
    out.job_id = job.id
    return out


async def _document(
    session: AsyncSession, organization_id: uuid.UUID, document_id: uuid.UUID
) -> Document:
    document = await session.get(Document, document_id)
    if document is None or document.organization_id != organization_id:
        raise DocumentNotFoundError(f"document {document_id} not found")
    return document


async def _newest_version(
    session: AsyncSession, organization_id: uuid.UUID, document_id: uuid.UUID
) -> DocumentVersion:
    version = (
        await session.execute(
            select(DocumentVersion)
            .where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.organization_id == organization_id,
            )
            .order_by(DocumentVersion.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if version is None:
        raise DocumentNotFoundError(f"document {document_id} has no versions")
    return version


async def _summaries(
    session: AsyncSession, organization_id: uuid.UUID, documents: list[Document]
) -> list[DocumentOut]:
    if not documents:
        return []
    ids = [d.id for d in documents]
    versions: dict[uuid.UUID, list[DocumentVersion]] = defaultdict(list)
    for v in (
        await session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id.in_(ids))
            .order_by(DocumentVersion.version)
        )
    ).scalars():
        versions[v.document_id].append(v)

    offerings: dict[uuid.UUID, list[OfferingRef]] = defaultdict(list)
    for document_id, product_id, name in (
        await session.execute(
            select(DocumentOffering.document_id, Product.id, Product.name)
            .join(Product, Product.id == DocumentOffering.product_id)
            .where(DocumentOffering.document_id.in_(ids))
            .order_by(Product.name)
        )
    ).all():
        offerings[document_id].append(OfferingRef(id=product_id, name=name))

    newest_ids = [vs[-1].id for vs in versions.values()]
    # The summary and cards shown are those of the version in use, else of the newest one.
    shown_ids = [_shown(vs).id for vs in versions.values()]
    summaries: dict[uuid.UUID, str] = dict(
        (
            await session.execute(
                select(DocumentSummary.version_id, DocumentSummary.text).where(
                    DocumentSummary.version_id.in_(shown_ids),
                    DocumentSummary.scope == SUMMARY_DOCUMENT,
                )
            )
        )
        .tuples()
        .all()
    )
    card_counts: dict[uuid.UUID, int] = dict(
        (
            await session.execute(
                select(KnowledgeCard.version_id, func.count())
                .where(KnowledgeCard.version_id.in_(shown_ids), ~KnowledgeCard.hidden)
                .group_by(KnowledgeCard.version_id)
            )
        )
        .tuples()
        .all()
    )
    counts: dict[uuid.UUID, AssetCounts] = defaultdict(AssetCounts)
    for version_id, status, n in (
        await session.execute(
            select(DocumentAsset.version_id, DocumentAsset.status, func.count())
            .where(DocumentAsset.version_id.in_(newest_ids))
            .group_by(DocumentAsset.version_id, DocumentAsset.status)
        )
    ).all():
        setattr(counts[version_id], status, n)
    indexed: dict[uuid.UUID, int] = dict(
        (
            await session.execute(
                select(DocumentChunk.version_id, func.count())
                .where(
                    DocumentChunk.version_id.in_(newest_ids),
                    DocumentChunk.embedding.is_not(None),
                )
                .group_by(DocumentChunk.version_id)
            )
        )
        .tuples()
        .all()
    )
    held = set(
        (
            await session.execute(
                select(DocumentUpload.version_id).where(DocumentUpload.version_id.in_(newest_ids))
            )
        )
        .scalars()
        .all()
    )

    out: list[DocumentOut] = []
    for document in documents:
        vs = versions[document.id]
        newest = vs[-1]
        shown = _shown(vs)
        out.append(
            DocumentOut(
                id=document.id,
                name=document.name,
                original_filename=newest.original_filename,
                media_type=newest.media_type,
                size_bytes=newest.size_bytes,
                status=newest.status,
                error=newest.error,
                page_count=newest.page_count,
                chunk_count=newest.chunk_count,
                indexed_chunks=indexed.get(newest.id, 0),
                version=newest.version,
                version_count=len(vs),
                is_searchable=any(v.is_current for v in vs),
                offerings=offerings[document.id],
                assets=counts[newest.id],
                can_reprocess=newest.id in held and newest.status in (STATUS_FAILED, STATUS_READY),
                summary=summaries.get(shown.id),
                card_count=card_counts.get(shown.id, 0),
                created_at=document.created_at,
                updated_at=document.updated_at,
            )
        )
    return out


def _shown(versions: list[DocumentVersion]) -> DocumentVersion:
    """The version whose summary and cards are shown: the one in use, else the newest."""
    return next((v for v in versions if v.is_current), versions[-1])


async def list_documents(session: AsyncSession, organization_id: uuid.UUID) -> list[DocumentOut]:
    documents = list(
        (
            await session.execute(
                select(Document)
                .where(Document.organization_id == organization_id)
                .order_by(Document.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return await _summaries(session, organization_id, documents)


async def get_document(
    session: AsyncSession, organization_id: uuid.UUID, document_id: uuid.UUID
) -> DocumentDetail:
    document = await _document(session, organization_id, document_id)
    (summary,) = await _summaries(session, organization_id, [document])
    versions = (
        (
            await session.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document_id)
                .order_by(DocumentVersion.version.desc())
            )
        )
        .scalars()
        .all()
    )
    events = (
        (
            await session.execute(
                select(DocumentIngestionEvent)
                .where(DocumentIngestionEvent.document_id == document_id)
                .order_by(DocumentIngestionEvent.created_at.desc())
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    shown = _shown(list(reversed(versions)))
    written = list(
        (
            await session.execute(
                select(DocumentSummary)
                .where(DocumentSummary.version_id == shown.id)
                .order_by(DocumentSummary.scope, DocumentSummary.position)
            )
        )
        .scalars()
        .all()
    )
    overall = next((s for s in written if s.scope == SUMMARY_DOCUMENT), None)
    return DocumentDetail(
        **summary.model_dump(),
        versions=[VersionOut.model_validate(v) for v in versions],
        events=[EventOut.model_validate(e) for e in events],
        sections=[SummaryOut.model_validate(s) for s in written if s.scope == SUMMARY_SECTION],
        cards=await _cards(session, shown.id),
        summary_model=overall.model_used if overall else None,
        summary_prompt_version=overall.prompt_version if overall else None,
        summary_cost_usd=overall.est_cost_usd if overall else None,
        summarised_at=overall.created_at if overall else None,
        can_summarise=cards_available(get_settings())
        and shown.status == STATUS_READY
        and shown.chunk_count > 0,
    )


async def _cards(
    session: AsyncSession, version_id: uuid.UUID, card_id: uuid.UUID | None = None
) -> list[KnowledgeCardOut]:
    stmt = (
        select(KnowledgeCard, DocumentChunk.locator, Product.id, Product.name)
        .join(DocumentChunk, DocumentChunk.id == KnowledgeCard.chunk_id)
        .outerjoin(Product, Product.id == KnowledgeCard.product_id)
        .where(KnowledgeCard.version_id == version_id)
        .order_by(KnowledgeCard.position)
    )
    if card_id is not None:
        stmt = stmt.where(KnowledgeCard.id == card_id)
    return [
        KnowledgeCardOut(
            id=card.id,
            kind=card.kind,
            statement=card.statement,
            quote=card.quote,
            client=card.client,
            industry=card.industry,
            offering=OfferingRef(id=product_id, name=name) if product_id else None,
            confidence=card.confidence,
            hidden=card.hidden,
            locator=locator,
            chunk_id=card.chunk_id,
            model_used=card.model_used,
            prompt_version=card.prompt_version,
        )
        for card, locator, product_id, name in (await session.execute(stmt)).all()
    ]


async def set_card_hidden(
    session: AsyncSession,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    card_id: uuid.UUID,
    hidden: bool,
) -> KnowledgeCardOut:
    """Hides a wrong card from every flow (or shows it again). The card itself is never edited:
    its words stay the model's own. Recorded in the library history."""
    document = await _document(session, organization_id, document_id)
    card = await session.get(KnowledgeCard, card_id)
    if card is None or card.document_id != document_id:
        raise CardNotFoundError(f"card {card_id} is not in document {document_id}")
    if card.hidden != hidden:
        card.hidden = hidden
        await record_audit(
            session,
            organization_id,
            document,
            AUDIT_CARD_HIDDEN if hidden else AUDIT_CARD_SHOWN,
            card.statement,
        )
        await session.flush()
    (out,) = await _cards(session, card.version_id, card.id)
    return out


async def get_pages(
    session: AsyncSession,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    version: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> DocumentPages:
    """What was extracted from one version (the current one by default, else the newest), page by
    page, with the picture and table descriptions and who wrote them."""
    await _document(session, organization_id, document_id)
    stmt = select(DocumentVersion).where(DocumentVersion.document_id == document_id)
    if version is not None:
        stmt = stmt.where(DocumentVersion.version == version)
    else:
        stmt = stmt.order_by(DocumentVersion.is_current.desc(), DocumentVersion.version.desc())
    chosen = (await session.execute(stmt.limit(1))).scalar_one_or_none()
    if chosen is None:
        raise DocumentNotFoundError(f"document {document_id} has no such version")
    total = (
        await session.scalar(
            select(func.count())
            .select_from(DocumentPage)
            .where(DocumentPage.version_id == chosen.id)
        )
    ) or 0
    pages = (
        (
            await session.execute(
                select(DocumentPage)
                .where(DocumentPage.version_id == chosen.id)
                .order_by(DocumentPage.position)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    assets = (
        (
            await session.execute(
                select(DocumentAsset)
                .where(DocumentAsset.version_id == chosen.id)
                .order_by(DocumentAsset.position)
            )
        )
        .scalars()
        .all()
    )
    return DocumentPages(
        version=chosen.version,
        total=total,
        pages=[PageOut.model_validate(p) for p in pages],
        assets=[AssetOut.model_validate(a) for a in assets],
    )


async def update_document(
    session: AsyncSession,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    name: str | None = None,
    product_ids: list[uuid.UUID] | None = None,
) -> DocumentDetail:
    document = await _document(session, organization_id, document_id)
    if name is not None:
        old_name = document.name
        document.name = name.strip()[:255] or document.name
        if document.name != old_name:
            await record_audit(
                session, organization_id, document, AUDIT_RENAMED, f"Renamed from {old_name}"
            )
    if product_ids is not None:
        wanted = await _offerings(session, organization_id, product_ids)
        await session.execute(
            delete(DocumentOffering).where(DocumentOffering.document_id == document_id)
        )
        session.add_all(DocumentOffering(document_id=document_id, product_id=p) for p in wanted)
    document.updated_at = datetime.now(UTC)
    await session.flush()
    return await get_document(session, organization_id, document_id)


async def delete_document(
    session: AsyncSession, organization_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    """Removes the document with every version, page, passage and description. Cannot be undone."""
    document = await _document(session, organization_id, document_id)
    await record_audit(session, organization_id, document, AUDIT_DELETED)
    await session.delete(document)
    await session.flush()


async def purge_stale_uploads(session: AsyncSession, hours: int) -> int:
    """Drops staged files older than `hours` for versions that are not waiting or being read. A
    successful read deletes its own; what is left is a failed read or a partly described file,
    kept only so it can be run again for a day."""
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    idle = select(DocumentVersion.id).where(
        DocumentVersion.status.not_in([STATUS_QUEUED, STATUS_PROCESSING])
    )
    result = await session.execute(
        delete(DocumentUpload).where(
            DocumentUpload.created_at < cutoff, DocumentUpload.version_id.in_(idle)
        )
    )
    return int(getattr(result, "rowcount", 0) or 0)
