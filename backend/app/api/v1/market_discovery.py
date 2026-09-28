import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.ai_recommendation.gemini_client import GeminiClientError
from app.modules.companies.service import list_company_ids_by_source_run
from app.modules.ingestion.market_discovery import (
    confirm_market_discovery,
    get_default_market_description_parser,
    get_market_discovery_run,
    start_market_discovery_parse,
)
from app.modules.ingestion.schemas import (
    MarketDiscoveryConfirmRequest,
    MarketDiscoveryParsed,
    MarketDiscoveryParseRequest,
    MarketDiscoveryRunOut,
    MarketDiscoveryStarted,
)
from app.modules.jobs.service import enqueue_job
from app.modules.orchestrator.service import JOB_TYPE_AUTO_PIPELINE
from app.modules.products.service import list_products
from app.modules.qualification.service import JOB_TYPE_BULK_QUALIFY

router = APIRouter(prefix="/market-discovery", tags=["market-discovery"])


@router.post("/parse", response_model=MarketDiscoveryParsed)
async def parse_market_discovery_endpoint(
    body: MarketDiscoveryParseRequest, session: AsyncSession = Depends(get_db)
) -> MarketDiscoveryParsed:
    parser = get_default_market_description_parser()
    try:
        run = await start_market_discovery_parse(
            session, DEFAULT_ORGANIZATION_ID, body.raw_input, parser
        )
    except GeminiClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    await session.commit()
    return MarketDiscoveryParsed(ingestion_run_id=run.id, parsed_fields=run.parsed_fields or {})


@router.post("/{run_id}/confirm", response_model=MarketDiscoveryStarted, status_code=202)
async def confirm_market_discovery_endpoint(
    run_id: uuid.UUID,
    body: MarketDiscoveryConfirmRequest,
    session: AsyncSession = Depends(get_db),
) -> MarketDiscoveryStarted:
    run = await confirm_market_discovery(
        session,
        DEFAULT_ORGANIZATION_ID,
        run_id,
        industry_keywords=body.industry_keywords,
        location=body.location,
        employee_size_range=body.employee_size_range,
    )
    if run is None:
        raise HTTPException(status_code=404, detail="market discovery run not found")

    # Confirming is the one remaining manual gate before the One-Prompt Pipeline: from here,
    # discovery, qualification, role classification, and (when a product is known) drafting all
    # run automatically as a single auto_pipeline job.
    product_id = body.product_id
    if product_id is None:
        products, total = await list_products(session, DEFAULT_ORGANIZATION_ID, limit=2)
        if total == 1:
            product_id = products[0].id  # unambiguous default; >1 or 0 leaves drafting skipped

    job = await enqueue_job(
        session,
        DEFAULT_ORGANIZATION_ID,
        JOB_TYPE_AUTO_PIPELINE,
        {
            "ingestion_run_id": str(run.id),
            "product_id": str(product_id) if product_id else None,
        },
    )
    await session.commit()
    return MarketDiscoveryStarted(job_id=job.id)


@router.post(
    "/{run_id}/qualify-companies", response_model=MarketDiscoveryStarted, status_code=202
)
async def qualify_run_companies_endpoint(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> MarketDiscoveryStarted:
    run = await get_market_discovery_run(session, DEFAULT_ORGANIZATION_ID, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="market discovery run not found")
    company_ids = await list_company_ids_by_source_run(session, DEFAULT_ORGANIZATION_ID, run_id)
    if not company_ids:
        raise HTTPException(
            status_code=422, detail="this run has no newly-created companies to qualify"
        )
    job = await enqueue_job(
        session,
        DEFAULT_ORGANIZATION_ID,
        JOB_TYPE_BULK_QUALIFY,
        {"company_ids": [str(cid) for cid in company_ids]},
    )
    await session.commit()
    return MarketDiscoveryStarted(job_id=job.id)


@router.get("/{run_id}", response_model=MarketDiscoveryRunOut)
async def get_market_discovery_run_endpoint(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> MarketDiscoveryRunOut:
    run = await get_market_discovery_run(session, DEFAULT_ORGANIZATION_ID, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="market discovery run not found")
    return MarketDiscoveryRunOut.model_validate(run)
