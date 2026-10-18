import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
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
from app.modules.contacts.models import CHANNEL_TYPE_EMAIL, CHANNEL_TYPE_LINKEDIN, Contact
from app.modules.contacts.service import get_or_create_contact, upsert_contact_channel
from app.modules.enrichment.models import ENTITY_TYPE_COMPANY, EnrichmentRecord
from app.modules.enrichment.providers.base import (
    CompanyDataProvider,
    ContactDataProvider,
    DomainDiscoveryProvider,
    FetchedPage,
    ScrapedCompanyData,
    ScrapedContact,
    ScrapedSignal,
    SignalDataProvider,
)
from app.modules.enrichment.providers.context_dev import SOURCE_LABEL_BRAND, SOURCE_LABEL_NEWS
from app.modules.enrichment.providers.factory import build_company_providers
from app.modules.enrichment.providers.search_contacts import (
    ContactSearchProvider,
    SerperContactSearchProvider,
)
from app.modules.enrichment.providers.search_serper import SerperSearchProvider
from app.modules.enrichment.providers.website_scraper import WebsiteScraperProvider
from app.modules.enrichment.signals import (
    is_clean_payload,
    normalize_signals,
    normalize_title,
    parse_published,
)
from app.modules.jobs.models import Job
from app.modules.jobs.service import enqueue_job

JOB_TYPE_SCRAPE_COMPANY = "scrape_company"

# EnrichmentRecord.source is VARCHAR(100). Third-party news URLs (context.dev signals) routinely
# exceed that on their own, and an over-long insert aborts the whole pipeline job. The full URL
# is always kept in the record's raw_payload; `source` only needs the label prefix that
# `list_company_signals` filters on, so the tail is what gets cut.
_SOURCE_MAX_LEN = 100


def _record_source(label: str, detail: str) -> str:
    return f"{label}:{detail}"[:_SOURCE_MAX_LEN]


