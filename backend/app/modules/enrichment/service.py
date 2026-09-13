import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.modules.companies.models import (
    ENRICHMENT_STATUS_ENRICHED,
    ENRICHMENT_STATUS_FAILED,
    ENRICHMENT_STATUS_NEVER_ENRICHED,
    ENRICHMENT_STATUS_PENDING,
    Company,
)
from app.modules.contacts.models import Contact
from app.modules.contacts.service import get_or_create_contact, upsert_contact_channel
from app.modules.enrichment.models import ENTITY_TYPE_COMPANY, EnrichmentRecord
from app.modules.enrichment.providers.base import (
    CompanyDataProvider,
    ContactDataProvider,
    DomainDiscoveryProvider,
    SignalDataProvider,
)
from app.modules.enrichment.providers.search_serper import SerperSearchProvider
from app.modules.enrichment.providers.website_scraper import WebsiteScraperProvider
from app.modules.jobs.models import Job
from app.modules.jobs.service import enqueue_job

JOB_TYPE_SCRAPE_COMPANY = "scrape_company"

# One Job enqueued per company on a bulk trigger — capped so a single click can't accidentally
# enqueue an unbounded number of jobs. Repeatable: the next call picks up whatever's still
# never_enriched/failed.
BULK_SCRAPE_LIMIT = 500

ProgressCallback = Callable[[int, int], Awaitable[None]]


@dataclass(frozen=True)
class NeedsReviewEntry:
    entity_type: str
    company_id: uuid.UUID
    company_name: str
    contact_id: uuid.UUID | None
    contact_name: str | None
    reason: str
    flagged_at: datetime


async def start_company_scrape(
    session: AsyncSession, organization_id: uuid.UUID, company_id: uuid.UUID
) -> Job | None:
    company = await session.get(Company, company_id)
    if company is None or company.organization_id != organization_id:
        return None
    company.enrichment_status = ENRICHMENT_STATUS_PENDING
    await session.flush()
    return await enqueue_job(
        session, organization_id, JOB_TYPE_SCRAPE_COMPANY, {"company_id": str(company_id)}
    )


async def start_bulk_scrape(session: AsyncSession, organization_id: uuid.UUID) -> int:
    stmt = (
        select(Company)
        .where(
            Company.organization_id == organization_id,
            Company.enrichment_status.in_(
                [ENRICHMENT_STATUS_NEVER_ENRICHED, ENRICHMENT_STATUS_FAILED]
            ),
        )
        .limit(BULK_SCRAPE_LIMIT)
    )
    companies = (await session.execute(stmt)).scalars().all()
    for company in companies:
        company.enrichment_status = ENRICHMENT_STATUS_PENDING
        await enqueue_job(
            session, organization_id, JOB_TYPE_SCRAPE_COMPANY, {"company_id": str(company.id)}
        )
    await session.flush()
    return len(companies)


async def list_needs_review(
    session: AsyncSession, organization_id: uuid.UUID
) -> list[NeedsReviewEntry]:
    entries: list[NeedsReviewEntry] = []

    company_stmt = select(Company).where(
        Company.organization_id == organization_id, Company.needs_review.is_(True)
    )
    for company in (await session.execute(company_stmt)).scalars().all():
        entries.append(
            NeedsReviewEntry(
                entity_type="company",
                company_id=company.id,
                company_name=company.name,
                contact_id=None,
                contact_name=None,
                reason=company.needs_review_reason or "",
                flagged_at=company.updated_at,
            )
        )

    contact_stmt = (
        select(Contact)
        .where(Contact.organization_id == organization_id, Contact.needs_review.is_(True))
        .options(selectinload(Contact.company))
    )
    for contact in (await session.execute(contact_stmt)).scalars().all():
        entries.append(
            NeedsReviewEntry(
                entity_type="contact",
                company_id=contact.company_id,
                company_name=contact.company.name,
                contact_id=contact.id,
                contact_name=contact.full_name,
                reason=contact.needs_review_reason or "",
                flagged_at=contact.updated_at,
            )
        )

    def _sort_key(entry: NeedsReviewEntry) -> datetime:
        # SQLite (used in tests) does not round-trip tzinfo, so a freshly-reloaded row can come
        # back naive even though it was written as UTC-aware — normalize before comparing.
        flagged_at = entry.flagged_at
        return flagged_at if flagged_at.tzinfo is not None else flagged_at.replace(tzinfo=UTC)

    entries.sort(key=_sort_key, reverse=True)
    return entries


