import uuid

import pytest

from app.modules.ai_recommendation.gemini_client import GeminiClientError
from app.modules.companies.models import Company
from app.modules.qualification.models import QualificationCriterion
from app.modules.qualification.qualification_generator import (
    CriterionVerdict,
    QualificationJudgment,
)
from app.modules.qualification.service import (
    CompanyNotFoundError,
    NoCriteriaConfiguredError,
    _compute_overall_verdict,
    create_criterion,
    judge_qualification,
    run_qualification_check,
)


def _company(**overrides: object) -> Company:
    defaults: dict[str, object] = {
        "name": "Acme Inc",
        "domain": "acme.com",
        "industry": "SaaS",
        "employee_count_range": "50-200",
        "description": "Acme builds widgets.",
    }
    defaults.update(overrides)
    return Company(**defaults)  # type: ignore[arg-type]


def _criterion(**overrides: object) -> QualificationCriterion:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "name": "Minimum IT spend",
        "description": "Evidence of significant annual IT spend.",
        "is_disqualifying": True,
        "is_active": True,
    }
    defaults.update(overrides)
    return QualificationCriterion(**defaults)  # type: ignore[arg-type]


class _FakeGenerator:
    def __init__(self, verdicts: dict[str, str]) -> None:
        self._verdicts = verdicts

    @property
    def model_name(self) -> str:
        return "fake-model"

    async def generate(self, company, signals, criteria) -> QualificationJudgment:  # type: ignore[no-untyped-def]
        return QualificationJudgment(
            criteria_results=[
                CriterionVerdict(
                    criterion_id=str(c.id), verdict=self._verdicts[str(c.id)], reasoning="r"
                )
                for c in criteria
            ]
        )


# --- _compute_overall_verdict (pure, deterministic) ---


def test_overall_verdict_not_qualified_when_disqualifying_criterion_fails() -> None:
    results = [
        {"is_disqualifying": True, "verdict": "not_met"},
        {"is_disqualifying": False, "verdict": "met"},
    ]
    assert _compute_overall_verdict(results) == "not_qualified"


def test_overall_verdict_could_not_determine_when_disqualifying_criterion_is_undetermined() -> None:
    results = [
        {"is_disqualifying": True, "verdict": "could_not_determine"},
        {"is_disqualifying": False, "verdict": "not_met"},
    ]
    assert _compute_overall_verdict(results) == "could_not_determine"


def test_overall_verdict_qualified_when_disqualifying_criteria_all_met() -> None:
    results = [
        {"is_disqualifying": True, "verdict": "met"},
        {"is_disqualifying": False, "verdict": "not_met"},  # soft criterion never gates it
    ]
    assert _compute_overall_verdict(results) == "qualified"


def test_overall_verdict_qualified_by_default_with_no_disqualifying_criteria() -> None:
    results = [{"is_disqualifying": False, "verdict": "not_met"}]
    assert _compute_overall_verdict(results) == "qualified"


# --- judge_qualification (pure core, fake generator) ---


async def test_judge_qualification_snapshots_criteria_and_computes_verdict() -> None:
    criterion = _criterion(is_disqualifying=True)
    generator = _FakeGenerator({str(criterion.id): "met"})

    overall_verdict, criteria_results = await judge_qualification(
        _company(), [], [criterion], generator  # type: ignore[arg-type]
    )

    assert overall_verdict == "qualified"
    assert criteria_results == [
        {
            "criterion_id": str(criterion.id),
            "criterion_name": "Minimum IT spend",
            "is_disqualifying": True,
            "verdict": "met",
            "reasoning": "r",
        }
    ]


async def test_judge_qualification_raises_on_criterion_id_mismatch() -> None:
    criterion = _criterion()

    class _BadGenerator:
        model_name = "fake-model"

        async def generate(self, company, signals, criteria) -> QualificationJudgment:  # type: ignore[no-untyped-def]
            return QualificationJudgment(
                criteria_results=[
                    CriterionVerdict(criterion_id="not-a-real-id", verdict="met", reasoning="r")
                ]
            )

    with pytest.raises(GeminiClientError, match="exactly one verdict per given criterion"):
        await judge_qualification(_company(), [], [criterion], _BadGenerator())  # type: ignore[arg-type]


# --- run_qualification_check (DB-backed) ---


async def test_run_qualification_check_raises_for_missing_company(
    db_session, organization_id
) -> None:
    generator = _FakeGenerator({})
    with pytest.raises(CompanyNotFoundError):
        await run_qualification_check(
            db_session, organization_id, uuid.uuid4(), generator  # type: ignore[arg-type]
        )


async def test_run_qualification_check_raises_without_active_criteria(
    db_session, organization_id
) -> None:
    company = Company(organization_id=organization_id, name="Acme", domain="acme.com")
    db_session.add(company)
    await db_session.commit()

    generator = _FakeGenerator({})
    with pytest.raises(NoCriteriaConfiguredError):
        await run_qualification_check(
            db_session, organization_id, company.id, generator  # type: ignore[arg-type]
        )


async def test_run_qualification_check_excludes_inactive_criteria_and_persists_history(
    db_session, organization_id
) -> None:
    company = Company(organization_id=organization_id, name="Acme", domain="acme.com")
    db_session.add(company)
    active = await create_criterion(
        db_session, organization_id, name="Active one", description=None,
        is_disqualifying=True, is_active=True,
    )
    await create_criterion(
        db_session, organization_id, name="Inactive one", description=None,
        is_disqualifying=True, is_active=False,
    )
    await db_session.commit()

    generator = _FakeGenerator({str(active.id): "met"})

    first = await run_qualification_check(
        db_session, organization_id, company.id, generator  # type: ignore[arg-type]
    )
    await db_session.commit()
    assert first.overall_verdict == "qualified"
    assert len(first.criteria_results) == 1  # inactive criterion excluded
    assert first.criteria_results[0]["criterion_name"] == "Active one"

    second = await run_qualification_check(
        db_session, organization_id, company.id, generator  # type: ignore[arg-type]
    )
    await db_session.commit()

    assert first.id != second.id  # append-only: a re-check creates a new row, not an overwrite
