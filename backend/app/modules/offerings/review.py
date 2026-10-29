"""The people side of the website sync: listing what it found, approving or rejecting each item,
and the status of the sync itself. Approving is the only place a website offering is created,
changed or archived."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.jobs.models import STATUS_DONE, STATUS_PENDING, STATUS_RUNNING, Job
from app.modules.jobs.service import enqueue_job
from app.modules.offerings.models import (
    CHANGE_CHANGED,
    CHANGE_NEW,
    CHANGE_REMOVED,
    PROPOSAL_APPROVED,
    PROPOSAL_PENDING,
    PROPOSAL_REJECTED,
    OfferingProposal,
)
from app.modules.offerings.names import names_match
from app.modules.offerings.service import JOB_TYPE_SYNC_OFFERINGS
from app.modules.products.models import SOURCE_WEBSITE, STATUS_ACTIVE, STATUS_ARCHIVED, Product


async def list_proposals(
    session: AsyncSession, organization_id: uuid.UUID, status: str | None = PROPOSAL_PENDING
) -> list[tuple[OfferingProposal, Product | None]]:
    """Each proposal with the live offering it would change (if any), so the screen can show
    before and after."""
    stmt = select(OfferingProposal).where(OfferingProposal.organization_id == organization_id)
    if status is not None:
        stmt = stmt.where(OfferingProposal.status == status)
    stmt = stmt.order_by(OfferingProposal.kind.desc(), OfferingProposal.name)
    proposals = (await session.execute(stmt)).scalars().all()
    product_ids = {p.product_id for p in proposals if p.product_id is not None}
    products = {}
    if product_ids:
        rows = await session.execute(select(Product).where(Product.id.in_(product_ids)))
        products = {p.id: p for p in rows.scalars()}
    return [(p, products.get(p.product_id) if p.product_id else None) for p in proposals]


async def duplicate_hints(
    session: AsyncSession,
    organization_id: uuid.UUID,
    proposals: list[OfferingProposal],
) -> dict[uuid.UUID, str]:
    """For each waiting "new" proposal, the name of a live offering or another waiting proposal
    it may be the same thing as (the same product reached by two addresses, for example), so a
    person approves one and skips the other."""
    live = (
        await session.execute(
            select(Product.name).where(
                Product.organization_id == organization_id, Product.status == STATUS_ACTIVE
            )
        )
    ).scalars().all()
    hints: dict[uuid.UUID, str] = {}
    waiting = [p for p in proposals if p.change == CHANGE_NEW and p.status == PROPOSAL_PENDING]
    for proposal in waiting:
        match = next((n for n in live if names_match(proposal.name, n)), None)
        if match is None:
            match = next(
                (
                    other.name
                    for other in waiting
                    if other.id != proposal.id and names_match(proposal.name, other.name)
                ),
                None,
            )
        if match is not None:
            hints[proposal.id] = match
    return hints


async def count_pending(session: AsyncSession, organization_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(OfferingProposal)
        .where(
            OfferingProposal.organization_id == organization_id,
            OfferingProposal.status == PROPOSAL_PENDING,
        )
    )
    return (await session.execute(stmt)).scalar_one()


async def _get_proposal(
    session: AsyncSession, organization_id: uuid.UUID, proposal_id: uuid.UUID
) -> OfferingProposal | None:
    proposal = await session.get(OfferingProposal, proposal_id)
    if proposal is None or proposal.organization_id != organization_id:
        return None
    return proposal


async def approve_proposal(
    session: AsyncSession, organization_id: uuid.UUID, proposal_id: uuid.UUID
) -> OfferingProposal | None:
    """Applies the proposal to the live offerings. Idempotent: one already decided is returned
    untouched, so a double click cannot apply it twice."""
    proposal = await _get_proposal(session, organization_id, proposal_id)
    if proposal is None:
        return None
    if proposal.status != PROPOSAL_PENDING:
        return proposal
    now = datetime.now(UTC)

    if proposal.change == CHANGE_REMOVED:
        product = await session.get(Product, proposal.product_id) if proposal.product_id else None
        if product is not None:
            product.status = STATUS_ARCHIVED
    else:
        product = None
        if proposal.product_id is not None:
            product = await session.get(Product, proposal.product_id)
        if product is None:
            # A page that was approved earlier, archived, and has come back reuses its row.
            product = (
                await session.execute(
                    select(Product).where(
                        Product.organization_id == organization_id,
                        Product.source_url == proposal.source_url,
                    )
                )
            ).scalar_one_or_none()
        if product is None:
            product = Product(
                organization_id=organization_id,
                source=SOURCE_WEBSITE,
                source_url=proposal.source_url,
            )
            session.add(product)
        product.name = proposal.name
        product.description = proposal.description
        product.kind = proposal.kind
        product.source_hash = proposal.content_hash
        product.status = STATUS_ACTIVE
        product.last_seen_at = now

    proposal.status = PROPOSAL_APPROVED
    proposal.decided_at = now
    await session.flush()
    return proposal


async def reject_proposal(
    session: AsyncSession, organization_id: uuid.UUID, proposal_id: uuid.UUID
) -> OfferingProposal | None:
    proposal = await _get_proposal(session, organization_id, proposal_id)
    if proposal is None:
        return None
    if proposal.status == PROPOSAL_PENDING:
        proposal.status = PROPOSAL_REJECTED
        proposal.decided_at = datetime.now(UTC)
        await session.flush()
    return proposal


async def _latest_job(
    session: AsyncSession, organization_id: uuid.UUID, *statuses: str
) -> Job | None:
    stmt = select(Job).where(
        Job.organization_id == organization_id, Job.job_type == JOB_TYPE_SYNC_OFFERINGS
    )
    if statuses:
        stmt = stmt.where(Job.status.in_(statuses))
    stmt = stmt.order_by(Job.created_at.desc()).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


async def start_sync(session: AsyncSession, organization_id: uuid.UUID) -> Job:
    """Queues a sync, unless one is already waiting or running (then that one is returned, so
    pressing the button twice never doubles the work)."""
    active = await _latest_job(session, organization_id, STATUS_PENDING, STATUS_RUNNING)
    if active is not None:
        return active
    return await enqueue_job(session, organization_id, JOB_TYPE_SYNC_OFFERINGS, {})


async def sync_due(
    session: AsyncSession, organization_id: uuid.UUID, interval_days: int
) -> bool:
    """True when no sync is waiting or running and the last finished one is older than the
    interval (or there has never been one)."""
    if await _latest_job(session, organization_id, STATUS_PENDING, STATUS_RUNNING) is not None:
        return False
    last = await _latest_job(session, organization_id, STATUS_DONE)
    if last is None or last.finished_at is None:
        return True
    finished = last.finished_at
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=UTC)
    return datetime.now(UTC) - finished >= timedelta(days=interval_days)


async def enqueue_sync_if_due(
    session: AsyncSession, organization_id: uuid.UUID, interval_days: int
) -> bool:
    """The weekly check: queues a sync when one is due. An interval of 0 turns it off."""
    if interval_days <= 0 or not await sync_due(session, organization_id, interval_days):
        return False
    await start_sync(session, organization_id)
    return True


async def sync_status(session: AsyncSession, organization_id: uuid.UUID) -> dict[str, Any]:
    latest = await _latest_job(session, organization_id)
    last_done = await _latest_job(session, organization_id, STATUS_DONE)
    running = latest is not None and latest.status in (STATUS_PENDING, STATUS_RUNNING)
    return {
        "running": running,
        "job_id": latest.id if running and latest is not None else None,
        "progress": latest.progress if running and latest is not None else None,
        "last_checked_at": last_done.finished_at if last_done is not None else None,
        "last_result": last_done.result if last_done is not None else None,
        "last_error": latest.error if latest is not None and latest.status == "failed" else None,
        "pending_count": await count_pending(session, organization_id),
    }


__all__ = [
    "CHANGE_CHANGED",
    "CHANGE_NEW",
    "CHANGE_REMOVED",
    "approve_proposal",
    "count_pending",
    "duplicate_hints",
    "enqueue_sync_if_due",
    "list_proposals",
    "reject_proposal",
    "start_sync",
    "sync_due",
    "sync_status",
]
