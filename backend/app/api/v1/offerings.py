import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.offerings.coverage import get_coverage, request_extraction
from app.modules.offerings.review import (
    approve_proposal,
    duplicate_hints,
    list_proposals,
    reject_proposal,
    start_sync,
    sync_status,
)
from app.modules.offerings.schemas import (
    BulkDecisionRequest,
    BulkDecisionResult,
    CheckPageRequest,
    CoverageOut,
    CurrentOffering,
    ProposalList,
    ProposalOut,
    SyncStarted,
    SyncStatus,
)

# Shares the /products prefix and must be mounted BEFORE the products router, or "/products/sync"
# would be read as a product id.
router = APIRouter(prefix="/products", tags=["offerings"])


def _to_out(proposal, product, duplicate: str | None = None) -> ProposalOut:  # noqa: ANN001
    return ProposalOut(
        id=proposal.id,
        change=proposal.change,
        status=proposal.status,
        kind=proposal.kind,
        name=proposal.name,
        description=proposal.description,
        source_url=proposal.source_url,
        product_id=proposal.product_id,
        detected_at=proposal.detected_at,
        origin=proposal.origin,
        source_excerpt=proposal.source_excerpt,
        grounding_flags=proposal.grounding_flags,
        possible_duplicate=duplicate,
        current=(
            CurrentOffering(name=product.name, description=product.description, kind=product.kind)
            if product is not None
            else None
        ),
    )


@router.post("/sync", response_model=SyncStarted, status_code=202)
async def start_sync_endpoint(session: AsyncSession = Depends(get_db)) -> SyncStarted:
    job = await start_sync(session, DEFAULT_ORGANIZATION_ID)
    await session.commit()
    return SyncStarted(job_id=job.id)


@router.get("/sync/status", response_model=SyncStatus)
async def sync_status_endpoint(session: AsyncSession = Depends(get_db)) -> SyncStatus:
    return SyncStatus(**await sync_status(session, DEFAULT_ORGANIZATION_ID))


@router.get("/coverage", response_model=CoverageOut)
async def coverage_endpoint(session: AsyncSession = Depends(get_db)) -> CoverageOut:
    return CoverageOut(**await get_coverage(session, DEFAULT_ORGANIZATION_ID))


@router.post("/coverage/check", response_model=SyncStarted, status_code=202)
async def check_page_endpoint(
    body: CheckPageRequest, session: AsyncSession = Depends(get_db)
) -> SyncStarted:
    """Treat this page as an offering: remember the request and queue a sync to read it."""
    url = body.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="enter a full web address starting with https://")
    await request_extraction(session, DEFAULT_ORGANIZATION_ID, url)
    job = await start_sync(session, DEFAULT_ORGANIZATION_ID)
    await session.commit()
    return SyncStarted(job_id=job.id)


@router.get("/proposals", response_model=ProposalList)
async def list_proposals_endpoint(
    status: str = Query("pending", pattern="^(pending|approved|rejected|all)$"),
    session: AsyncSession = Depends(get_db),
) -> ProposalList:
    rows = await list_proposals(
        session, DEFAULT_ORGANIZATION_ID, None if status == "all" else status
    )
    hints = await duplicate_hints(session, DEFAULT_ORGANIZATION_ID, [p for p, _ in rows])
    items = [_to_out(proposal, product, hints.get(proposal.id)) for proposal, product in rows]
    return ProposalList(items=items, total=len(items))


@router.post("/proposals/decide", response_model=BulkDecisionResult)
async def decide_proposals_endpoint(
    body: BulkDecisionRequest, session: AsyncSession = Depends(get_db)
) -> BulkDecisionResult:
    decide = approve_proposal if body.decision == "approve" else reject_proposal
    decided = not_found = 0
    for proposal_id in body.proposal_ids:
        if await decide(session, DEFAULT_ORGANIZATION_ID, proposal_id) is None:
            not_found += 1
        else:
            decided += 1
    await session.commit()
    return BulkDecisionResult(decided=decided, not_found=not_found)


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalOut)
async def approve_proposal_endpoint(
    proposal_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> ProposalOut:
    proposal = await approve_proposal(session, DEFAULT_ORGANIZATION_ID, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    await session.commit()
    return _to_out(proposal, None)


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalOut)
async def reject_proposal_endpoint(
    proposal_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> ProposalOut:
    proposal = await reject_proposal(session, DEFAULT_ORGANIZATION_ID, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    await session.commit()
    return _to_out(proposal, None)
