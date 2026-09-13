from sqlalchemy import select

from app.modules.companies.models import ENRICHMENT_STATUS_ENRICHED, ENRICHMENT_STATUS_FAILED
from app.modules.companies.service import get_or_create_company
from app.modules.contacts.models import Contact
from app.modules.enrichment.models import EnrichmentRecord
from app.modules.enrichment.providers.base import (
    DomainMatch,
    FetchedPage,
    ScrapedCompanyData,
    ScrapedContact,
    ScrapedSignal,
)
from app.modules.enrichment.providers.mock import (
    MockCompanyDataProvider,
    MockContactDataProvider,
    MockDomainDiscoveryProvider,
    MockSignalDataProvider,
)
from app.modules.enrichment.service import (
    JOB_TYPE_SCRAPE_COMPANY,
    _run_scrape,
    list_company_signals,
)
from app.modules.jobs.service import enqueue_job

_PAGE = FetchedPage(url="https://acme.com/", status_code=200, text="<html></html>")


async def _make_job(session, organization_id, company_id):
    return await enqueue_job(
        session, organization_id, JOB_TYPE_SCRAPE_COMPANY, {"company_id": str(company_id)}
    )


async def test_scrape_with_existing_domain_and_verified_contact_is_not_flagged(
    db_session, organization_id
) -> None:
    company, _ = await get_or_create_company(
        db_session, organization_id, name="Acme", domain="acme.com"
    )
    await db_session.commit()
    job = await _make_job(db_session, organization_id, company.id)

    result = await _run_scrape(
        db_session,
        job,
        domain_provider=MockDomainDiscoveryProvider(),
        company_provider=MockCompanyDataProvider(
            ScrapedCompanyData(description="We build widgets.", pages_fetched=[_PAGE])
        ),
        contact_provider=MockContactDataProvider(
            [ScrapedContact(full_name="Jane Doe", role_title="CEO", email="jane@acme.com")]
        ),
        signal_provider=MockSignalDataProvider(),
    )

    assert result["status"] == ENRICHMENT_STATUS_ENRICHED
    assert result["contacts_found"] == 1
    assert result["contacts_flagged"] == 0

    await db_session.refresh(company)
    assert company.enrichment_status == ENRICHMENT_STATUS_ENRICHED
    assert company.needs_review is False
    assert company.description == "We build widgets."

    records = (await db_session.execute(select(EnrichmentRecord))).scalars().all()
    assert len(records) == 1
    assert records[0].source == "scraper:companysite:https://acme.com/"


async def test_domain_discovered_via_search_flags_company_needs_review(
    db_session, organization_id
) -> None:
    company, _ = await get_or_create_company(db_session, organization_id, name="Acme", domain=None)
    await db_session.commit()
    job = await _make_job(db_session, organization_id, company.id)

    result = await _run_scrape(
        db_session,
        job,
        domain_provider=MockDomainDiscoveryProvider(
            DomainMatch(domain="acme.com", confidence="fuzzy")
        ),
        company_provider=MockCompanyDataProvider(ScrapedCompanyData(pages_fetched=[_PAGE])),
        contact_provider=MockContactDataProvider([]),
        signal_provider=MockSignalDataProvider(),
    )

    assert result["status"] == ENRICHMENT_STATUS_ENRICHED
    assert result["domain_discovered"] is True

    await db_session.refresh(company)
    assert company.domain == "acme.com"
    assert company.needs_review is True
    assert company.needs_review_reason == "domain found via search API, not confirmed"


async def test_no_domain_and_no_search_match_marks_enrichment_failed(
    db_session, organization_id
) -> None:
    company, _ = await get_or_create_company(db_session, organization_id, name="Acme", domain=None)
    await db_session.commit()
    job = await _make_job(db_session, organization_id, company.id)

    result = await _run_scrape(
        db_session,
        job,
        domain_provider=MockDomainDiscoveryProvider(None),
        company_provider=MockCompanyDataProvider(),
        contact_provider=MockContactDataProvider([]),
        signal_provider=MockSignalDataProvider(),
    )

    assert result["status"] == ENRICHMENT_STATUS_FAILED
    await db_session.refresh(company)
    assert company.enrichment_status == ENRICHMENT_STATUS_FAILED
    assert company.enrichment_error == "no domain on file and none found"
    assert company.needs_review is False  # a failure, not an ambiguous match


