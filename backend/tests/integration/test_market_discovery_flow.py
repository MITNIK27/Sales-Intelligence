from datetime import UTC, datetime

from sqlalchemy import select

from app.modules.ai_recommendation.gemini_client import (
    MarketCriteria as ParsedMarketCriteria,
)
from app.modules.ai_recommendation.gemini_client import (
    ParsedListField,
    ParsedOptionalStrField,
)
from app.modules.ai_recommendation.mock import MockMarketDescriptionParser
from app.modules.companies.models import Company
from app.modules.discovery_agent.schemas import DiscoveredCompany
from app.modules.discovery_agent.testing import StubCompanyDiscoveryAgent
from app.modules.enrichment.providers.base import ScrapedCompanyData
from app.modules.enrichment.providers.mock import (
    MockCompanyDataProvider,
    MockContactDataProvider,
    MockDomainDiscoveryProvider,
    MockSignalDataProvider,
)
from app.modules.ingestion.market_discovery import (
    CANDIDATE_LIMIT,
    JOB_TYPE_MARKET_DISCOVERY,
    _run_market_discovery,
    confirm_market_discovery,
    start_market_discovery_parse,
)
from app.modules.ingestion.models import (
    STATUS_AWAITING_CONFIRMATION,
    STATUS_DONE,
    STATUS_PENDING,
    IngestionRun,
)
from app.modules.jobs.models import Job
from app.modules.jobs.worker import _HANDLERS


def test_market_discovery_job_type_is_registered_with_worker() -> None:
    assert JOB_TYPE_MARKET_DISCOVERY in _HANDLERS


def _job(organization_id, run: IngestionRun) -> Job:
    """Confirming a run no longer enqueues a job itself (the router does, as an `auto_pipeline`
    job, to avoid a circular import between `ingestion` and `orchestrator`) — these tests build
    the plain `market_discovery`-job payload `_run_market_discovery` itself still expects."""
    return Job(
        organization_id=organization_id,
        job_type=JOB_TYPE_MARKET_DISCOVERY,
        payload={"ingestion_run_id": str(run.id)},
    )


_CRITERIA = ParsedMarketCriteria(
    industry_keywords=ParsedListField(value=["SaaS"], confidence="confident"),
    location=ParsedOptionalStrField(value="Bangalore", confidence="confident"),
    employee_size_range=ParsedOptionalStrField(value="50-200", confidence="confident"),
)


async def test_parse_stores_raw_input_and_parsed_fields_awaiting_confirmation(
    db_session, organization_id
) -> None:
    parser = MockMarketDescriptionParser(_CRITERIA)
    run = await start_market_discovery_parse(
        db_session, organization_id, "SaaS companies in Bangalore, 50-200 employees", parser
    )
    await db_session.commit()

    assert run.status == STATUS_AWAITING_CONFIRMATION
    assert run.raw_input == "SaaS companies in Bangalore, 50-200 employees"
    assert run.parsed_fields is not None
    assert run.parsed_fields["location"]["value"] == "Bangalore"
    assert run.confirmed_at is None


async def test_confirm_sets_confirmed_at_and_parsed_fields(db_session, organization_id) -> None:
    parser = MockMarketDescriptionParser(_CRITERIA)
    run = await start_market_discovery_parse(
        db_session, organization_id, "SaaS in Bangalore", parser
    )
    await db_session.commit()

    confirmed = await confirm_market_discovery(
        db_session,
        organization_id,
        run.id,
        industry_keywords=["SaaS", "fintech"],  # user corrected/added a keyword
        location="Bangalore",
        employee_size_range="50-200",
    )
    await db_session.commit()

    assert confirmed is not None
    assert confirmed.id == run.id

    await db_session.refresh(run)
    assert run.status == STATUS_PENDING
    assert run.confirmed_at is not None
    assert run.parsed_fields["industry_keywords"]["value"] == ["SaaS", "fintech"]


async def test_market_discovery_job_creates_flagged_companies(db_session, organization_id) -> None:
    parser = MockMarketDescriptionParser(_CRITERIA)
    run = await start_market_discovery_parse(
        db_session, organization_id, "SaaS in Bangalore", parser
    )
    await db_session.commit()
    confirmed = await confirm_market_discovery(
        db_session,
        organization_id,
        run.id,
        industry_keywords=["SaaS"],
        location="Bangalore",
        employee_size_range="50-200",
    )
    await db_session.commit()
    assert confirmed is not None
    job = _job(organization_id, confirmed)

    # Acme carries the discovery agent's own low-confidence flag (e.g. the listicle-name
    # heuristic backstop) through to the created company; Globex has none, so it should reach
    # role classification/drafting without a rep having to confirm it first.
    result = await _run_market_discovery(
        db_session,
        job,
        discovery_agent=StubCompanyDiscoveryAgent(
            [
                DiscoveredCompany(
                    name="Acme Inc",
                    domain="acme.com",
                    source_snippet="Acme Inc",
                    needs_review=True,
                    needs_review_reason="structurally suspicious name",
                ),
                DiscoveredCompany(
                    name="Globex Corp", domain="globex.com", source_snippet="Globex Corp"
                ),
            ]
        ),
        domain_provider=MockDomainDiscoveryProvider(),
        company_provider=MockCompanyDataProvider(ScrapedCompanyData()),
        contact_provider=MockContactDataProvider([]),
        signal_provider=MockSignalDataProvider([]),
    )
    await db_session.commit()

    assert result["candidates_found"] == 2
    assert result["companies_created"] == 2
    assert result["accepted"] == 2
    assert result["rejected"] == 0

    companies = (
        await db_session.execute(
            select(Company).where(Company.organization_id == organization_id)
        )
    ).scalars().all()
    by_domain = {c.domain: c for c in companies}
    assert by_domain["acme.com"].needs_review is True
    assert by_domain["acme.com"].needs_review_reason == "structurally suspicious name"
    assert by_domain["acme.com"].name == "Acme Inc"
    assert by_domain["acme.com"].source_ingestion_run_id == run.id
    assert by_domain["globex.com"].needs_review is False
    assert by_domain["globex.com"].needs_review_reason is None

    await db_session.refresh(run)
    assert run.status == STATUS_DONE
    assert run.summary["candidates_found"] == 2
    assert run.summary["companies_created"] == 2
    assert run.summary["reused_from_index"] == 0


