"""Manual tool: check, without changing anything, that the offerings catalogue is complete and
correct. Not part of the app, not imported by anything.

For every live offering imported from the website it checks that the address still answers, that
the name is on the page, and that the description sticks to what the page says. It also looks for
offerings that may be the same thing under two addresses, compares the catalogue with the
company's own website menu, and reports the health of the importer's page memory.

Read-only: it reads the database and the website and writes nothing. Exits with status 1 when
something needs attention, 0 when everything is clean, so it can be run before showing the tool.

Run from `backend/`:   .venv\\Scripts\\python.exe scripts\\audit_offerings.py
"""

import asyncio
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.tenancy import DEFAULT_ORGANIZATION_ID  # noqa: E402
from app.db import models as _models  # noqa: E402, F401 - registers every model
from app.db.session import SessionLocal  # noqa: E402
from app.modules.jobs.models import Job  # noqa: E402
from app.modules.offerings.coverage import reconcile_menu  # noqa: E402
from app.modules.offerings.grounding import check_grounding  # noqa: E402
from app.modules.offerings.menu import read_menu  # noqa: E402
from app.modules.offerings.models import (  # noqa: E402
    CHANGE_REMOVED,
    PROPOSAL_PENDING,
    VERDICT_FAILED,
    VERDICT_OFFERING,
    OfferingPage,
    OfferingProposal,
)
from app.modules.offerings.names import names_match  # noqa: E402
from app.modules.offerings.service import JOB_TYPE_SYNC_OFFERINGS  # noqa: E402
from app.modules.offerings.sources import html_to_text  # noqa: E402
from app.modules.offerings.urls import canonical_url  # noqa: E402
from app.modules.products.models import SOURCE_WEBSITE, STATUS_ACTIVE, Product  # noqa: E402

problems: list[str] = []


def note(line: str = "") -> None:
    print(line)


def problem(line: str) -> None:
    problems.append(line)
    print(f"  ! {line}")


async def check_offerings(products: list[Product], user_agent: str) -> None:
    note(f"\n== Live offerings from the website ({len(products)}) ==")
    async with httpx.AsyncClient(
        headers={"User-Agent": user_agent}, timeout=20.0, follow_redirects=True
    ) as client:
        for product in products:
            url = product.source_url or ""
            try:
                resp = await client.get(url)
            except httpx.HTTPError as exc:
                problem(f"{product.name}: could not reach {url} ({type(exc).__name__})")
                continue
            if resp.status_code in (404, 410):
                problem(f"{product.name}: {url} answers {resp.status_code} (the page is gone)")
                continue
            if resp.status_code != 200:
                problem(f"{product.name}: {url} answers {resp.status_code}")
                continue
            flags = check_grounding(product.name, product.description, html_to_text(resp.text))
            if flags:
                problem(f"{product.name}: wording to check: " + "; ".join(flags))
            else:
                note(f"  ok  {product.name}")
            if url != canonical_url(url):
                problem(f"{product.name}: address is not in canonical form: {url}")


def check_duplicates(products: list[Product]) -> None:
    note("\n== Possible duplicates ==")
    found = False
    for index, a in enumerate(products):
        for b in products[index + 1 :]:
            if names_match(a.name, b.name):
                found = True
                problem(f'"{a.name}" ({a.source_url}) and "{b.name}" ({b.source_url})')
    if not found:
        note("  none")


async def check_menu(session, settings, pages: dict[str, OfferingPage], names: list[str]) -> None:
    note("\n== Website menu against the catalogue ==")
    try:
        items = await read_menu(
            settings.offerings_menu_url, settings.offerings_menu_groups, settings.scraper_user_agent
        )
    except Exception as exc:  # noqa: BLE001 - reported, not fatal
        problem(f"could not read the website menu: {type(exc).__name__}")
        return
    menu = [{"group": i.group, "label": i.label, "url": i.url} for i in items]
    for entry in reconcile_menu(menu, pages, names):
        status = entry["status"]
        line = f'{entry["group"]}: {entry["label"]} ({entry["url"]}) -> {status}'
        if status in ("missing", "unreadable"):
            problem(line)
        else:
            note(f"  ok  {line}")


