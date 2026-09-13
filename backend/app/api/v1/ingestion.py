from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.ingestion.schemas import CsvIngestionStarted
from app.modules.ingestion.service import start_csv_ingestion

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/csv", response_model=CsvIngestionStarted, status_code=202)
async def upload_csv(
    file: UploadFile, session: AsyncSession = Depends(get_db)
) -> CsvIngestionStarted:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="only .csv files are accepted")

    raw_bytes = await file.read()
    try:
        raw_text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="file is not valid UTF-8 text") from exc

    run, job = await start_csv_ingestion(
        session, DEFAULT_ORGANIZATION_ID, file.filename, raw_text
    )
    await session.commit()
    return CsvIngestionStarted(ingestion_run_id=run.id, job_id=job.id)