async def _enrich_company(
    session: AsyncSession,
    organization_id: uuid.UUID,
    company: Company,
    domain_provider: DomainDiscoveryProvider,
    company_provider: CompanyDataProvider,
    contact_provider: ContactDataProvider,
    signal_provider: SignalDataProvider,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """The testable core of company enrichment — domain resolution, firmographics, contacts,
    signals. Takes providers explicitly so tests can inject mocks instead of hitting the
    network. Shared by both the per-company scrape job (`_run_scrape`) and the Market Discovery
    job's per-candidate enrichment step, so this pipeline exists exactly once."""
    steps_total = 4
    step = 0

    async def tick() -> None:
        nonlocal step
        step += 1
        if progress_callback:
            await progress_callback(step, steps_total)

    domain = company.domain
    domain_discovered = False
    if not domain:
        match = await domain_provider.find_domain(company.name)
        await tick()
        if match is None:
            company.enrichment_status = ENRICHMENT_STATUS_FAILED
            company.enrichment_error = "no domain on file and none found"
            await session.flush()
            return {"status": ENRICHMENT_STATUS_FAILED, "reason": "no_domain"}
        domain = match.domain
        domain_discovered = True
    else:
        await tick()

    try:
        company_data = await company_provider.fetch_company_data(domain)
    except Exception as exc:  # noqa: BLE001 - surfaced as a retryable enrichment failure
        company.enrichment_status = ENRICHMENT_STATUS_FAILED
        company.enrichment_error = str(exc)
        await session.flush()
        return {"status": ENRICHMENT_STATUS_FAILED, "reason": str(exc)}
    await tick()

    if not company.domain:
        company.domain = domain
    if domain_discovered:
        company.needs_review = True
        company.needs_review_reason = "domain found via search API, not confirmed"
    if not company.description and company_data.description:
        company.description = company_data.description
    if not company.employee_count_range and company_data.employee_count_range:
        company.employee_count_range = company_data.employee_count_range
    if not company.industry and company_data.industry:
        company.industry = company_data.industry

    now = datetime.now(UTC)
    for page in company_data.pages_fetched:
        session.add(
            EnrichmentRecord(
                organization_id=organization_id,
                entity_type=ENTITY_TYPE_COMPANY,
                entity_id=company.id,
                source=f"scraper:companysite:{page.url}",
                raw_payload={
                    "url": page.url,
                    "status_code": page.status_code,
                    "description": company_data.description,
                    "employee_count_range": company_data.employee_count_range,
                },
                fetched_at=now,
            )
        )

    contacts_found = 0
    contacts_flagged = 0
    scraped_contacts = await contact_provider.fetch_contacts(domain, company_data.pages_fetched)
    for scraped in scraped_contacts:
        async with session.begin_nested():
            contact, _created = await get_or_create_contact(
                session,
                organization_id,
                company_id=company.id,
                full_name=scraped.full_name,
                role_title=scraped.role_title,
                email=scraped.email,
            )
            if scraped.email:
                await upsert_contact_channel(
                    session, contact.id, "email", scraped.email, source="scraper:companysite"
                )
            else:
                contact.needs_review = True
                contact.needs_review_reason = "no verified email found"
            contacts_found += 1
            if contact.needs_review:
                contacts_flagged += 1
    await tick()

    signals = await signal_provider.fetch_signals(domain)
    for signal in signals:
        session.add(
            EnrichmentRecord(
                organization_id=organization_id,
                entity_type=ENTITY_TYPE_COMPANY,
                entity_id=company.id,
                source=f"scraper:companysite:signals:{signal.url}",
                raw_payload={
                    "signal_type": signal.signal_type,
                    "text": signal.text,
                    "url": signal.url,
                    "date": signal.date,
                },
                fetched_at=now,
            )
        )
    await tick()

    company.enrichment_status = ENRICHMENT_STATUS_ENRICHED
    company.last_enriched_at = now
    company.enrichment_error = None
    await session.flush()

    return {
        "status": ENRICHMENT_STATUS_ENRICHED,
        "domain": domain,
        "domain_discovered": domain_discovered,
        "contacts_found": contacts_found,
        "contacts_flagged": contacts_flagged,
        "signals_found": len(signals),
    }


async def _run_scrape(
    session: AsyncSession,
    job: Job,
    domain_provider: DomainDiscoveryProvider,
    company_provider: CompanyDataProvider,
    contact_provider: ContactDataProvider,
    signal_provider: SignalDataProvider,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Per-company scrape job: resolves the target company from the job payload, then
    delegates to the shared `_enrich_company` pipeline."""
    payload = job.payload or {}
    company_id = uuid.UUID(payload["company_id"])
    company = await session.get(Company, company_id)
    if company is None:
        raise ValueError(f"company {company_id} not found")

    return await _enrich_company(
        session,
        job.organization_id,
        company,
        domain_provider,
        company_provider,
        contact_provider,
        signal_provider,
        progress_callback,
    )


async def process_scrape_company_job(
    session: AsyncSession, job: Job, progress_callback: ProgressCallback | None = None
) -> dict[str, Any]:
    """Handler registered with the job worker — builds the real (network-calling) providers
    and delegates to `_run_scrape`."""
    settings = get_settings()
    domain_provider = SerperSearchProvider(settings)
    scraper = WebsiteScraperProvider(settings)
    try:
        return await _run_scrape(
            session, job, domain_provider, scraper, scraper, scraper, progress_callback
        )
    finally:
        await scraper.aclose()


async def list_company_signals(
    session: AsyncSession, organization_id: uuid.UUID, company_id: uuid.UUID
) -> list[EnrichmentRecord]:
    """EnrichmentRecord is an append-only provenance log by design — re-scraping a company adds
    new rows rather than overwriting old ones, so the same signal can appear once per scrape.
    That's correct for audit history, but not for what a user should see: dedupe here on
    (signal_type, text), keeping only the most recent occurrence of each."""
    company = await session.get(Company, company_id)
    if company is None or company.organization_id != organization_id:
        return []
    stmt = (
        select(EnrichmentRecord)
        .where(
            EnrichmentRecord.organization_id == organization_id,
            EnrichmentRecord.entity_type == ENTITY_TYPE_COMPANY,
            EnrichmentRecord.entity_id == company_id,
            EnrichmentRecord.source.like("scraper:companysite:signals:%"),
        )
        .order_by(EnrichmentRecord.fetched_at.desc())
    )
    records = (await session.execute(stmt)).scalars().all()

    deduped: list[EnrichmentRecord] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        key = (record.raw_payload.get("signal_type", ""), record.raw_payload.get("text", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped
