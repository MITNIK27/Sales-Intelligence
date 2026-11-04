import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.ai_recommendation.gemini_client import GeminiClientError
from app.modules.companies.models import Company
from app.modules.companies.service import split_company_input
from app.modules.enrichment.schemas import ScrapeJobStarted
from app.modules.jobs.service import enqueue_job
from app.modules.qualification.qualification_generator import GeminiQualificationGenerator
from app.modules.qualification.schemas import (
    AdhocQualificationCheckRequest,
    CompanyCriteriaUpdate,
    CompanyCriterionOut,
    QualificationResultOut,
)
from app.modules.qualification.service import (
    JOB_TYPE_ADHOC_QUALIFY,
    CompanyNotFoundError,
    NoCriteriaConfiguredError,
    build_run_criteria,
    clean_criteria,
    list_qualification_results,
    run_qualification_check,
)

# Mounted under the companies prefix for locality — a qualification result always belongs to a
# company, same reasoning as api/v1/recommendations.py.
company_router = APIRouter(prefix="/companies", tags=["qualification"])

# Ad hoc check — resolves/creates the Company itself, so it isn't nested under an existing
# company_id like company_router's routes.
check_router = APIRouter(prefix="/qualification", tags=["qualification"])


@company_router.get("/{company_id}/criteria", response_model=list[CompanyCriterionOut])
async def get_company_criteria_endpoint(
    company_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> list[dict[str, object]]:
    company = await session.get(Company, company_id)
    if company is None or company.organization_id != DEFAULT_ORGANIZATION_ID:
        raise HTTPException(status_code=404, detail="company not found")
    return company.criteria or []


@company_router.put("/{company_id}/criteria", response_model=list[CompanyCriterionOut])
async def set_company_criteria_endpoint(
    company_id: uuid.UUID,
    body: CompanyCriteriaUpdate,
    session: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    """Replaces the company's criteria: what the person wants to know about this company."""
    company = await session.get(Company, company_id)
    if company is None or company.organization_id != DEFAULT_ORGANIZATION_ID:
        raise HTTPException(status_code=404, detail="company not found")
    company.criteria = clean_criteria([c.model_dump() for c in body.criteria])
    await session.commit()
    return company.criteria


@company_router.post(
    "/{company_id}/qualification-results", response_model=QualificationResultOut, status_code=201
)
async def run_qualification_check_endpoint(
    company_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> QualificationResultOut:
    """An informational check of the company against its own criteria: an answer for each, never a
    Qualified or Not qualified label."""
    generator = GeminiQualificationGenerator(get_settings())
    company = await session.get(Company, company_id)
    if company is None or company.organization_id != DEFAULT_ORGANIZATION_ID:
        raise HTTPException(status_code=404, detail="company not found")
    criteria = build_run_criteria(DEFAULT_ORGANIZATION_ID, company.criteria)
    if not criteria:
        raise HTTPException(status_code=422, detail="Add at least one criterion to check.")
    try:
        result = await run_qualification_check(
            session,
            DEFAULT_ORGANIZATION_ID,
            company_id,
            generator,
            criteria,
            run_criterion_ids=frozenset(str(c.id) for c in criteria),
            informational=True,
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
    name, domain = body.name, body.domain
    if body.company and body.company.strip():
        name, domain = split_company_input(body.company)
    job = await enqueue_job(
        session,
        DEFAULT_ORGANIZATION_ID,
        JOB_TYPE_ADHOC_QUALIFY,
        {
            "name": name,
            "domain": domain,
            "focus": (body.focus or "").strip() or None,
            "product_ids": [str(p) for p in body.product_ids],
        },
    )
    await session.commit()
    return ScrapeJobStarted(job_id=job.id)
