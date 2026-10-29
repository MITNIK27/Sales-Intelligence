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


def test_adhoc_check_request_requires_a_company() -> None:
    with pytest.raises(ValidationError, match="Provide a company name or website"):
        AdhocQualificationCheckRequest()
    with pytest.raises(ValidationError, match="Provide a company name or website"):
        AdhocQualificationCheckRequest(company="   ", focus="payments")
    assert AdhocQualificationCheckRequest(company="Acme", focus="payments").focus == "payments"
    assert AdhocQualificationCheckRequest(domain="acme.com").domain == "acme.com"


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

    async def progress_callback(done: int, total: int, **_extra: object) -> None:
        progress_calls.append((done, total))

    job = _job(organization_id, name="Acme Inc", domain="acme.com")
    await _run_adhoc_qualification(
        db_session, job,
        MockDomainDiscoveryProvider(), MockCompanyDataProvider(),
        MockContactDataProvider([]), MockSignalDataProvider([]),
        _FakeGenerator(),  # type: ignore[arg-type]
        progress_callback,
    )

    assert progress_calls == [(0, 2), (1, 2), (2, 2)]


class _SearchingProvider(MockDomainDiscoveryProvider):
    def __init__(self) -> None:
        super().__init__()
        self.queries: list[str] = []

    async def search_raw(self, query: str, num: int) -> list[dict[str, str]]:
        self.queries.append(query)
        return [{"title": "Acme payments rollout", "snippet": "Moves to a new payments.", "link": "https://x/1"}]


class _FocusGenerator(_FakeGenerator):
    def __init__(self) -> None:
        super().__init__()
        self.focus: str | None = None
        self.signal_texts: list[str] = []

    async def generate(self, company, signals, criteria, focus=None):  # type: ignore[no-untyped-def]
        self.focus = focus
        self.signal_texts = [s.raw_payload["text"] for s in signals]
        return await super().generate(company, signals, criteria)


async def test_adhoc_check_with_focus_searches_it_judges_around_it_and_stores_it(
    db_session, organization_id
) -> None:
    await create_criterion(
        db_session, organization_id, name="Some criterion", description=None,
        is_disqualifying=False, is_active=True,
    )
    await db_session.commit()

    provider, generator = _SearchingProvider(), _FocusGenerator()
    calls: list[tuple[int, int]] = []

    async def progress_callback(done: int, total: int, **_extra: object) -> None:
        calls.append((done, total))

    job = Job(
        organization_id=organization_id,
        job_type="adhoc_qualify",
        payload={"name": "Acme", "domain": "acme.com", "focus": "payments"},
    )
    result = await _run_adhoc_qualification(
        db_session, job, provider, MockCompanyDataProvider(),
        MockContactDataProvider([]), MockSignalDataProvider([]),
        generator, progress_callback,  # type: ignore[arg-type]
    )

    assert provider.queries == ["Acme payments"]
    assert generator.focus == "payments"
    assert generator.signal_texts[0].startswith("Acme payments rollout")
    assert result["focus"] == "payments"
    assert calls == [(0, 3), (1, 3), (2, 3), (3, 3)]

    from app.modules.qualification.models import QualificationResult

    stored = await db_session.get(QualificationResult, uuid.UUID(result["qualification_result_id"]))
    assert stored.focus == "payments"


def test_split_company_input_tells_a_name_from_a_website() -> None:
    from app.modules.companies.service import split_company_input

    assert split_company_input("Acme") == ("Acme", None)
    assert split_company_input("  Acme Inc. ") == ("Acme Inc.", None)
    assert split_company_input("acme.com") == (None, "acme.com")
    assert split_company_input("https://www.Acme.com/about") == (None, "acme.com")
    assert split_company_input("www.acme.com") == (None, "acme.com")
    assert split_company_input("   ") == (None, None)


def test_focus_is_added_to_the_qualification_prompt_only_when_given() -> None:
    from app.modules.qualification.prompts import build_qualification_prompt

    company = Company(name="Acme", domain="acme.com")
    assert "payments" not in build_qualification_prompt(company, [], [])
    prompt = build_qualification_prompt(company, [], [], "payments")
    assert "specifically around: payments" in prompt