# How much a field is trusted by where it came from: a structured brand record beats text pulled
# from page HTML. Shown with the field so a rep can weigh it; not used to gate anything.
def _source_confidence(source: str) -> float:
    if source.startswith("contextdev:brand"):
        return 0.9
    if source.startswith("contextdev"):
        return 0.8
    return 0.7

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
    # Who the flagged contact is, so a rep can judge it without opening the company: all optional,
    # since a company-level flag has no contact.
    contact_title: str | None = None
    contact_email: str | None = None
    contact_linkedin: str | None = None
    contact_source: str | None = None
    contact_confidence: float | None = None
    company_domain: str | None = None


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
                company_domain=company.domain,
            )
        )

    contact_stmt = (
        select(Contact)
        .where(Contact.organization_id == organization_id, Contact.needs_review.is_(True))
        .options(selectinload(Contact.company), selectinload(Contact.channels))
    )
    for contact in (await session.execute(contact_stmt)).scalars().all():
        by_type = {channel.channel_type: channel.value for channel in contact.channels}
        entries.append(
            NeedsReviewEntry(
                entity_type="contact",
                company_id=contact.company_id,
                company_name=contact.company.name,
                contact_id=contact.id,
                contact_name=contact.full_name,
                reason=contact.needs_review_reason or "",
                flagged_at=contact.updated_at,
                contact_title=contact.role_title,
                contact_email=by_type.get(CHANNEL_TYPE_EMAIL),
                contact_linkedin=by_type.get(CHANNEL_TYPE_LINKEDIN),
                contact_source=contact.source,
                contact_confidence=contact.confidence,
                company_domain=contact.company.domain,
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
    contact_search_provider: ContactSearchProvider | None = None,
) -> dict[str, Any]:
    """The testable core of company enrichment — domain resolution, firmographics, contacts,
    signals. Takes providers explicitly so tests can inject mocks instead of hitting the
    network. Shared by both the per-company scrape job (`_run_scrape`) and the Market Discovery
    job's per-candidate enrichment step, so this pipeline exists exactly once.

    `contact_search_provider` is optional and additive — when given, supplements the website
    scraper's on-page contacts with search-derived ones (see
    `enrichment/providers/search_contacts.py`), deduped against existing contacts for free by
    `get_or_create_contact`'s own (company_id, normalized name) matching. `None` (the default)
    just means this pipeline runs exactly as it did before this capability existed."""
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

    # Company data, signals and contact search are INDEPENDENT branches: a blocked website must
    # not cost us the contacts or the news, and a failing news source must not fail the company.
    # They run concurrently (network only); every database write happens afterwards, in order,
    # because the session is not safe to share across concurrent tasks.
    async def _no_search() -> list[ScrapedContact]:
        return []

    company_result, signals_result, search_result = await asyncio.gather(
        company_provider.fetch_company_data(domain),
        signal_provider.fetch_signals(domain),
        contact_search_provider.search_contacts(company.name, domain)
        if contact_search_provider is not None
        else _no_search(),
        return_exceptions=True,
    )
    await tick()

    branch_errors: dict[str, str] = {}
    company_data: ScrapedCompanyData | None = None
    if isinstance(company_result, BaseException):
        branch_errors["company_data"] = str(company_result)
    else:
        company_data = company_result
    signals: list[ScrapedSignal] = []
    if isinstance(signals_result, BaseException):
        branch_errors["signals"] = str(signals_result)
    else:
        signals = signals_result
    searched_contacts: list[ScrapedContact] = []
    if isinstance(search_result, BaseException):
        branch_errors["contact_search"] = str(search_result)
    else:
        searched_contacts = search_result

    if not company.domain:
        company.domain = domain
    if domain_discovered:
        company.needs_review = True
        company.needs_review_reason = "domain found via search API, not confirmed"

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    pages: list[FetchedPage] = []
    if company_data is not None:
        pages = company_data.pages_fetched
        provenance = dict(company.field_provenance or {})
        for field_name in ("description", "employee_count_range", "industry"):
            value = getattr(company_data, field_name)
            if not getattr(company, field_name) and value:
                setattr(company, field_name, value)
                source = company_data.field_sources.get(field_name, company_data.source_label)
                provenance[field_name] = {
                    "source": source,
                    "confidence": _source_confidence(source),
                    "fetched_at": now_iso,
                }
        company.field_provenance = provenance

        for page in pages:
            session.add(
                EnrichmentRecord(
                    organization_id=organization_id,
                    entity_type=ENTITY_TYPE_COMPANY,
                    entity_id=company.id,
                    source=_record_source(company_data.source_label, page.url),
                    raw_payload={
                        "url": page.url,
                        "status_code": page.status_code,
                        "description": company_data.description,
                        "employee_count_range": company_data.employee_count_range,
                    },
                    fetched_at=now,
                )
            )
        if company_data.raw_brand is not None:
            session.add(
                EnrichmentRecord(
                    organization_id=organization_id,
                    entity_type=ENTITY_TYPE_COMPANY,
                    entity_id=company.id,
                    source=_record_source(SOURCE_LABEL_BRAND, domain),
                    raw_payload=company_data.raw_brand,
                    fetched_at=now,
                )
            )

    contacts_found = 0
    contacts_flagged = 0
    scraped_contacts: list[ScrapedContact] = []
    try:
        scraped_contacts = await contact_provider.fetch_contacts(domain, pages)
    except Exception as exc:  # noqa: BLE001 - one branch's failure must not sink the company
        branch_errors["page_contacts"] = str(exc)
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

    for searched in searched_contacts:
        async with session.begin_nested():
            created = await _store_searched_contact(session, organization_id, company, searched)
            if created:
                contacts_found += 1
                contacts_flagged += 1
    await tick()

    raw_signal_count = len(signals)
    signals = normalize_signals(signals)
    for signal in signals:
        session.add(
            EnrichmentRecord(
                organization_id=organization_id,
                entity_type=ENTITY_TYPE_COMPANY,
                entity_id=company.id,
                source=_record_source(f"{signal.source_label}:signals", signal.url),
                raw_payload={
                    "signal_type": signal.signal_type,
                    "text": signal.text,
                    "url": signal.url,
                    "date": signal.date,
                    "summary": signal.summary,
                    "provider": signal.source_label,
                },
                fetched_at=now,
            )
        )
    await tick()

    if company_data is None:
        # No firmographics from any provider. The contacts and signals gathered above are kept,
        # but the company itself is marked failed so it can be retried.
        company.enrichment_status = ENRICHMENT_STATUS_FAILED
        company.enrichment_error = branch_errors.get("company_data", "no company data")
        await session.flush()
        return {
            "status": ENRICHMENT_STATUS_FAILED,
            "reason": company.enrichment_error,
            "contacts_found": contacts_found,
            "signals_found": len(signals),
            "branch_errors": branch_errors,
        }

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
        "signals_filtered_out": raw_signal_count - len(signals),
        "firmographics_source": company_data.source_label,
        "industry_filled": bool(company.industry),
        "branch_errors": branch_errors,
    }


