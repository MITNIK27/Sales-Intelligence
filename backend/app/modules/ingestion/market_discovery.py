import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.ai_recommendation.gemini_client import (
    GeminiMarketDescriptionParser,
    MarketDescriptionParser,
)
from app.modules.companies.service import get_or_create_company, search_company_index
from app.modules.discovery_agent.agent import (
    CompanyDiscoveryAgentProtocol,
    DiscoveryAgentError,
    get_default_discovery_agent,
)
from app.modules.discovery_agent.schemas import MarketCriteria
from app.modules.enrichment.providers.base import (
    CompanyDataProvider,
    ContactDataProvider,
    DomainDiscoveryProvider,
    SignalDataProvider,
)
from app.modules.enrichment.providers.search_serper import SerperSearchProvider
from app.modules.enrichment.providers.website_scraper import WebsiteScraperProvider
from app.modules.enrichment.service import _enrich_company
from app.modules.ingestion.models import (
    SOURCE_TYPE_MARKET_DISCOVERY,
    STATUS_AWAITING_CONFIRMATION,
    STATUS_DONE,
    STATUS_PENDING,
    STATUS_RUNNING,
    IngestionRun,
)
from app.modules.jobs.models import Job
from app.modules.jobs.service import enqueue_job

logger = logging.getLogger(__name__)

JOB_TYPE_MARKET_DISCOVERY = "market_discovery"

# One search call, one page of results — keeps a single Market Discovery run bounded and fast.
# Repeatable: the user can run another description/search to get more.
CANDIDATE_LIMIT = 10

ProgressCallback = Callable[[int, int], Awaitable[None]]


async def start_market_discovery_parse(
    session: AsyncSession,
    organization_id: uuid.UUID,
    raw_input: str,
    parser: MarketDescriptionParser,
) -> IngestionRun:
    """Calls the Gemini parser inline (a single fast LLM call, not worth a background job) and
    stores the result for the user to confirm/correct. Raises `GeminiClientError` on failure —
    the caller (the API router) surfaces that as a clear error, not a silent fallback."""
    criteria = await parser.parse(raw_input)
    run = IngestionRun(
        organization_id=organization_id,
        source_type=SOURCE_TYPE_MARKET_DISCOVERY,
        status=STATUS_AWAITING_CONFIRMATION,
        raw_input=raw_input,
        parsed_fields=criteria.model_dump(),
    )
    session.add(run)
    await session.flush()
    return run


async def get_market_discovery_run(
    session: AsyncSession, organization_id: uuid.UUID, run_id: uuid.UUID
) -> IngestionRun | None:
    run = await session.get(IngestionRun, run_id)
    if run is None or run.organization_id != organization_id:
        return None
    return run


async def confirm_market_discovery(
    session: AsyncSession,
    organization_id: uuid.UUID,
    run_id: uuid.UUID,
    industry_keywords: list[str],
    location: str | None,
    employee_size_range: str | None,
) -> Job | None:
    run = await get_market_discovery_run(session, organization_id, run_id)
    if run is None:
        return None
    run.parsed_fields = {
        "industry_keywords": {"value": industry_keywords, "confidence": "confident"},
        "location": {"value": location, "confidence": "confident"},
        "employee_size_range": {"value": employee_size_range, "confidence": "confident"},
    }
    run.confirmed_at = datetime.now(UTC)
    run.status = STATUS_PENDING
    await session.flush()
    return await enqueue_job(
        session, organization_id, JOB_TYPE_MARKET_DISCOVERY, {"ingestion_run_id": str(run.id)}
    )


def _build_search_query(parsed_fields: dict[str, Any]) -> str:
    industry_keywords = (parsed_fields.get("industry_keywords") or {}).get("value") or []
    location = (parsed_fields.get("location") or {}).get("value")
    parts = [*industry_keywords, "companies"]
    if location:
        parts.append(f"in {location}")
    return " ".join(parts)


def _to_market_criteria(parsed_fields: dict[str, Any]) -> MarketCriteria:
    industry_keywords = (parsed_fields.get("industry_keywords") or {}).get("value") or []
    location = (parsed_fields.get("location") or {}).get("value")
    employee_size_range = (parsed_fields.get("employee_size_range") or {}).get("value")
    return MarketCriteria(
        industry_keywords=industry_keywords,
        location=location,
        employee_size_range=employee_size_range,
    )


