import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.ai_recommendation.gemini_client import GeminiClientError
from app.modules.enrichment.schemas import ScrapeJobStarted
from app.modules.jobs.service import enqueue_job
from app.modules.qualification.qualification_generator import GeminiQualificationGenerator
from app.modules.qualification.schemas import (
    AdhocQualificationCheckRequest,
    CriterionCreate,
    CriterionList,
    CriterionOut,
    CriterionUpdate,
    QualificationResultOut,
)
from app.modules.qualification.service import (
    JOB_TYPE_ADHOC_QUALIFY,
    CompanyNotFoundError,
    NoCriteriaConfiguredError,
    create_criterion,
    delete_criterion,
    get_criterion,
    list_criteria,
    list_qualification_results,
    run_qualification_check,
    update_criterion,
)

router = APIRouter(prefix="/qualification/criteria", tags=["qualification"])

# Mounted under the companies prefix for locality — a qualification result always belongs to a
# company, same reasoning as api/v1/recommendations.py.
company_router = APIRouter(prefix="/companies", tags=["qualification"])

# Ad hoc check — resolves/creates the Company itself, so it isn't nested under an existing
# company_id like company_router's routes.
check_router = APIRouter(prefix="/qualification", tags=["qualification"])


@router.post("", response_model=CriterionOut, status_code=201)
async def create_criterion_endpoint(
    body: CriterionCreate, session: AsyncSession = Depends(get_db)
) -> CriterionOut:
    criterion = await create_criterion(
        session,
        DEFAULT_ORGANIZATION_ID,
        name=body.name,
        description=body.description,
        is_disqualifying=body.is_disqualifying,
        is_active=body.is_active,
    )
    await session.commit()
    return CriterionOut.model_validate(criterion)


@router.get("", response_model=CriterionList)
async def list_criteria_endpoint(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> CriterionList:
    criteria, total = await list_criteria(session, DEFAULT_ORGANIZATION_ID, limit, offset)
    items = [CriterionOut.model_validate(c) for c in criteria]
    return CriterionList(items=items, total=total, limit=limit, offset=offset)


@router.get("/{criterion_id}", response_model=CriterionOut)
async def get_criterion_endpoint(
    criterion_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> CriterionOut:
    criterion = await get_criterion(session, DEFAULT_ORGANIZATION_ID, criterion_id)
    if criterion is None:
        raise HTTPException(status_code=404, detail="qualification criterion not found")
    return CriterionOut.model_validate(criterion)


@router.patch("/{criterion_id}", response_model=CriterionOut)
async def update_criterion_endpoint(
    criterion_id: uuid.UUID, body: CriterionUpdate, session: AsyncSession = Depends(get_db)
) -> CriterionOut:
    criterion = await update_criterion(
        session, DEFAULT_ORGANIZATION_ID, criterion_id, body.model_dump(exclude_unset=True)
    )
    if criterion is None:
        raise HTTPException(status_code=404, detail="qualification criterion not found")
    await session.commit()
    return CriterionOut.model_validate(criterion)


@router.delete("/{criterion_id}", status_code=204)
async def delete_criterion_endpoint(
    criterion_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> None:
    deleted = await delete_criterion(session, DEFAULT_ORGANIZATION_ID, criterion_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="qualification criterion not found")
    await session.commit()


@company_router.post(
    "/{company_id}/qualification-results", response_model=QualificationResultOut, status_code=201
)
async def run_qualification_check_endpoint(
    company_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> QualificationResultOut:
    generator = GeminiQualificationGenerator(get_settings())
    try:
        result = await run_qualification_check(
            session, DEFAULT_ORGANIZATION_ID, company_id, generator
        )
    except CompanyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NoCriteriaConfiguredError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GeminiClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    await session.commit()
    return QualificationResultOut.model_validate(result)


@company_router.get(
    "/{company_id}/qualification-results", response_model=list[QualificationResultOut]
)
async def list_qualification_results_endpoint(
    company_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> list[QualificationResultOut]:
    results = await list_qualification_results(session, DEFAULT_ORGANIZATION_ID, company_id)
    return [QualificationResultOut.model_validate(r) for r in results]


@check_router.post("/check", response_model=ScrapeJobStarted, status_code=202)
async def run_adhoc_check_endpoint(
    body: AdhocQualificationCheckRequest, session: AsyncSession = Depends(get_db)
) -> ScrapeJobStarted:
    """Enriches (scrapes) the resolved-or-created company before judging it — a brand-new
    company otherwise has nothing but a name/domain to judge against, which just produces
    could_not_determine on every criterion. That takes real time (a network fetch + an LLM call),
    so this runs as a background job like Market Discovery and per-company scrape do, rather than
    blocking the request."""
    job = await enqueue_job(
        session,
        DEFAULT_ORGANIZATION_ID,
        JOB_TYPE_ADHOC_QUALIFY,
        {"name": body.name, "domain": body.domain},
    )
    await session.commit()
    return ScrapeJobStarted(job_id=job.id)
