"""The "what was checked" view: every page the importer has considered and what it concluded, and
the website menu checked against the catalogue. It exists so that a missing offering is never a
mystery: anyone can see whether the page was read, why it was set aside, or never looked at."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.jobs.models import STATUS_DONE, Job
from app.modules.offerings.models import (
    LANE_EXTRA,
    PROPOSAL_PENDING,
    VERDICT_FAILED,
    VERDICT_NOT_OFFERING,
    VERDICT_OFFERING,
    OfferingPage,
    OfferingProposal,
)
from app.modules.offerings.names import names_match
from app.modules.offerings.service import JOB_TYPE_SYNC_OFFERINGS
from app.modules.offerings.urls import canonical_url
from app.modules.products.models import STATUS_ACTIVE, Product

# Menu statuses.
MENU_COVERED = "covered"
MENU_NOT_AN_OFFERING = "judged_not_offering"
MENU_UNREADABLE = "unreadable"
MENU_MISSING = "missing"


def reconcile_menu(
    menu: list[dict[str, str]],
    pages: dict[str, OfferingPage],
    offering_names: list[str],
) -> list[dict[str, Any]]:
    """Each menu entry with what the catalogue knows about it."""
    results: list[dict[str, Any]] = []
    for item in menu:
        row = pages.get(item["url"])
        by_name = any(names_match(item["label"], name) for name in offering_names)
        if row is not None and row.verdict == VERDICT_OFFERING:
            status = MENU_COVERED
        elif by_name:
            status = MENU_COVERED  # e.g. expona.io is the menu link, /expona/ is what we read
        elif row is not None and row.verdict == VERDICT_NOT_OFFERING:
            status = MENU_NOT_AN_OFFERING
        elif row is not None and row.verdict == VERDICT_FAILED:
            status = MENU_UNREADABLE
        else:
            status = MENU_MISSING
        results.append({**item, "status": status})
    return results


async def latest_menu(session: AsyncSession, organization_id: uuid.UUID) -> dict[str, Any] | None:
    """The menu snapshot taken by the last finished sync (None if there has been none)."""
    stmt = (
        select(Job)
        .where(
            Job.organization_id == organization_id,
            Job.job_type == JOB_TYPE_SYNC_OFFERINGS,
            Job.status == STATUS_DONE,
        )
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None or not job.result:
        return None
    return {"menu": job.result.get("menu"), "menu_error": job.result.get("menu_error")}


async def get_coverage(session: AsyncSession, organization_id: uuid.UUID) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(OfferingPage)
            .where(OfferingPage.organization_id == organization_id)
            .order_by(OfferingPage.verdict, OfferingPage.url)
        )
    ).scalars().all()
    pages = {canonical_url(row.url): row for row in rows}

    names = [
        n
        for n in (
            await session.execute(
                select(Product.name).where(
                    Product.organization_id == organization_id, Product.status == STATUS_ACTIVE
                )
            )
        ).scalars()
    ]
    names += [
        n
        for n in (
            await session.execute(
                select(OfferingProposal.name).where(
                    OfferingProposal.organization_id == organization_id,
                    OfferingProposal.status == PROPOSAL_PENDING,
                )
            )
        ).scalars()
    ]

    snapshot = await latest_menu(session, organization_id)
    menu_items = None
    menu_error = None
    if snapshot is not None:
        menu_error = snapshot["menu_error"]
        if snapshot["menu"] is not None:
            menu_items = reconcile_menu(snapshot["menu"], pages, names)

    counts = {VERDICT_OFFERING: 0, VERDICT_NOT_OFFERING: 0, VERDICT_FAILED: 0}
    for row in rows:
        counts[row.verdict] = counts.get(row.verdict, 0) + 1

    return {
        "summary": {"total": len(rows), **counts},
        "pages": [
            {
                "url": row.url,
                "title": row.title,
                "lane": row.lane,
                "verdict": row.verdict,
                "reason": row.reason,
                "lastmod": row.lastmod,
                "last_checked_at": row.last_checked_at,
                "force_extract": row.force_extract,
            }
            for row in rows
        ],
        "menu": menu_items,
        "menu_error": menu_error,
    }


async def request_extraction(
    session: AsyncSession, organization_id: uuid.UUID, url: str, lane: str = LANE_EXTRA
) -> OfferingPage:
    """A person says this page is an offering (or wants it checked): the next sync reads it and
    asks the model to describe it regardless of an earlier "not an offering". A page the importer
    has never seen is added to the ledger first."""
    url = canonical_url(url)
    row = (
        await session.execute(
            select(OfferingPage).where(
                OfferingPage.organization_id == organization_id, OfferingPage.url == url
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = OfferingPage(
            organization_id=organization_id,
            url=url,
            lane=lane,
            verdict=VERDICT_NOT_OFFERING,
            reason="added by a person",
            last_checked_at=datetime.now(UTC),
        )
        session.add(row)
    row.force_extract = True
    await session.flush()
    return row
