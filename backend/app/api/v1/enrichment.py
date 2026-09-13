from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.enrichment.schemas import NeedsReviewItem, ScrapeAllStarted
from app.modules.enrichment.service import list_needs_review, start_bulk_scrape

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
