import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.modules.companies.models import Company
from app.modules.enrichment.providers.mock import (
    MockCompanyDataProvider,
    MockContactDataProvider,
    MockDomainDiscoveryProvider,
    MockSignalDataProvider,
)
from app.modules.jobs.models import Job
from app.modules.qualification.qualification_generator import (
    CriterionVerdict,
    QualificationJudgment,
)
from app.modules.qualification.schemas import AdhocQualificationCheckRequest
from app.modules.qualification.service import (
    NoCriteriaConfiguredError,
    _run_adhoc_qualification,
    create_criterion,
)


def test_adhoc_check_request_requires_name_or_domain() -> None:
    with pytest.raises(ValidationError, match="Provide a company name or domain"):
        AdhocQualificationCheckRequest()


class _FakeGenerator:
    def __init__(self, verdict: str = "met") -> None:
        self._verdict = verdict
        self.seen_company = None

    @property
    def model_name(self) -> str:
        return "fake-model"

    async def generate(self, company, signals, criteria) -> QualificationJudgment:  # type: ignore[no-untyped-def]
        self.seen_company = company
        return QualificationJudgment(
            criteria_results=[
                CriterionVerdict(criterion_id=str(c.id), verdict=self._verdict, reasoning="r")
                for c in criteria
            ]
        )


def _job(organization_id, name=None, domain=None) -> Job:  # type: ignore[no-untyped-def]
    return Job(
        organization_id=organization_id,
        job_type="adhoc_qualify",
        payload={"name": name, "domain": domain},
    )


async def test_adhoc_check_raises_without_active_criteria_before_any_side_effect(
    db_session, organization_id
) -> None:
    job = _job(organization_id, name="No Criteria Co", domain="nocriteria.example.com")
    with pytest.raises(NoCriteriaConfiguredError):
        await _run_adhoc_qualification(
            db_session, job,
            MockDomainDiscoveryProvider(), MockCompanyDataProvider(),
            MockContactDataProvider(), MockSignalDataProvider(),
            _FakeGenerator(),  # type: ignore[arg-type]
        )

    count = (await db_session.execute(select(func.count()).select_from(Company))).scalar_one()
    assert count == 0  # no company row created when the org isn't configured to judge anything


async def test_adhoc_check_enriches_company_before_judging(db_session, organization_id) -> None:
    await create_criterion(
        db_session, organization_id, name="Digital transformation maturity", description=None,
        is_disqualifying=True, is_active=True,
    )
    await db_session.commit()

    generator = _FakeGenerator(verdict="met")
    job = _job(organization_id, name="Acme Inc", domain="acme.com")
    result = await _run_adhoc_qualification(
        db_session, job,
        MockDomainDiscoveryProvider(),
        MockCompanyDataProvider(),  # default ScrapedCompanyData() — no pages, still "enriched"
        MockContactDataProvider([]), MockSignalDataProvider([]),
        generator,  # type: ignore[arg-type]
    )

    assert result["company_created"] is True
    assert result["company_domain"] == "acme.com"

    company = await db_session.get(Company, uuid.UUID(result["company_id"]))
    assert company.enrichment_status == "enriched"  # the fix: enrichment ran before judging
    assert generator.seen_company.id == company.id


async def test_adhoc_check_cleans_url_shaped_name(db_session, organization_id) -> None:
    await create_criterion(
        db_session, organization_id, name="Operates in Europe", description=None,
        is_disqualifying=False, is_active=True,
    )
    await db_session.commit()

    job = _job(organization_id, name="https://www.Sennder.com/", domain=None)
    result = await _run_adhoc_qualification(
        db_session, job,
        MockDomainDiscoveryProvider(), MockCompanyDataProvider(),
        MockContactDataProvider([]), MockSignalDataProvider([]),
        _FakeGenerator(),  # type: ignore[arg-type]
    )

    assert result["company_name"] == "sennder.com"


async def test_adhoc_check_reports_progress(db_session, organization_id) -> None:
    await create_criterion(
        db_session, organization_id, name="Some criterion", description=None,
        is_disqualifying=False, is_active=True,
    )
    await db_session.commit()

    progress_calls: list[tuple[int, int]] = []

    async def progress_callback(done: int, total: int) -> None:
        progress_calls.append((done, total))

    job = _job(organization_id, name="Acme Inc", domain="acme.com")
    await _run_adhoc_qualification(
        db_session, job,
        MockDomainDiscoveryProvider(), MockCompanyDataProvider(),
        MockContactDataProvider([]), MockSignalDataProvider([]),
        _FakeGenerator(),  # type: ignore[arg-type]
        progress_callback,
    )

    assert progress_calls == [(1, 2), (2, 2)]
