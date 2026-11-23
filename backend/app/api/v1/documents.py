import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.documents import cards, retrieval, service
from app.modules.documents.embedding import embeddings_available
from app.modules.documents.reading import DocumentReadError
from app.modules.documents.schemas import (
    CardUpdate,
    DocumentDetail,
    DocumentOut,
    DocumentPages,
    DocumentsStatus,
    DocumentUpdate,
    KnowledgeCardOut,
    OfferingRef,
    SearchHitOut,
    SearchOut,
)

# Open even while documents are switched off, so the screen can say so instead of failing.
status_router = APIRouter(prefix="/documents", tags=["documents"])


@status_router.get("/status", response_model=DocumentsStatus)
async def documents_status() -> DocumentsStatus:
    settings = get_settings()
    return DocumentsStatus(
        enabled=settings.documents_enabled,
        max_upload_mb=settings.documents_max_upload_mb,
        accepted_extensions=service.ACCEPTED_EXTENSIONS,
        vision_enabled=settings.documents_vision_enabled and bool(settings.gemini_api_key),
        meaning_search_enabled=embeddings_available(settings),
        cards_enabled=service.cards_available(settings),
    )


def _require_enabled() -> None:
    if not get_settings().documents_enabled:
        raise HTTPException(status_code=404, detail="Documents are not switched on.")


router = APIRouter(
    prefix="/documents", tags=["documents"], dependencies=[Depends(_require_enabled)]
)


async def _read_upload(file: UploadFile) -> tuple[str, bytes]:
    """The file's bytes, refusing early (without holding it all in memory) when it is too big."""
    filename = file.filename or ""
    if not filename:
        raise HTTPException(status_code=400, detail="The file has no name.")
    limit = get_settings().documents_max_upload_mb * 1024 * 1024
    data = bytearray()
    while chunk := await file.read(1024 * 1024):
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(
                status_code=413,
                detail=f"This file is larger than the {limit // (1024 * 1024)} MB limit.",
            )
    return filename, bytes(data)


