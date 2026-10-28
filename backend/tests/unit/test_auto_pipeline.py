import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.modules.ai_recommendation.gemini_client import (
    MarketCriteria as ParsedMarketCriteria,
)
from app.modules.ai_recommendation.gemini_client import ParsedListField, ParsedOptionalStrField
from app.modules.ai_recommendation.mock import MockMarketDescriptionParser
from app.modules.companies.models import Company
from app.modules.companies.service import confirm_company
from app.modules.discovery_agent.schemas import DiscoveredCompany
from app.modules.discovery_agent.testing import StubCompanyDiscoveryAgent
from app.modules.draft.mock import MockDraftGenerator
from app.modules.draft.service import list_drafts
from app.modules.enrichment.providers.base import ScrapedCompanyData, ScrapedContact
from app.modules.enrichment.providers.mock import (
    MockCompanyDataProvider,
    MockContactDataProvider,
    MockDomainDiscoveryProvider,
    MockSignalDataProvider,
)
from app.modules.ingestion.market_discovery import (
    confirm_market_discovery,
    start_market_discovery_parse,
)
from app.modules.jobs.models import Job
from app.modules.orchestrator.service import (
    JOB_TYPE_AUTO_PIPELINE,
    _run_auto_pipeline,
    classify_and_draft_company,
)
from app.modules.products.service import create_product
from app.modules.qualification.qualification_generator import (
    CriterionVerdict,
    QualificationJudgment,
)
from app.modules.qualification.service import create_criterion
from app.modules.role_relevance.mock import MockRoleRelevanceGenerator
from app.modules.role_relevance.service import create_category

_CRITERIA = ParsedMarketCriteria(
    industry_keywords=ParsedListField(value=["SaaS"], confidence="confident"),
    location=ParsedOptionalStrField(value=None, confidence="could_not_determine"),
    employee_size_range=ParsedOptionalStrField(value=None, confidence="could_not_determine"),
)


class _AllMetQualificationGenerator:
    """Judges every criterion "met" for every company -> always qualifies (no disqualifying
    criteria configured in these tests)."""

    @property
    def model_name(self) -> str:
        return "fake-model"

    async def generate(self, company, signals, criteria) -> QualificationJudgment:  # type: ignore[no-untyped-def]
        return QualificationJudgment(
            criteria_results=[
                CriterionVerdict(criterion_id=str(c.id), verdict="met", reasoning="r")
                for c in criteria
            ]
        )


async def _confirmed_run(db_session, organization_id, discovered: list[DiscoveredCompany]):
    parser = MockMarketDescriptionParser(_CRITERIA)
    run = await start_market_discovery_parse(
        db_session, organization_id, "SaaS companies", parser
    )
    await db_session.commit()
    confirmed = await confirm_market_discovery(
        db_session, organization_id, run.id,
        industry_keywords=["SaaS"], location=None, employee_size_range=None,
    )
    await db_session.commit()
    assert confirmed is not None
    return confirmed


def _pipeline_job(
    organization_id: uuid.UUID, run_id: uuid.UUID, product_id: uuid.UUID | None
) -> Job:
    return Job(
        organization_id=organization_id,
        job_type=JOB_TYPE_AUTO_PIPELINE,
        payload={
            "ingestion_run_id": str(run_id),
            "product_ids": [str(product_id)] if product_id else [],
        },
    )


def _providers(contacts: list[ScrapedContact]):
    return dict(
        domain_provider=MockDomainDiscoveryProvider(),
        company_provider=MockCompanyDataProvider(ScrapedCompanyData()),
        contact_provider=MockContactDataProvider(contacts),
        signal_provider=MockSignalDataProvider([]),
    )