async def _store_searched_contact(
    session: AsyncSession,
    organization_id: uuid.UUID,
    company: Company,
    searched: ScrapedContact,
) -> bool:
    """Saves one search-found person: the contact (flagged for the rep's confirmation - nothing
    found by search is ever treated as verified), its source and confidence, and its LinkedIn
    profile as a channel. Returns True when a new contact was created."""
    contact, created = await get_or_create_contact(
        session,
        organization_id,
        company_id=company.id,
        full_name=searched.full_name,
        role_title=searched.role_title,
        email=None,
    )
    if created:
        settings = get_settings()
        contact.needs_review = True
        if searched.confidence is None:
            contact.needs_review_reason = "found via contact search, not confirmed"
        elif searched.confidence >= settings.contact_confidence_likely:
            contact.needs_review_reason = "found via contact search (likely match), not confirmed"
        else:
            contact.needs_review_reason = (
                "found via contact search, low confidence - check the company"
            )
        contact.source = searched.source
        contact.confidence = searched.confidence
    if searched.linkedin_url:
        await upsert_contact_channel(
            session,
            contact.id,
            CHANNEL_TYPE_LINKEDIN,
            searched.linkedin_url,
            source=searched.source,
        )
    return created


async def search_company_contacts(
    session: AsyncSession,
    organization_id: uuid.UUID,
    company_id: uuid.UUID,
    contact_search_provider: ContactSearchProvider,
) -> list[Contact] | None:
    """The manual, on-demand counterpart to the automatic search-contacts step inside
    `_enrich_company` — a rep triggering a search for one specific company at will, independent
    of a full (re-)enrichment run. Fast enough (one Serper call + parsing) to stay synchronous,
    same "fast stays synchronous, slow becomes a job" convention already used for role-relevance
    classification. Returns `None` if the company doesn't exist; otherwise the list of newly
    found-or-matched contacts (same dedup-by-name behavior as the automatic path)."""
    company = await session.get(Company, company_id)
    if company is None or company.organization_id != organization_id:
        return None

    searched_contacts = await contact_search_provider.search_contacts(
        company.name, company.domain
    )
    found_ids: list[uuid.UUID] = []
    for searched in searched_contacts:
        await _store_searched_contact(session, organization_id, company, searched)
        contact, _ = await get_or_create_contact(
            session,
            organization_id,
            company_id=company.id,
            full_name=searched.full_name,
            role_title=searched.role_title,
            email=None,
        )
        found_ids.append(contact.id)
    await session.flush()
    if not found_ids:
        return []

    # Re-fetched with `channels` eager-loaded — a matched *existing* contact (created=False) may
    # already have channels from prior website scraping, and lazily loading them later during
    # response serialization (after this function's caller commits) would hit the same
    # MissingGreenlet failure already fixed once elsewhere in this codebase (outreach/service.py).
    stmt = (
        select(Contact)
        .where(Contact.id.in_(found_ids))
        .options(selectinload(Contact.channels))
    )
    return list((await session.execute(stmt)).scalars().all())


async def _run_scrape(
    session: AsyncSession,
    job: Job,
    domain_provider: DomainDiscoveryProvider,
    company_provider: CompanyDataProvider,
    contact_provider: ContactDataProvider,
    signal_provider: SignalDataProvider,
    progress_callback: ProgressCallback | None = None,
    contact_search_provider: ContactSearchProvider | None = None,
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
        contact_search_provider,
    )


async def process_scrape_company_job(
    session: AsyncSession, job: Job, progress_callback: ProgressCallback | None = None
) -> dict[str, Any]:
    """Handler registered with the job worker — builds the real (network-calling) providers
    and delegates to `_run_scrape`."""
    settings = get_settings()
    domain_provider = SerperSearchProvider(settings)
    scraper = WebsiteScraperProvider(settings)
    providers = build_company_providers(settings, scraper)
    contact_search_provider = SerperContactSearchProvider(settings, domain_provider)
    try:
        return await _run_scrape(
            session,
            job,
            domain_provider,
            providers.company,
            scraper,
            providers.signals,
            progress_callback,
            contact_search_provider,
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
            or_(
                EnrichmentRecord.source.like("scraper:companysite:signals:%"),
                EnrichmentRecord.source.like(f"{SOURCE_LABEL_NEWS}:signals:%"),
            ),
        )
        .order_by(EnrichmentRecord.fetched_at.desc())
    )
    records = (await session.execute(stmt)).scalars().all()

    deduped: list[EnrichmentRecord] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        payload = record.raw_payload or {}
        if not is_clean_payload(payload):
            continue  # page chrome stored before filtering existed
        key = (payload.get("signal_type", ""), normalize_title(str(payload.get("text", ""))))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)

    # Newest story first by its own publication date (undated ones keep fetch order, last).
    def _recency(record: EnrichmentRecord) -> float:
        published = parse_published((record.raw_payload or {}).get("date"))
        return published.timestamp() if published else float("-inf")

    deduped.sort(key=_recency, reverse=True)
    return deduped