async def test_market_discovery_skips_already_known_companies(db_session, organization_id) -> None:
    existing = Company(organization_id=organization_id, name="Acme", domain="acme.com")
    db_session.add(existing)
    await db_session.commit()

    parser = MockMarketDescriptionParser(_CRITERIA)
    run = await start_market_discovery_parse(
        db_session, organization_id, "SaaS in Bangalore", parser
    )
    await db_session.commit()
    confirmed = await confirm_market_discovery(
        db_session, organization_id, run.id, industry_keywords=["SaaS"], location=None,
        employee_size_range=None,
    )
    await db_session.commit()
    assert confirmed is not None
    job = _job(organization_id, confirmed)

    result = await _run_market_discovery(
        db_session,
        job,
        discovery_agent=StubCompanyDiscoveryAgent(
            [DiscoveredCompany(name="Acme Inc", domain="acme.com", source_snippet="Acme Inc")]
        ),
        domain_provider=MockDomainDiscoveryProvider(),
        company_provider=MockCompanyDataProvider(ScrapedCompanyData()),
        contact_provider=MockContactDataProvider([]),
        signal_provider=MockSignalDataProvider([]),
    )
    await db_session.commit()

    assert result["candidates_found"] == 1
    assert result["companies_created"] == 0  # already existed, not re-flagged

    await db_session.refresh(existing)
    assert existing.needs_review is False


async def test_market_discovery_reuses_indexed_companies_and_reduces_live_search(
    db_session, organization_id
) -> None:
    existing = Company(
        organization_id=organization_id,
        name="Acme",
        domain="acme.com",
        industry="SaaS",
        last_enriched_at=datetime.now(UTC),
    )
    db_session.add(existing)
    await db_session.commit()

    parser = MockMarketDescriptionParser(_CRITERIA)
    run = await start_market_discovery_parse(
        db_session, organization_id, "SaaS in Bangalore", parser
    )
    await db_session.commit()
    confirmed = await confirm_market_discovery(
        db_session,
        organization_id,
        run.id,
        industry_keywords=["SaaS"],
        location=None,
        employee_size_range=None,
    )
    await db_session.commit()
    assert confirmed is not None
    job = _job(organization_id, confirmed)

    discovery_agent = StubCompanyDiscoveryAgent(
        [DiscoveredCompany(name="Globex Corp", domain="globex.com", source_snippet="Globex Corp")]
    )
    result = await _run_market_discovery(
        db_session,
        job,
        discovery_agent=discovery_agent,
        domain_provider=MockDomainDiscoveryProvider(),
        company_provider=MockCompanyDataProvider(ScrapedCompanyData()),
        contact_provider=MockContactDataProvider([]),
        signal_provider=MockSignalDataProvider([]),
    )
    await db_session.commit()

    assert result["reused_from_index"] == 1
    assert result["companies_created"] == 1  # globex.com is genuinely new
    assert discovery_agent.calls[-1][1] == CANDIDATE_LIMIT - 1


async def test_market_discovery_skips_live_search_entirely_when_index_fills_the_limit(
    db_session, organization_id
) -> None:
    for i in range(CANDIDATE_LIMIT):
        db_session.add(
            Company(
                organization_id=organization_id,
                name=f"Company {i}",
                domain=f"company{i}.com",
                industry="SaaS",
                last_enriched_at=datetime.now(UTC),
            )
        )
    await db_session.commit()

    parser = MockMarketDescriptionParser(_CRITERIA)
    run = await start_market_discovery_parse(
        db_session, organization_id, "SaaS in Bangalore", parser
    )
    await db_session.commit()
    confirmed = await confirm_market_discovery(
        db_session,
        organization_id,
        run.id,
        industry_keywords=["SaaS"],
        location=None,
        employee_size_range=None,
    )
    await db_session.commit()
    assert confirmed is not None
    job = _job(organization_id, confirmed)

    discovery_agent = StubCompanyDiscoveryAgent([])
    result = await _run_market_discovery(
        db_session,
        job,
        discovery_agent=discovery_agent,
        domain_provider=MockDomainDiscoveryProvider(),
        company_provider=MockCompanyDataProvider(ScrapedCompanyData()),
        contact_provider=MockContactDataProvider([]),
        signal_provider=MockSignalDataProvider([]),
    )
    await db_session.commit()

    assert result["reused_from_index"] == CANDIDATE_LIMIT
    assert discovery_agent.calls == []  # live discovery skipped entirely