def _refusal(exc: Exception) -> HTTPException:
    if isinstance(exc, service.DuplicateDocumentError):
        return HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "document_id": str(exc.document_id),
                "name": exc.name,
                "version": exc.version,
            },
        )
    if isinstance(exc, service.DocumentNotFoundError):
        return HTTPException(status_code=404, detail="Document not found.")
    if isinstance(exc, service.CardNotFoundError):
        return HTTPException(status_code=404, detail="Card not found.")
    if isinstance(exc, service.CannotReprocessError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


_REFUSALS = (
    DocumentReadError,
    service.DuplicateDocumentError,
    service.DocumentNotFoundError,
    service.CannotReprocessError,
    service.UnknownOfferingError,
    service.CardNotFoundError,
)


@router.post("", response_model=DocumentDetail, status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    product_ids: list[uuid.UUID] = Form(default_factory=list),
    # False: do not describe pictures for this file. Unset follows the setting.
    describe_pictures: bool | None = Form(default=None),
    session: AsyncSession = Depends(get_db),
) -> DocumentDetail:
    filename, data = await _read_upload(file)
    try:
        created = await service.create_document(
            session,
            DEFAULT_ORGANIZATION_ID,
            filename=filename,
            data=data,
            name=name,
            product_ids=product_ids,
            describe_pictures=describe_pictures,
        )
    except _REFUSALS as exc:
        raise _refusal(exc) from exc
    await session.commit()
    return created


@router.get("", response_model=list[DocumentOut])
async def list_documents(session: AsyncSession = Depends(get_db)) -> list[DocumentOut]:
    return await service.list_documents(session, DEFAULT_ORGANIZATION_ID)


# Declared before "/{document_id}" so "search" is not read as an id.
@router.get("/search", response_model=SearchOut)
async def search_documents(
    q: str = Query(..., max_length=2000, description="A question or some words"),
    product_id: list[uuid.UUID] = Query(default_factory=list),
    limit: int = Query(8, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
) -> SearchOut:
    """Passages that answer the question, from the current version of each document, found by
    meaning and by words and merged. Falls back to words alone (and says so) when meaning search
    is off or unavailable."""
    try:
        outcome = await retrieval.search(
            session, DEFAULT_ORGANIZATION_ID, q, product_ids=product_id, limit=limit
        )
    except retrieval.EmptyQuestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()  # the question's embedding call is recorded in the usage log
    return SearchOut(
        question=" ".join(q.split())[: retrieval.MAX_QUESTION_CHARS],
        mode=outcome.mode,
        note=outcome.note,
        indexed_passages=outcome.indexed,
        total_passages=outcome.total,
        hits=[
            SearchHitOut(
                chunk_id=h.chunk_id,
                document_id=h.document_id,
                document_name=h.document_name,
                version=h.version,
                locator=h.locator,
                heading_path=h.heading_path,
                text=h.text,
                offerings=[OfferingRef(id=i, name=n) for i, n in h.offerings],
                score=round(h.score, 5),
                similarity=None if h.similarity is None else round(h.similarity, 4),
                word_match=h.word_match,
                about_offering=h.about_offering,
            )
            for h in outcome.hits
        ],
    )


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> DocumentDetail:
    try:
        return await service.get_document(session, DEFAULT_ORGANIZATION_ID, document_id)
    except _REFUSALS as exc:
        raise _refusal(exc) from exc


@router.get("/{document_id}/pages", response_model=DocumentPages)
async def get_document_pages(
    document_id: uuid.UUID,
    version: int | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
) -> DocumentPages:
    try:
        return await service.get_pages(
            session,
            DEFAULT_ORGANIZATION_ID,
            document_id,
            version=version,
            limit=min(max(limit, 1), 200),
            offset=max(offset, 0),
        )
    except _REFUSALS as exc:
        raise _refusal(exc) from exc


@router.patch("/{document_id}", response_model=DocumentDetail)
async def update_document(
    document_id: uuid.UUID, body: DocumentUpdate, session: AsyncSession = Depends(get_db)
) -> DocumentDetail:
    try:
        updated = await service.update_document(
            session,
            DEFAULT_ORGANIZATION_ID,
            document_id,
            name=body.name,
            product_ids=body.product_ids,
        )
    except _REFUSALS as exc:
        raise _refusal(exc) from exc
    await session.commit()
    return updated


@router.post("/{document_id}/versions", response_model=DocumentDetail, status_code=202)
async def upload_new_version(
    document_id: uuid.UUID,
    file: UploadFile = File(...),
    describe_pictures: bool | None = Form(default=None),
    session: AsyncSession = Depends(get_db),
) -> DocumentDetail:
    filename, data = await _read_upload(file)
    try:
        created = await service.add_version(
            session,
            DEFAULT_ORGANIZATION_ID,
            document_id,
            filename=filename,
            data=data,
            describe_pictures=describe_pictures,
        )
    except _REFUSALS as exc:
        raise _refusal(exc) from exc
    await session.commit()
    return created


@router.post("/{document_id}/reprocess", response_model=DocumentDetail, status_code=202)
async def reprocess_document(
    document_id: uuid.UUID,
    describe_pictures: bool = True,
    session: AsyncSession = Depends(get_db),
) -> DocumentDetail:
    try:
        queued = await service.reprocess(
            session, DEFAULT_ORGANIZATION_ID, document_id, describe_pictures=describe_pictures
        )
    except _REFUSALS as exc:
        raise _refusal(exc) from exc
    await session.commit()
    return queued


@router.post("/{document_id}/summarise", response_model=DocumentDetail, status_code=202)
async def summarise_document(
    document_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> DocumentDetail:
    """Writes the summary and knowledge cards of the version in use again, in the background."""
    try:
        job = await cards.summarise_again(session, DEFAULT_ORGANIZATION_ID, document_id)
        detail = await service.get_document(session, DEFAULT_ORGANIZATION_ID, document_id)
    except _REFUSALS as exc:
        raise _refusal(exc) from exc
    await session.commit()
    detail.job_id = job.id
    return detail


@router.patch("/{document_id}/cards/{card_id}", response_model=KnowledgeCardOut)
async def update_card(
    document_id: uuid.UUID,
    card_id: uuid.UUID,
    body: CardUpdate,
    session: AsyncSession = Depends(get_db),
) -> KnowledgeCardOut:
    """Hides a wrong card from every flow, or shows it again."""
    try:
        updated = await service.set_card_hidden(
            session, DEFAULT_ORGANIZATION_ID, document_id, card_id, body.hidden
        )
    except _REFUSALS as exc:
        raise _refusal(exc) from exc
    await session.commit()
    return updated


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: uuid.UUID, session: AsyncSession = Depends(get_db)) -> None:
    try:
        await service.delete_document(session, DEFAULT_ORGANIZATION_ID, document_id)
    except _REFUSALS as exc:
        raise _refusal(exc) from exc
    await session.commit()
