import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.companies.schemas import CompanyDetail, CompanyList, CompanyListItem
from app.modules.companies.service import get_company_detail, list_companies
from app.modules.enrichment.schemas import ScrapeJobStarted, SignalItem
from app.modules.enrichment.service import list_company_signals, start_company_scrape

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=CompanyList)
async def list_companies_endpoint(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> CompanyList:
    rows, total = await list_companies(session, DEFAULT_ORGANIZATION_ID, limit, offset)
    items = [
        CompanyListItem(
            id=company.id,
            name=company.name,
            domain=company.domain,
            industry=company.industry,
            contact_count=contact_count,
            enrichment_status=company.enrichment_status,
            needs_review=company.needs_review,
            qualification_verdict=qualification_verdict,
        )
        for company, contact_count, qualification_verdict in rows
    ]
    return CompanyList(items=items, total=total, limit=limit, offset=offset)


@router.get("/{company_id}", response_model=CompanyDetail)
async def get_company_endpoint(
    company_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> CompanyDetail:
    company = await get_company_detail(session, DEFAULT_ORGANIZATION_ID, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="company not found")
    return CompanyDetail.model_validate(company)


@router.post("/{company_id}/scrape", response_model=ScrapeJobStarted, status_code=202)
async def scrape_company_endpoint(
    company_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> ScrapeJobStarted:
    job = await start_company_scrape(session, DEFAULT_ORGANIZATION_ID, company_id)
    if job is None:
        raise HTTPException(status_code=404, detail="company not found")
    await session.commit()
    return ScrapeJobStarted(job_id=job.id)


@router.get("/{company_id}/signals", response_model=list[SignalItem])
async def list_company_signals_endpoint(
    company_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> list[SignalItem]:
    records = await list_company_signals(session, DEFAULT_ORGANIZATION_ID, company_id)
    return [
        SignalItem(
            signal_type=record.raw_payload.get("signal_type", ""),
            text=record.raw_payload.get("text", ""),
            url=record.raw_payload.get("url", ""),
            date=record.raw_payload.get("date"),
            fetched_at=record.fetched_at,
        )
        for record in records
    ]
