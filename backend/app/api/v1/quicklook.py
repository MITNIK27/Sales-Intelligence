import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
from app.modules.auth.deps import signed_in
from app.modules.auth.models import User
from app.modules.companies.service import normalize_domain, split_company_input
from app.modules.enrichment.providers.search_serper import SerperSearchProvider
from app.modules.enrichment.providers.website_scraper import WebsiteScraperProvider
from app.modules.jobs.errors import friendly_error
from app.modules.llm.structured import LLMError, StructuredLLM, build_structured_llm
from app.modules.opportunity.research.sources import build_research_sources
from app.modules.opportunity.research.types import ResearchSources
from app.modules.quicklook.models import CompanySnapshot
from app.modules.quicklook.schemas import (
    CandidateOut,
    CheckAnswerOut,
    CheckedCompanyList,
    CheckedCompanyOut,
    CheckEntryOut,
    CompanyChecksOut,
    CriterionResultOut,
    OfferingFitOut,
    QuickLookRequest,
    QuickLookResponse,
    SaveRequest,
    SaveResponse,
    SnapshotOut,
    WorkingOnOut,
)
from app.modules.quicklook.service import (
    HISTORY_PAGE,
    HistoryNotFoundError,
    PageFetcher,
    Searcher,
    SnapshotNotFoundError,
    checks_for_company,
    existing_company_dismissal,
    existing_company_id,
    get_check,
    get_snapshot,
    list_checked_companies,
    look_up,
    save_as_company,
)
from app.modules.usage.context import usage_scope

router = APIRouter(prefix="/quick-look", tags=["quick-look"])


@dataclass
class QuickLookDeps:
    searcher: Searcher
    fetcher: PageFetcher
    llm: StructuredLLM
    denylist: list[str]
    # News, open jobs and related-work search; any source may be absent (not set up).
    sources: ResearchSources | None = None


async def get_deps() -> AsyncIterator[QuickLookDeps]:
    """The real providers; tests replace this dependency with fakes."""
    settings = get_settings()
    scraper = WebsiteScraperProvider(settings)
    sources, closers = build_research_sources(settings, scraper)
    try:
        yield QuickLookDeps(
            searcher=SerperSearchProvider(settings),
            fetcher=scraper,
            llm=build_structured_llm(settings, order=settings.opportunity_llm_order),
            denylist=settings.market_discovery_domain_denylist,
            sources=sources,
        )
    finally:
        await scraper.aclose()
        for closer in closers:
            await closer.aclose()


async def _snapshot_out(
    session: AsyncSession, snapshot: CompanySnapshot, cached: bool
) -> SnapshotOut:
    return await _answer_out(
        session,
        snapshot_id=snapshot.id,
        organization_id=snapshot.organization_id,
        domain=snapshot.domain,
        name=snapshot.name,
        summary=snapshot.summary or {},
        sources=snapshot.sources or [],
        updated_at=snapshot.updated_at,
        cached=cached,
    )


async def _answer_out(
    session: AsyncSession,
    *,
    snapshot_id: uuid.UUID,
    organization_id: uuid.UUID,
    domain: str,
    name: str,
    summary: dict[str, Any],
    sources: list[dict[str, Any]],
    updated_at: datetime,
    cached: bool,
) -> SnapshotOut:
    return SnapshotOut(
        id=snapshot_id,
        domain=domain,
        name=name,
        what_they_do=summary.get("what_they_do"),
        industry=summary.get("industry"),
        size_hint=summary.get("size_hint"),
        relevance=summary.get("relevance"),
        call=summary.get("call", "unclear"),
        call_reason=summary.get("call_reason", ""),
        offerings=[OfferingFitOut(**o) for o in summary.get("offerings", [])],
        working_on=[WorkingOnOut(**w) for w in summary.get("working_on", [])],
        focus=summary.get("focus"),
        criteria=[CriterionResultOut(**c) for c in summary.get("criteria", [])],
        knowledge=summary.get("knowledge") or [],
        sources=sources,
        updated_at=updated_at,
        cached=cached,
        existing_company_id=await existing_company_id(session, organization_id, domain),
        existing_company_dismissed_reason=await existing_company_dismissal(
            session, organization_id, domain
        ),
    )