async def test_happy_path_discovers_qualifies_and_then_classifies_and_drafts_once_confirmed(
    db_session, organization_id
) -> None:
    await create_criterion(
        db_session, organization_id, name="Some criterion", description=None,
        is_disqualifying=False, is_active=True,
    )
    await create_category(
        db_session, organization_id, name="Vendor / IT", description=None,
        is_primary_target=True, is_active=True,
    )
    product = await create_product(db_session, organization_id, name="Widget", description=None)
    await db_session.commit()

    run = await _confirmed_run(
        db_session, organization_id,
        [
            DiscoveredCompany(name="Acme Inc", domain="acme.com", source_snippet="Acme Inc"),
            DiscoveredCompany(name="Globex Corp", domain="globex.com", source_snippet="Globex"),
        ],
    )
    job = _pipeline_job(organization_id, run.id, product.id)

    result = await _run_auto_pipeline(
        db_session, job,
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
                    name="Globex Corp",
                    domain="globex.com",
                    source_snippet="Globex",
                    needs_review=True,
                    needs_review_reason="structurally suspicious name",
                ),
            ]
        ),
        qualification_generator=_AllMetQualificationGenerator(),
        role_relevance_generator=MockRoleRelevanceGenerator(),
        draft_generator=MockDraftGenerator(),
        **_providers(
            [
                ScrapedContact(
                    full_name="Jane Doe", role_title="Procurement Manager", email="jane@acme.com"
                )
            ]
        ),
    )
    await db_session.commit()

    assert result["discovery"]["companies_created"] == 2
    assert result["qualification"]["ran"] is True
    assert result["qualification"]["qualified"] == 2
    assert len(result["qualification"]["qualified_company_ids"]) == 2

    # Both companies here were flagged needs_review by the discovery agent itself (a confident,
    # unflagged match would proceed straight through instead) — classification and drafting must
    # not run on them yet, however qualified they are, until a rep confirms each one.
    assert result["role_classification"]["ran"] is True
    assert result["role_classification"]["companies_classified"] == 0
    assert len(result["role_classification"]["skipped_needs_review"]) == 2
    assert result["drafting"] == {
        "ran": False,
        "skipped_reason": "no primary-target contacts identified",
    }
    assert result["needs_review_summary"]["companies_skipped_at_role_classification"] == 2
    assert result["capped"] is False

    acme = (
        await db_session.execute(select(Company).where(Company.domain == "acme.com"))
    ).scalars().one()
    globex = (
        await db_session.execute(select(Company).where(Company.domain == "globex.com"))
    ).scalars().one()
    assert acme.needs_review is True
    assert len(await list_drafts(db_session, organization_id, acme.id)) == 0

    # A rep reviews and confirms each company — this should resume classification + drafting for
    # it in one action, exactly like the `POST /companies/{id}/confirm` endpoint does.
    for company in (acme, globex):
        confirmed = await confirm_company(db_session, organization_id, company.id)
        assert confirmed is not None
        resumed = await classify_and_draft_company(
            db_session, organization_id, company.id,
            MockRoleRelevanceGenerator(), MockDraftGenerator(), [product.id],
        )
        await db_session.commit()
        assert resumed["role_classification"]["ran"] is True
        assert resumed["drafting"]["ran"] is True
        assert resumed["drafting"]["drafts_generated"] == 1

    # Sanity: real Draft rows were actually persisted, not just counted.
    drafts = await list_drafts(db_session, organization_id, acme.id)
    assert len(drafts) == 1
    assert drafts[0].product_id == product.id


async def test_no_active_criteria_skips_qualification_and_downstream_stages(
    db_session, organization_id
) -> None:
    product = await create_product(db_session, organization_id, name="Widget", description=None)
    await db_session.commit()

    run = await _confirmed_run(
        db_session, organization_id,
        [DiscoveredCompany(name="Acme Inc", domain="acme.com", source_snippet="Acme Inc")],
    )
    job = _pipeline_job(organization_id, run.id, product.id)

    result = await _run_auto_pipeline(
        db_session, job,
        discovery_agent=StubCompanyDiscoveryAgent(
            [DiscoveredCompany(name="Acme Inc", domain="acme.com", source_snippet="Acme Inc")]
        ),
        qualification_generator=_AllMetQualificationGenerator(),
        role_relevance_generator=MockRoleRelevanceGenerator(),
        draft_generator=MockDraftGenerator(),
        **_providers([]),
    )

    assert result["discovery"]["companies_created"] == 1
    assert result["qualification"] == {
        "ran": False,
        "skipped_reason": "no active qualification criteria configured",
    }
    assert result["role_classification"] == {
        "ran": False,
        "skipped_reason": "no qualified companies",
    }
    assert result["drafting"] == {
        "ran": False,
        "skipped_reason": "no primary-target contacts identified",
    }


async def test_no_active_categories_skips_role_classification_and_drafting(
    db_session, organization_id
) -> None:
    await create_criterion(
        db_session, organization_id, name="Some criterion", description=None,
        is_disqualifying=False, is_active=True,
    )
    product = await create_product(db_session, organization_id, name="Widget", description=None)
    await db_session.commit()

    run = await _confirmed_run(
        db_session, organization_id,
        [DiscoveredCompany(name="Acme Inc", domain="acme.com", source_snippet="Acme Inc")],
    )
    job = _pipeline_job(organization_id, run.id, product.id)

    result = await _run_auto_pipeline(
        db_session, job,
        discovery_agent=StubCompanyDiscoveryAgent(
            [DiscoveredCompany(name="Acme Inc", domain="acme.com", source_snippet="Acme Inc")]
        ),
        qualification_generator=_AllMetQualificationGenerator(),
        role_relevance_generator=MockRoleRelevanceGenerator(),
        draft_generator=MockDraftGenerator(),
        **_providers([ScrapedContact(full_name="Jane Doe", role_title="Procurement Manager")]),
    )

    assert result["qualification"]["ran"] is True
    assert result["role_classification"] == {
        "ran": False,
        "skipped_reason": "no active role categories configured",
    }
    assert result["drafting"] == {
        "ran": False,
        "skipped_reason": "no primary-target contacts identified",
    }


