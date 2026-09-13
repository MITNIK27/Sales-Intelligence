from app.modules.companies.models import ENRICHMENT_STATUS_ENRICHED, ENRICHMENT_STATUS_PENDING
from app.modules.companies.service import get_or_create_company
from app.modules.enrichment.providers.base import ScrapedCompanyData, ScrapedContact
from app.modules.enrichment.providers.mock import (
    MockCompanyDataProvider,
    MockContactDataProvider,
    MockDomainDiscoveryProvider,
    MockSignalDataProvider,
)
from app.modules.enrichment.service import (
    JOB_TYPE_SCRAPE_COMPANY,
    _run_scrape,
    list_needs_review,
    start_bulk_scrape,
    start_company_scrape,
)
from app.modules.jobs.worker import _HANDLERS


def test_scrape_company_job_type_is_registered_with_worker() -> None:
    assert JOB_TYPE_SCRAPE_COMPANY in _HANDLERS


async def test_trigger_scrape_sets_pending_status_and_enqueues_job(
    db_session, organization_id
) -> None:
    company, _ = await get_or_create_company(
        db_session, organization_id, name="Acme", domain="acme.com"
    )
    await db_session.commit()

    job = await start_company_scrape(db_session, organization_id, company.id)
    await db_session.commit()

    assert job is not None
    assert job.job_type == JOB_TYPE_SCRAPE_COMPANY
    assert job.payload == {"company_id": str(company.id)}
    await db_session.refresh(company)
    assert company.enrichment_status == ENRICHMENT_STATUS_PENDING


async def test_full_scrape_flow_surfaces_flagged_items_on_needs_review(
    db_session, organization_id
) -> None:
    # Company with no domain -> discovered via search (fuzzy) -> flagged.
    company, _ = await get_or_create_company(db_session, organization_id, name="Acme", domain=None)
    await db_session.commit()

    from app.modules.enrichment.providers.base import DomainMatch, FetchedPage

    job = await start_company_scrape(db_session, organization_id, company.id)
    await db_session.commit()

    result = await _run_scrape(
        db_session,
        job,
        domain_provider=MockDomainDiscoveryProvider(
            DomainMatch(domain="acme.com", confidence="fuzzy")
        ),
        company_provider=MockCompanyDataProvider(
            ScrapedCompanyData(
                pages_fetched=[FetchedPage(url="https://acme.com/", status_code=200, text="")]
            )
        ),
        contact_provider=MockContactDataProvider(
            [ScrapedContact(full_name="Jane Doe", role_title="CEO", email=None)]
        ),
        signal_provider=MockSignalDataProvider(),
    )
    await db_session.commit()

    assert result["status"] == ENRICHMENT_STATUS_ENRICHED

    review_items = await list_needs_review(db_session, organization_id)
    entity_types = {item.entity_type for item in review_items}
    assert entity_types == {"company", "contact"}


async def test_bulk_scrape_enqueues_only_never_enriched_and_failed_companies(
    db_session, organization_id
) -> None:
    never_enriched, _ = await get_or_create_company(
        db_session, organization_id, name="Never Enriched Co", domain="never.example.com"
    )
    already_enriched, _ = await get_or_create_company(
        db_session, organization_id, name="Already Enriched Co", domain="done.example.com"
    )
    already_enriched.enrichment_status = ENRICHMENT_STATUS_ENRICHED
    await db_session.commit()

    enqueued_count = await start_bulk_scrape(db_session, organization_id)
    await db_session.commit()

    assert enqueued_count == 1
    await db_session.refresh(never_enriched)
    assert never_enriched.enrichment_status == "pending"