@router.post("", response_model=QuickLookResponse)
async def quick_look_endpoint(
    body: QuickLookRequest,
    session: AsyncSession = Depends(get_db),
    deps: QuickLookDeps = Depends(get_deps),
) -> QuickLookResponse:
    name, domain = None, normalize_domain(body.domain)
    if body.company and body.company.strip():
        name, typed_domain = split_company_input(body.company)
        domain = domain or typed_domain
    if not name and not domain:
        raise HTTPException(status_code=422, detail="Type a company name or website.")
    avoid = {d for d in (normalize_domain(a) for a in body.avoid) if d}
    try:
        with usage_scope(organization_id=DEFAULT_ORGANIZATION_ID):
            outcome = await look_up(
                session,
                DEFAULT_ORGANIZATION_ID,
                deps.searcher,
                deps.fetcher,
                deps.llm,
                deps.denylist,
                name,
                domain,
                avoid,
                body.refresh,
                body.always_ask,
                body.focus,
                body.criteria,
                deps.sources,
            )
    except LLMError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"The short answer could not be written. {friendly_error(exc)}",
        ) from exc
    await session.commit()
    snapshot = (
        await _snapshot_out(session, outcome.snapshot, outcome.cached) if outcome.snapshot else None
    )
    return QuickLookResponse(
        status=outcome.status,
        snapshot=snapshot,
        candidates=[
            CandidateOut(name=c.name, domain=c.domain, snippet=c.snippet)
            for c in outcome.candidates
        ],
        notes=outcome.notes,
    )


# The history routes come before "/{snapshot_id}", which would otherwise claim "/history".


@router.get("/history", response_model=CheckedCompanyList)
async def history_endpoint(
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=HISTORY_PAGE, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(signed_in),
) -> CheckedCompanyList:
    """The companies this person checked, most recent first."""
    items, total = await list_checked_companies(
        session, DEFAULT_ORGANIZATION_ID, user.id, q, limit, offset
    )
    return CheckedCompanyList(
        items=[CheckedCompanyOut(**asdict(item)) for item in items], total=total
    )


@router.get("/history/checks", response_model=CompanyChecksOut)
async def company_checks_endpoint(
    domain: str = Query(max_length=255),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(signed_in),
) -> CompanyChecksOut:
    """Every check this person ran on one website, newest first."""
    entries = await checks_for_company(session, DEFAULT_ORGANIZATION_ID, user.id, domain)
    if not entries:
        raise HTTPException(status_code=404, detail="You have not checked this company.")
    return CompanyChecksOut(
        domain=entries[0].domain,
        name=entries[0].name,
        entries=[
            CheckEntryOut(
                id=e.id,
                checked_at=e.created_at,
                asked=e.asked,
                focus=e.focus,
                criteria=e.criteria or [],
                call=e.call,
                call_reason=str((e.summary or {}).get("call_reason") or ""),
                cached=e.cached,
                refreshed=e.refreshed,
            )
            for e in entries
        ],
    )


@router.get("/history/entries/{entry_id}", response_model=CheckAnswerOut)
async def check_answer_endpoint(
    entry_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(signed_in),
) -> CheckAnswerOut:
    """An earlier check's answer as it was given then."""
    try:
        entry = await get_check(session, DEFAULT_ORGANIZATION_ID, user.id, entry_id)
    except HistoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    answer = await _answer_out(
        session,
        snapshot_id=entry.snapshot_id,
        organization_id=entry.organization_id,
        domain=entry.domain,
        name=entry.name,
        summary=entry.summary or {},
        sources=entry.sources or [],
        updated_at=entry.created_at,
        cached=True,
    )
    return CheckAnswerOut(
        entry_id=entry.id, checked_at=entry.created_at, criteria=entry.criteria or [], answer=answer
    )


@router.get("/{snapshot_id}", response_model=SnapshotOut)
async def get_snapshot_endpoint(
    snapshot_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> SnapshotOut:
    try:
        snapshot = await get_snapshot(session, DEFAULT_ORGANIZATION_ID, snapshot_id)
    except SnapshotNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await _snapshot_out(session, snapshot, True)


@router.post("/save", response_model=SaveResponse)
async def save_endpoint(body: SaveRequest, session: AsyncSession = Depends(get_db)) -> SaveResponse:
    try:
        saved = await save_as_company(
            session, DEFAULT_ORGANIZATION_ID, body.snapshot_id, body.go_deeper
        )
    except SnapshotNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return SaveResponse(**saved)
