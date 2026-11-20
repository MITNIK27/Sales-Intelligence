import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.documents import service
from app.modules.documents.reading import DocumentReadError
from app.modules.documents.schemas import (
    DocumentDetail,
    DocumentOut,
    DocumentPages,
    DocumentsStatus,
    DocumentUpdate,
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
    if isinstance(exc, service.CannotReprocessError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


_REFUSALS = (
    DocumentReadError,
    service.DuplicateDocumentError,
    service.DocumentNotFoundError,
    service.CannotReprocessError,
    service.UnknownOfferingError,
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


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: uuid.UUID, session: AsyncSession = Depends(get_db)) -> None:
    try:
        await service.delete_document(session, DEFAULT_ORGANIZATION_ID, document_id)
    except _REFUSALS as exc:
        raise _refusal(exc) from exc
    await session.commit()
