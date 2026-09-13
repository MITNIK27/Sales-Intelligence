import uuid

import pytest

from app.modules.ai_recommendation.gemini_client import GeminiClientError
from app.modules.companies.models import Company
from app.modules.jobs.models import Job
from app.modules.qualification.qualification_generator import (
    CriterionVerdict,
    QualificationJudgment,
)
from app.modules.qualification.service import (
    NoCriteriaConfiguredError,
    create_criterion,
    run_bulk_qualification_job,
)


class _FakeGenerator:
    """Returns "met" for every criterion for every company it's asked about, except for
    companies in `failing_company_ids`, which raise a GeminiClientError instead — lets tests
    exercise both the happy path and the per-company error-capture path in one generator."""

    def __init__(self, failing_company_ids: set[uuid.UUID] | None = None) -> None:
        self._failing = failing_company_ids or set()

    @property
    def model_name(self) -> str:
        return "fake-model"

    async def generate(self, company, signals, criteria) -> QualificationJudgment:  # type: ignore[no-untyped-def]
        if company.id in self._failing:
            raise GeminiClientError("simulated transient failure")
        return QualificationJudgment(
            criteria_results=[
                CriterionVerdict(criterion_id=str(c.id), verdict="met", reasoning="r")
                for c in criteria
            ]
        )


def _job(organization_id: uuid.UUID, company_ids: list[uuid.UUID]) -> Job:
    return Job(
        organization_id=organization_id,
        job_type="bulk_qualify",
        payload={"company_ids": [str(cid) for cid in company_ids]},
    )


async def test_bulk_qualify_raises_immediately_without_active_criteria(
    db_session, organization_id, monkeypatch
) -> None:
    company = Company(organization_id=organization_id, name="Acme", domain="acme.com")
    db_session.add(company)
    await db_session.commit()

    monkeypatch.setattr(
        "app.modules.qualification.service.GeminiQualificationGenerator",
        lambda settings: _FakeGenerator(),
    )
    job = _job(organization_id, [company.id])
    with pytest.raises(NoCriteriaConfiguredError):
        await run_bulk_qualification_job(db_session, job)


async def test_bulk_qualify_splits_counts_and_captures_per_company_errors(
    db_session, organization_id, monkeypatch
) -> None:
    good_company = Company(organization_id=organization_id, name="Acme", domain="acme.com")
    bad_company = Company(organization_id=organization_id, name="Globex", domain="globex.com")
    db_session.add_all([good_company, bad_company])
    await create_criterion(
        db_session, organization_id, name="Some criterion", description=None,
        is_disqualifying=False, is_active=True,
    )
    await db_session.commit()

    generator = _FakeGenerator(failing_company_ids={bad_company.id})
    monkeypatch.setattr(
        "app.modules.qualification.service.GeminiQualificationGenerator",
        lambda settings: generator,
    )

    progress_calls: list[tuple[int, int]] = []

    async def progress_callback(done: int, total: int) -> None:
        progress_calls.append((done, total))

    job = _job(organization_id, [good_company.id, bad_company.id])
    result = await run_bulk_qualification_job(db_session, job, progress_callback)

    assert result["qualified"] == 1
    assert result["not_qualified"] == 0
    assert result["could_not_determine"] == 0
    assert len(result["errors"]) == 1
    assert result["errors"][0]["company_id"] == str(bad_company.id)
    assert progress_calls == [(1, 2), (2, 2)]
