import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tenancy import DEFAULT_ORGANIZATION_ID
from app.db.session import get_db
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
    PageFetcher,
    Searcher,
    SnapshotNotFoundError,
    existing_company_dismissal,
    existing_company_id,
    get_snapshot,
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
    summary = snapshot.summary or {}
    return SnapshotOut(
        id=snapshot.id,
        domain=snapshot.domain,
        name=snapshot.name,
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
        sources=snapshot.sources or [],
        updated_at=snapshot.updated_at,
        cached=cached,
        existing_company_id=await existing_company_id(
            session, snapshot.organization_id, snapshot.domain
        ),
        existing_company_dismissed_reason=await existing_company_dismissal(
            session, snapshot.organization_id, snapshot.domain
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
