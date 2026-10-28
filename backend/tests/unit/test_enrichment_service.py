import uuid

from sqlalchemy import select

from app.modules.companies.models import ENRICHMENT_STATUS_ENRICHED, ENRICHMENT_STATUS_FAILED
from app.modules.companies.service import get_or_create_company
from app.modules.contacts.models import CHANNEL_TYPE_LINKEDIN, Contact
from app.modules.contacts.service import get_or_create_contact, upsert_contact_channel
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
    MockContactSearchProvider,
    MockDomainDiscoveryProvider,
    MockSignalDataProvider,
)
from app.modules.enrichment.service import (
    JOB_TYPE_SCRAPE_COMPANY,
    _run_scrape,
    list_company_signals,
    list_needs_review,
    search_company_contacts,
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


async def test_contact_search_provider_supplements_website_scraped_contacts(
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
            [ScrapedContact(full_name="Jane Doe", role_title="CEO", email="jane@acme.com")]
        ),
        signal_provider=MockSignalDataProvider(),
        contact_search_provider=MockContactSearchProvider(
            [ScrapedContact(full_name="John Smith", role_title="VP Sales")]
        ),
    )

    assert result["contacts_found"] == 2  # one scraped, one search-found
    assert result["contacts_flagged"] == 1  # only the search-found one lacks a verified email

    contacts = (await db_session.execute(select(Contact))).scalars().all()
    by_name = {c.full_name: c for c in contacts}
    assert set(by_name) == {"Jane Doe", "John Smith"}
    assert by_name["John Smith"].needs_review is True
    assert by_name["John Smith"].needs_review_reason == "found via contact search, not confirmed"


async def test_contact_search_provider_dedupes_against_already_scraped_contact(
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
            [ScrapedContact(full_name="Jane Doe", role_title="CEO", email="jane@acme.com")]
        ),
        signal_provider=MockSignalDataProvider(),
        # Same person, found again via search — should dedupe by (company, normalized name)
        # rather than creating a second row.
        contact_search_provider=MockContactSearchProvider(
            [ScrapedContact(full_name="jane doe", role_title="Chief Executive Officer")]
        ),
    )

    assert result["contacts_found"] == 1  # not 2 — the search hit matched the existing contact
    contacts = (await db_session.execute(select(Contact))).scalars().all()
    assert len(contacts) == 1
    assert contacts[0].needs_review is False  # the original, verified-email contact untouched


async def test_search_company_contacts_returns_none_for_missing_company(
    db_session, organization_id
) -> None:
    result = await search_company_contacts(
        db_session, organization_id, uuid.uuid4(), MockContactSearchProvider([])
    )
    assert result is None


async def test_search_company_contacts_creates_and_flags_new_contacts(
    db_session, organization_id
) -> None:
    company, _ = await get_or_create_company(
        db_session, organization_id, name="Acme", domain="acme.com"
    )
    await db_session.commit()

    provider = MockContactSearchProvider(
        [ScrapedContact(full_name="Alex Chen", role_title="Head of Procurement")]
    )
    result = await search_company_contacts(db_session, organization_id, company.id, provider)

    assert result is not None
    assert len(result) == 1
    assert result[0].full_name == "Alex Chen"
    assert result[0].needs_review is True
    assert result[0].channels == []  # eager-loaded, not a lazy attribute needing a later fetch


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


async def test_needs_review_entries_carry_the_contact_details(db_session, organization_id) -> None:
    company, _ = await get_or_create_company(
        db_session, organization_id, name="Acme", domain="acme.com"
    )
    contact, _ = await get_or_create_contact(
        db_session, organization_id, company.id, "Jane Doe", "Head of Logistics", None
    )
    contact.needs_review = True
    contact.needs_review_reason = "found via contact search, not confirmed"
    contact.source = "serper:linkedin"
    contact.confidence = 0.8
    await upsert_contact_channel(
        db_session, contact.id, CHANNEL_TYPE_LINKEDIN, "https://linkedin.com/in/jane"
    )
    await db_session.commit()

    entries = await list_needs_review(db_session, organization_id)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.entity_type == "contact"
    assert entry.contact_name == "Jane Doe"
    assert entry.contact_title == "Head of Logistics"
    assert entry.contact_source == "serper:linkedin"
    assert entry.contact_confidence == 0.8
    assert entry.contact_email is None
    assert entry.company_domain == "acme.com"


async def test_listing_needs_review_changes_nothing(db_session, organization_id) -> None:
    company, _ = await get_or_create_company(
        db_session, organization_id, name="Acme", domain="acme.com"
    )
    contact, _ = await get_or_create_contact(
        db_session, organization_id, company.id, "Jane Doe", None, None
    )
    contact.needs_review = True
    await db_session.commit()

    await list_needs_review(db_session, organization_id)
    await db_session.refresh(contact)

    assert contact.needs_review is True