async def test_contact_found_without_email_is_flagged_needs_review(
    db_session, organization_id
) -> None:
    company, _ = await get_or_create_company(
        db_session, organization_id, name="Acme", domain="acme.com"
    )
    await db_session.commit()
    job = await _make_job(db_session, organization_id, company.id)

    result = await _run_scrape(
        db_session,
        job,
        domain_provider=MockDomainDiscoveryProvider(),
        company_provider=MockCompanyDataProvider(ScrapedCompanyData(pages_fetched=[_PAGE])),
        contact_provider=MockContactDataProvider(
            [ScrapedContact(full_name="Jane Doe", role_title="CEO", email=None)]
        ),
        signal_provider=MockSignalDataProvider(),
    )

    assert result["contacts_flagged"] == 1

    contact = (
        await db_session.execute(select(Contact).where(Contact.company_id == company.id))
    ).scalar_one()
    assert contact.needs_review is True
    assert contact.needs_review_reason == "no verified email found"


async def test_signals_are_stored_as_enrichment_records(db_session, organization_id) -> None:
    company, _ = await get_or_create_company(
        db_session, organization_id, name="Acme", domain="acme.com"
    )
    await db_session.commit()
    job = await _make_job(db_session, organization_id, company.id)

    result = await _run_scrape(
        db_session,
        job,
        domain_provider=MockDomainDiscoveryProvider(),
        company_provider=MockCompanyDataProvider(ScrapedCompanyData(pages_fetched=[_PAGE])),
        contact_provider=MockContactDataProvider([]),
        signal_provider=MockSignalDataProvider(
            [
                ScrapedSignal(
                    signal_type="job_posting",
                    text="Senior Sales Ops Manager",
                    url="https://acme.com/careers",
                    date=None,
                ),
                ScrapedSignal(
                    signal_type="news",
                    text="Acme raises $10M Series A",
                    url="https://acme.com/press",
                    date="2026-01-15",
                ),
            ]
        ),
    )

    assert result["signals_found"] == 2

    records = (
        await db_session.execute(
            select(EnrichmentRecord).where(
                EnrichmentRecord.source.like("scraper:companysite:signals:%")
            )
        )
    ).scalars().all()
    assert len(records) == 2
    payloads = {r.raw_payload["signal_type"]: r.raw_payload for r in records}
    assert payloads["job_posting"]["text"] == "Senior Sales Ops Manager"
    assert payloads["news"]["date"] == "2026-01-15"


async def test_list_company_signals_dedupes_across_rescrapes(db_session, organization_id) -> None:
    company, _ = await get_or_create_company(
        db_session, organization_id, name="Acme", domain="acme.com"
    )
    await db_session.commit()

    same_signal = ScrapedSignal(
        signal_type="job_posting",
        text="Senior Sales Ops Manager",
        url="https://acme.com/careers",
        date=None,
    )
    for _ in range(2):  # simulate two separate scrapes finding the same signal
        job = await _make_job(db_session, organization_id, company.id)
        await _run_scrape(
            db_session,
            job,
            domain_provider=MockDomainDiscoveryProvider(),
            company_provider=MockCompanyDataProvider(ScrapedCompanyData(pages_fetched=[_PAGE])),
            contact_provider=MockContactDataProvider([]),
            signal_provider=MockSignalDataProvider([same_signal]),
        )
        await db_session.commit()

    # Both scrapes wrote their own EnrichmentRecord (append-only provenance log)...
    raw_records = (
        await db_session.execute(
            select(EnrichmentRecord).where(
                EnrichmentRecord.source.like("scraper:companysite:signals:%")
            )
        )
    ).scalars().all()
    assert len(raw_records) == 2

    # ...but the user-facing list collapses to one, keeping the latest occurrence.
    signals = await list_company_signals(db_session, organization_id, company.id)
    assert len(signals) == 1
