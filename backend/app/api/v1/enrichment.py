from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.enrichment.schemas import (
    BulkConfirmRequest,
    BulkConfirmStarted,
    NeedsReviewItem,
    ScrapeAllStarted,
)
from app.modules.enrichment.service import list_needs_review, start_bulk_scrape
from app.modules.jobs.service import enqueue_job
from app.modules.orchestrator.service import JOB_TYPE_BULK_CONFIRM

router = APIRouter(prefix="/enrichment", tags=["enrichment"])


@router.post("/scrape-all", response_model=ScrapeAllStarted, status_code=202)
async def scrape_all_endpoint(session: AsyncSession = Depends(get_db)) -> ScrapeAllStarted:
    enqueued_count = await start_bulk_scrape(session, DEFAULT_ORGANIZATION_ID)
    await session.commit()
    return ScrapeAllStarted(enqueued_count=enqueued_count)


@router.get("/needs-review", response_model=list[NeedsReviewItem])
async def needs_review_endpoint(
    session: AsyncSession = Depends(get_db),
) -> list[NeedsReviewItem]:
    entries = await list_needs_review(session, DEFAULT_ORGANIZATION_ID)
    return [NeedsReviewItem.model_validate(e) for e in entries]


@router.post("/needs-review/confirm-bulk", response_model=BulkConfirmStarted, status_code=202)
async def confirm_needs_review_bulk_endpoint(
    body: BulkConfirmRequest, session: AsyncSession = Depends(get_db)
) -> BulkConfirmStarted:
    """Clears `needs_review` on every given company/contact in one job, instead of a rep clicking
    Confirm on each entry in the Needs Review queue individually — each confirmed company also
    resumes role classification/drafting exactly like confirming it one at a time would."""
    if not body.company_ids and not body.contact_ids:
        raise HTTPException(status_code=422, detail="no company_ids or contact_ids given")
    job = await enqueue_job(
        session,
        DEFAULT_ORGANIZATION_ID,
        JOB_TYPE_BULK_CONFIRM,
        {
            "company_ids": [str(cid) for cid in body.company_ids],
            "contact_ids": [str(cid) for cid in body.contact_ids],
            "product_id": str(body.product_id) if body.product_id else None,
        },
    )
    await session.commit()
    return BulkConfirmStarted(job_id=job.id)