async def test_no_product_skips_drafting_only(db_session, organization_id) -> None:
    await create_criterion(
        db_session, organization_id, name="Some criterion", description=None,
        is_disqualifying=False, is_active=True,
    )
    await create_category(
        db_session, organization_id, name="Vendor / IT", description=None,
        is_primary_target=True, is_active=True,
    )
    await db_session.commit()

    run = await _confirmed_run(
        db_session, organization_id,
        [DiscoveredCompany(name="Acme Inc", domain="acme.com", source_snippet="Acme Inc")],
    )
    job = _pipeline_job(organization_id, run.id, product_id=None)

    result = await _run_auto_pipeline(
        db_session, job,
        discovery_agent=StubCompanyDiscoveryAgent(
            [DiscoveredCompany(name="Acme Inc", domain="acme.com", source_snippet="Acme Inc")]
        ),
        qualification_generator=_AllMetQualificationGenerator(),
        role_relevance_generator=MockRoleRelevanceGenerator(),
        draft_generator=MockDraftGenerator(),
        **_providers([ScrapedContact(full_name="Jane Doe", role_title="Procurement Manager")]),
    )

    assert result["qualification"]["ran"] is True
    assert result["role_classification"]["ran"] is True
    assert result["drafting"] == {"ran": False, "skipped_reason": "no product specified"}


async def test_cap_limits_role_classification_and_drafting_to_first_n_qualified(
    db_session, organization_id, monkeypatch
) -> None:
    # get_settings() is lru_cached, so patch the attribute directly on the cached instance —
    # monkeypatch restores it automatically after the test.
    monkeypatch.setattr(get_settings(), "auto_pipeline_max_companies_to_draft", 1)

    await create_criterion(
        db_session, organization_id, name="Some criterion", description=None,
        is_disqualifying=False, is_active=True,
    )
    await create_category(
        db_session, organization_id, name="Vendor / IT", description=None,
        is_primary_target=True, is_active=True,
    )
    product = await create_product(db_session, organization_id, name="Widget", description=None)
    await db_session.commit()

    discovered = [
        DiscoveredCompany(
            name="Acme Inc",
            domain="acme.com",
            source_snippet="Acme Inc",
            needs_review=True,
            needs_review_reason="structurally suspicious name",
        ),
        DiscoveredCompany(
            name="Globex Corp",
            domain="globex.com",
            source_snippet="Globex",
            needs_review=True,
            needs_review_reason="structurally suspicious name",
        ),
    ]
    run = await _confirmed_run(db_session, organization_id, discovered)
    job = _pipeline_job(organization_id, run.id, product.id)

    result = await _run_auto_pipeline(
        db_session, job,
        discovery_agent=StubCompanyDiscoveryAgent(discovered),
        qualification_generator=_AllMetQualificationGenerator(),
        role_relevance_generator=MockRoleRelevanceGenerator(),
        draft_generator=MockDraftGenerator(),
        **_providers(
            [
                ScrapedContact(
                    full_name="Jane Doe", role_title="Procurement Manager", email="jane@acme.com"
                )
            ]
        ),
    )
    await db_session.commit()

    assert result["qualification"]["qualified"] == 2  # qualification itself isn't capped
    # Classification is capped to 1 company, and that one is still unconfirmed (needs_review),
    # so nothing was actually classified or drafted yet.
    assert len(result["role_classification"]["skipped_needs_review"]) == 1
    assert result["role_classification"]["companies_classified"] == 0
    assert result["drafting"] == {
        "ran": False,
        "skipped_reason": "no primary-target contacts identified",
    }
    assert result["capped"] is True

    skipped_company_id = uuid.UUID(
        result["role_classification"]["skipped_needs_review"][0]["company_id"]
    )
    await confirm_company(db_session, organization_id, skipped_company_id)
    resumed = await classify_and_draft_company(
        db_session, organization_id, skipped_company_id,
        MockRoleRelevanceGenerator(), MockDraftGenerator(), [product.id],
    )
    await db_session.commit()
    assert resumed["role_classification"]["ran"] is True
    assert resumed["drafting"]["drafts_generated"] == 1
