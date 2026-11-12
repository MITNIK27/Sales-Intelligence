import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.companies.models import Company
from app.modules.companies.schemas import (
    CompanyBulkDismissRequest,
    CompanyBulkDismissResult,
    CompanyConfirmRequest,
    CompanyConfirmResult,
    CompanyDetail,
    CompanyDismissRequest,
    CompanyList,
    CompanyListItem,
)
from app.modules.companies.service import (
    confirm_company,
    dismiss_company,
    get_company_detail,
    list_companies,
    restore_company,
)
from app.modules.contacts.schemas import ContactOut, PersonCreate
from app.modules.contacts.service import PersonAlreadyListedError, add_person
from app.modules.draft.draft_generator import GeminiDraftGenerator
from app.modules.enrichment.providers.search_contacts import SerperContactSearchProvider
from app.modules.enrichment.providers.search_serper import SerperSearchProvider
from app.modules.enrichment.schemas import ScrapeJobStarted, SignalItem
from app.modules.enrichment.service import (
    list_company_signals,
    search_company_contacts,
    start_company_scrape,
)
from app.modules.orchestrator.service import classify_and_draft_company
from app.modules.role_relevance.role_relevance_generator import GeminiRoleRelevanceGenerator

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=CompanyList)
async def list_companies_endpoint(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    sort_by: Literal[
        "name", "created_at", "last_enriched_at", "enrichment_status", "qualification"
    ] = Query("name"),
    sort_dir: Literal["asc", "desc"] = Query("asc"),
    dismissed: Literal["hide", "include", "only"] = Query(
        "hide", description="companies marked not a fit: leave out, include, or show only those"
    ),
    session: AsyncSession = Depends(get_db),
) -> CompanyList:
    rows, total = await list_companies(
        session, DEFAULT_ORGANIZATION_ID, limit, offset, sort_by, sort_dir, dismissed
    )
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
            created_at=company.created_at,
            last_enriched_at=company.last_enriched_at,
            dismissed_at=company.dismissed_at,
            dismissed_reason=company.dismissed_reason,
        )
        for company, contact_count, qualification_verdict in rows
    ]
    return CompanyList(items=items, total=total, limit=limit, offset=offset)


@router.post("/dismiss", response_model=CompanyBulkDismissResult)
async def dismiss_companies_endpoint(
    body: CompanyBulkDismissRequest, session: AsyncSession = Depends(get_db)
) -> CompanyBulkDismissResult:
    """Mark several companies not a fit with one reason (for clearing a noisy run). All in one
    transaction; each company gets its own labelled decision."""
    dismissed = already = 0
    missing: list[uuid.UUID] = []
    for company_id in dict.fromkeys(body.company_ids):  # in order, each id once
        result = await dismiss_company(
            session, DEFAULT_ORGANIZATION_ID, company_id, body.reason, body.note
        )
        if result is None:
            missing.append(company_id)
        elif result[1]:
            dismissed += 1
        else:
            already += 1
    await session.commit()
    return CompanyBulkDismissResult(
        dismissed=dismissed, already_dismissed=already, not_found=missing
    )


@router.get("/{company_id}", response_model=CompanyDetail)
async def get_company_endpoint(
    company_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> CompanyDetail:
    company = await get_company_detail(session, DEFAULT_ORGANIZATION_ID, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="company not found")
    return CompanyDetail.model_validate(company)


@router.post("/{company_id}/dismiss", response_model=CompanyDetail)
async def dismiss_company_endpoint(
    company_id: uuid.UUID,
    body: CompanyDismissRequest,
    session: AsyncSession = Depends(get_db),
) -> CompanyDetail:
    """A rep saying this company is not a fit. It is hidden and skipped by automatic work, and
    can be brought back with `/restore`."""
    result = await dismiss_company(
        session, DEFAULT_ORGANIZATION_ID, company_id, body.reason, body.note
    )
    if result is None:
        raise HTTPException(status_code=404, detail="company not found")
    detail = CompanyDetail.model_validate(result[0])
    await session.commit()
    return detail


@router.post("/{company_id}/restore", response_model=CompanyDetail)
async def restore_company_endpoint(
    company_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> CompanyDetail:
    """Undo a \"not a fit\"."""
    result = await restore_company(session, DEFAULT_ORGANIZATION_ID, company_id)
    if result is None:
        raise HTTPException(status_code=404, detail="company not found")
    detail = CompanyDetail.model_validate(result[0])
    await session.commit()
    return detail


@router.post("/{company_id}/confirm", response_model=CompanyConfirmResult)
async def confirm_company_endpoint(
    company_id: uuid.UUID,
    body: CompanyConfirmRequest = CompanyConfirmRequest(),
    session: AsyncSession = Depends(get_db),
) -> CompanyConfirmResult:
    """A rep vouching for a company the pipeline flagged `needs_review` — this is the only way
    that flag is ever cleared, and clearing it is also what unblocks role classification and
    drafting for it, so this immediately resumes both rather than leaving the rep to trigger them
    separately."""
    company = await confirm_company(session, DEFAULT_ORGANIZATION_ID, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="company not found")

    settings = get_settings()
    resumed = await classify_and_draft_company(
        session,
        DEFAULT_ORGANIZATION_ID,
        company_id,
        GeminiRoleRelevanceGenerator(settings),
        GeminiDraftGenerator(settings),
        body.product_ids,
    )
    await session.commit()
    return CompanyConfirmResult(
        company=CompanyDetail.model_validate(company),
        role_classification=resumed["role_classification"],
        drafting=resumed["drafting"],
    )


@router.post("/{company_id}/scrape", response_model=ScrapeJobStarted, status_code=202)
async def scrape_company_endpoint(
    company_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> ScrapeJobStarted:
    job = await start_company_scrape(session, DEFAULT_ORGANIZATION_ID, company_id)
    if job is None:
        raise HTTPException(status_code=404, detail="company not found")
    await session.commit()
    return ScrapeJobStarted(job_id=job.id)


@router.post("/{company_id}/contacts", response_model=ContactOut, status_code=201)
async def add_person_endpoint(
    company_id: uuid.UUID, payload: PersonCreate, session: AsyncSession = Depends(get_db)
) -> ContactOut:
    """A rep adds a person they know, for when the people search finds no one useful."""
    company = await session.get(Company, company_id)
    if company is None or company.organization_id != DEFAULT_ORGANIZATION_ID:
        raise HTTPException(status_code=404, detail="company not found")
    try:
        contact = await add_person(
            session,
            DEFAULT_ORGANIZATION_ID,
            company_id,
            payload.full_name,
            payload.role_title,
            payload.linkedin_url,
            payload.email,
        )
    except PersonAlreadyListedError as exc:
        raise HTTPException(
            status_code=409, detail=f"{payload.full_name} is already listed for this company"
        ) from exc
    await session.commit()
    await session.refresh(contact, attribute_names=["channels"])
    return ContactOut.model_validate(contact)


@router.post("/{company_id}/search-contacts", response_model=list[ContactOut])
async def search_company_contacts_endpoint(
    company_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> list[ContactOut]:
    settings = get_settings()
    domain_provider = SerperSearchProvider(settings)
    provider = SerperContactSearchProvider(settings, domain_provider)
    contacts = await search_company_contacts(session, DEFAULT_ORGANIZATION_ID, company_id, provider)
    if contacts is None:
        raise HTTPException(status_code=404, detail="company not found")
    await session.commit()
    return [ContactOut.model_validate(c) for c in contacts]


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
            summary=record.raw_payload.get("summary"),
            provider=record.raw_payload.get("provider"),
        )
        for record in records
    ]
