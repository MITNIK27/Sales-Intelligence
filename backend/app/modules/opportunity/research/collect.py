"""Collecting evidence for one opportunity. Runs each collector at most as often as its results
stay fresh, saves what they find as evidence tagged with the opportunity, and records on the
opportunity what was searched so a gap can be reported. A collector that fails reports an error
and the others carry on."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.enrichment.providers.context_dev import ContextDevBudgetExceeded
from app.modules.opportunity.models import CompanyOpportunity
from app.modules.opportunity.research.matching import matching_postings
from app.modules.opportunity.research.report import add_snapshot, is_fresh
from app.modules.opportunity.research.types import (
    KIND_HIRING,
    KIND_NEWS,
    KIND_WEB,
    SIGNAL_JOB_POSTING,
    CollectedItem,
    ResearchSources,
    SourceReport,
)
from app.modules.opportunity.service import save_area_records

logger = logging.getLogger(__name__)

NEWS_WINDOW = timedelta(days=365)
NEWS_LIMIT = 10
WEB_LIMIT = 10

SOURCE_NEWS = "opportunity:news"
SOURCE_HIRING = "opportunity:hiring"
SOURCE_WEB = "opportunity:web"

_WEB_TOPICS = "initiative OR partnership OR programme OR announces OR launches OR rollout"


def _failure(exc: Exception) -> str:
    if isinstance(exc, ContextDevBudgetExceeded):
        return "the search credit limit for this run was reached"
    if isinstance(exc, httpx.HTTPError):
        return "the search service could not be reached"
    return "the search did not complete"


def _posting_item(posting: Any, board: str | None) -> CollectedItem:
    parts = [posting.title, posting.department, posting.location]
    return CollectedItem(
        signal_type=SIGNAL_JOB_POSTING,
        text=" — ".join(p for p in parts if p),
        url=posting.url,
        date=posting.posted,
        summary=posting.excerpt or None,
        provider=board or "careers",
        extra={"department": posting.department, "location": posting.location, "board": board},
    )


async def _collect_news(
    session: AsyncSession,
    company: Company,
    opportunity: CompanyOpportunity,
    sources: ResearchSources,
    now: datetime,
    area: str | None = None,
) -> dict[str, Any]:
    if sources.news is None:
        return {"error": "news search is not set up", "found": 0, "searched": []}
    query = f'"{company.name}" {area or opportunity.area_label}'
    try:
        items = await sources.news.search(query, now - NEWS_WINDOW, NEWS_LIMIT)
    except Exception as exc:  # noqa: BLE001 - one collector failing must not stop the others
        logger.info("news collection failed for %s: %s", company.id, exc)
        return {"error": _failure(exc), "found": 0, "searched": ["news, last 12 months"]}
    await save_area_records(session, company, opportunity, SOURCE_NEWS, items)
    return {"found": len(items), "searched": ["news, last 12 months"], "error": None}


async def _collect_hiring(
    session: AsyncSession,
    company: Company,
    opportunity: CompanyOpportunity,
    sources: ResearchSources,
    now: datetime,
    previous: dict[str, Any] | None,
    area: str | None = None,
) -> dict[str, Any]:
    if sources.hiring is None or not company.domain:
        return {"error": "no website is known for this company", "found": 0, "searched": []}
    try:
        result = await sources.hiring.postings(company.domain)
    except Exception as exc:  # noqa: BLE001
        logger.info("hiring collection failed for %s: %s", company.id, exc)
        return {"error": _failure(exc), "found": 0, "searched": [company.domain]}
    matches = matching_postings(result.postings, area or opportunity.area_label)
    items = [_posting_item(p, result.board) for p in matches]
    await save_area_records(session, company, opportunity, SOURCE_HIRING, items)
    entry: dict[str, Any] = {
        "found": len(matches),
        "total_open": len(result.postings) if result.board and not result.error else None,
        "board": result.board,
        "searched": result.searched,
        "error": result.error,
        "snapshots": (previous or {}).get("snapshots", []),
    }
    if result.board and not result.error:
        entry["snapshots"] = add_snapshot(
            entry["snapshots"], now, len(result.postings), len(matches)
        )
    return entry


async def _collect_web(
    session: AsyncSession,
    company: Company,
    opportunity: CompanyOpportunity,
    sources: ResearchSources,
    area_text: str | None = None,
) -> dict[str, Any]:
    if sources.web is None:
        return {"error": "web search is not set up", "found": 0, "searched": []}
    area = area_text or opportunity.area_label
    searches: list[tuple[str, list[str] | None, str]] = [
        (f'"{company.name}" {area} {_WEB_TOPICS}', None, "the web"),
    ]
    if company.domain:
        searches.append((area, [company.domain], f"{company.domain}"))
    items: list[CollectedItem] = []
    searched: list[str] = []
    try:
        for query, domains, label in searches:
            items.extend(await sources.web.search(query, domains, WEB_LIMIT))
            searched.append(label)
    except Exception as exc:  # noqa: BLE001
        logger.info("web collection failed for %s: %s", company.id, exc)
        if not items:
            return {"error": _failure(exc), "found": 0, "searched": searched}
    await save_area_records(session, company, opportunity, SOURCE_WEB, items)
    return {"found": len(items), "searched": searched, "error": None}


async def collect_area_evidence(
    session: AsyncSession,
    company: Company,
    opportunity: CompanyOpportunity,
    sources: ResearchSources,
    now: datetime | None = None,
    force: bool = False,
    area: str | None = None,
) -> list[SourceReport]:
    """Run the collectors that are not still fresh and record what each did on the opportunity.
    `area` replaces the opportunity's own area label in the searches, which is how the company as a
    whole is researched (see `offers.py`)."""
    now = now or datetime.now(UTC)
    log: dict[str, Any] = dict(opportunity.research_log or {})
    reports: list[SourceReport] = []

    for kind in (KIND_HIRING, KIND_NEWS, KIND_WEB):
        if not force and is_fresh(log, kind, now):
            reports.append(
                SourceReport(
                    kind=kind,
                    skipped=True,
                    found=log[kind].get("found", 0),
                    searched=log[kind].get("searched", []),
                )
            )
            continue
        if kind == KIND_HIRING:
            entry = await _collect_hiring(
                session, company, opportunity, sources, now, log.get(kind), area
            )
        elif kind == KIND_NEWS:
            entry = await _collect_news(session, company, opportunity, sources, now, area)
        else:
            entry = await _collect_web(session, company, opportunity, sources, area)
        log[kind] = {"at": now.isoformat(), **entry}
        reports.append(
            SourceReport(
                kind=kind,
                searched=entry.get("searched", []),
                found=entry.get("found", 0),
                error=entry.get("error"),
                total_open=entry.get("total_open"),
                board=entry.get("board"),
            )
        )

    opportunity.research_log = log  # a new dict, so the change is saved
    await session.flush()
    return reports