async def check_ledger(session) -> dict[str, OfferingPage]:
    note("\n== Importer page memory ==")
    rows = (
        await session.execute(
            select(OfferingPage).where(OfferingPage.organization_id == DEFAULT_ORGANIZATION_ID)
        )
    ).scalars().all()
    # Looked up by canonical address, so rows saved before addresses were normalised still match.
    pages = {canonical_url(row.url): row for row in rows}
    counts = Counter((row.lane, row.verdict) for row in rows)
    for (lane, verdict), n in sorted(counts.items()):
        note(f"  {n:4d}  {lane:5s}  {verdict}")
    failed = [row.url for row in rows if row.verdict == VERDICT_FAILED]
    if failed:
        problem(f"{len(failed)} pages could not be read the last time they were tried")
    stale = [row.url for row in rows if row.url != canonical_url(row.url)]
    if stale:
        note(
            f"  {len(stale)} rows use an older address spelling (a trailing slash); the next "
            "check renames them. Not a problem."
        )
    return pages


async def check_consistency(session, products: list[Product], pages) -> None:
    note("\n== Consistency ==")
    proposals = (
        await session.execute(
            select(OfferingProposal).where(
                OfferingProposal.organization_id == DEFAULT_ORGANIZATION_ID
            )
        )
    ).scalars().all()
    known_urls = {canonical_url(p.source_url) for p in products if p.source_url}
    known_urls |= {canonical_url(p.source_url) for p in proposals}
    for url, row in pages.items():
        if row.verdict == VERDICT_OFFERING and url not in known_urls:
            problem(f"remembered as an offering but there is no offering or proposal for it: {url}")
    waiting_removals = [
        p for p in proposals if p.change == CHANGE_REMOVED and p.status == PROPOSAL_PENDING
    ]
    if waiting_removals:
        problem(
            f"{len(waiting_removals)} 'no longer on website' proposals are waiting; the next "
            "check withdraws any whose page is alive"
        )
    if not problems:
        note("  nothing inconsistent")


async def check_last_sync(session) -> None:
    note("\n== Last checks ==")
    jobs = (
        await session.execute(
            select(Job)
            .where(
                Job.organization_id == DEFAULT_ORGANIZATION_ID,
                Job.job_type == JOB_TYPE_SYNC_OFFERINGS,
            )
            .order_by(Job.created_at.desc())
            .limit(3)
        )
    ).scalars().all()
    if not jobs:
        problem("no check has ever run")
        return
    for job in jobs:
        age = ""
        if job.finished_at is not None:
            finished = job.finished_at
            if finished.tzinfo is None:
                finished = finished.replace(tzinfo=UTC)
            age = f"{(datetime.now(UTC) - finished).total_seconds() / 3600:.1f} h ago"
        result = job.result or {}
        summary = {k: v for k, v in result.items() if isinstance(v, int)}
        note(f"  {job.status:8s} {age:12s} {summary or (job.error or '')[:100]}")
    if jobs[0].status == "failed":
        problem(f"the latest check failed: {(jobs[0].error or '')[:120]}")


async def main() -> int:
    settings = get_settings()
    async with SessionLocal() as session:
        products = (
            await session.execute(
                select(Product)
                .where(
                    Product.organization_id == DEFAULT_ORGANIZATION_ID,
                    Product.source == SOURCE_WEBSITE,
                    Product.status == STATUS_ACTIVE,
                )
                .order_by(Product.name)
            )
        ).scalars().all()
        all_names = (
            await session.execute(
                select(Product.name).where(
                    Product.organization_id == DEFAULT_ORGANIZATION_ID,
                    Product.status == STATUS_ACTIVE,
                )
            )
        ).scalars().all()

        await check_offerings(list(products), settings.scraper_user_agent)
        check_duplicates(list(products))
        pages = await check_ledger(session)
        await check_menu(session, settings, pages, list(all_names))
        await check_consistency(session, list(products), pages)
        await check_last_sync(session)

    note()
    if problems:
        note(f"{len(problems)} thing(s) need attention (marked !).")
        return 1
    note("Everything checks out.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