async def _run_market_discovery(
    session: AsyncSession,
    job: Job,
    discovery_agent: CompanyDiscoveryAgentProtocol,
    domain_provider: DomainDiscoveryProvider,
    company_provider: CompanyDataProvider,
    contact_provider: ContactDataProvider,
    signal_provider: SignalDataProvider,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """The testable core of the Market Discovery job — takes providers/the discovery agent
    explicitly so tests can inject fakes. See `process_market_discovery_job` for the real
    provider wiring."""
    payload = job.payload or {}
    run_id = uuid.UUID(payload["ingestion_run_id"])
    run = await session.get(IngestionRun, run_id)
    if run is None:
        raise ValueError(f"ingestion run {run_id} not found")

    run.status = STATUS_RUNNING
    await session.flush()

    parsed_fields = run.parsed_fields or {}
    industry_keywords = (parsed_fields.get("industry_keywords") or {}).get("value") or []
    criteria = _to_market_criteria(parsed_fields)

    # Compounding index: reuse companies this org already discovered/enriched before paying for
    # a live discovery run. Reduces (or, once enough is known, eliminates) the agent call for
    # queries that overlap with past ones.
    reused_companies = await search_company_index(
        session, job.organization_id, industry_keywords, limit=CANDIDATE_LIMIT
    )
    reused_domains = {c.domain for c in reused_companies if c.domain}
    remaining_limit = CANDIDATE_LIMIT - len(reused_companies)

    candidates: list[Any] = []
    discovery_stats: dict[str, int] = {}
    if remaining_limit > 0:
        try:
            result = await discovery_agent.discover(criteria, limit=remaining_limit)
        except DiscoveryAgentError as exc:
            # No silent fallback: a broken discovery run must fail loudly, not quietly return
            # zero (or worse, noisy) candidates — same principle as `start_market_discovery_parse`.
            logger.warning("market discovery run %s: discovery agent failed: %s", run.id, exc)
            raise
        candidates = result.companies
        discovery_stats = {
            "raw_results": result.raw_results_count,
            "extracted": result.extracted_count,
            "accepted": result.accepted_count,
            "rejected": len(result.rejected),
        }
    logger.info(
        "market discovery run %s: criteria=%r reused=%d found=%d candidate(s) stats=%s",
        run.id,
        criteria,
        len(reused_companies),
        len(candidates),
        discovery_stats,
    )

    companies_created = 0
    total = len(candidates) or 1
    for i, candidate in enumerate(candidates, start=1):
        if candidate.domain in reused_domains:
            continue
        async with session.begin_nested():
            company, created = await get_or_create_company(
                session,
                job.organization_id,
                name=candidate.name or candidate.domain,
                domain=candidate.domain,
                source_ingestion_run_id=run.id,
            )
            if created:
                company.needs_review = True
                company.needs_review_reason = "found via Market Discovery search, not confirmed"
                companies_created += 1
                await session.flush()
                await _enrich_company(
                    session,
                    job.organization_id,
                    company,
                    domain_provider,
                    company_provider,
                    contact_provider,
                    signal_provider,
                )
        if progress_callback:
            await progress_callback(i, total)

    run.status = STATUS_DONE
    run.summary = {
        "candidates_found": len(candidates),
        "companies_created": companies_created,
        "reused_from_index": len(reused_companies),
        **discovery_stats,
    }
    await session.flush()
    return run.summary


async def process_market_discovery_job(
    session: AsyncSession, job: Job, progress_callback: ProgressCallback | None = None
) -> dict[str, Any]:
    """Handler registered with the job worker — builds the real providers/agent and delegates to
    `_run_market_discovery`."""
    settings = get_settings()
    discovery_agent = get_default_discovery_agent(settings)
    domain_provider = SerperSearchProvider(settings)
    scraper = WebsiteScraperProvider(settings)
    try:
        return await _run_market_discovery(
            session,
            job,
            discovery_agent,
            domain_provider,
            scraper,
            scraper,
            scraper,
            progress_callback,
        )
    finally:
        await scraper.aclose()


def get_default_market_description_parser() -> MarketDescriptionParser:
    return GeminiMarketDescriptionParser(get_settings())
