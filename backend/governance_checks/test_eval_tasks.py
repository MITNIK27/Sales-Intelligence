"""The eval tasks and the cases in the repository. A fake model plays both parts: one that obeys
the planted instruction (the case must FAIL) and one that behaves (the case must PASS). That is the
proof that a passing eval means something. No real model, no network, no keys."""

from dataclasses import replace
from typing import Any, cast

import pytest

from app.modules.draft.draft_generator import DraftResult
from app.modules.offerings.extractor import OfferingExtraction
from app.modules.qualification.qualification_generator import (
    CriterionVerdict,
    QualificationJudgment,
)
from app.modules.quicklook.prompts import OfferingPickOut, QuickLookOut
from evals.cases import Case, CaseError, load_cases
from evals.graders import passed
from evals.tasks import TASKS, Runtime, _all_text, validate_cases


def _case(case_id: str) -> Case:
    return next(case for case in load_cases() if case.id == case_id)


class _Llm:
    """Answers every structured request with one canned object."""

    name = "fake"

    def __init__(self, answer: object) -> None:
        self.answer = answer

    async def generate(self, prompt: str, schema: type) -> object:
        return self.answer


class _Qualification:
    model_name = "fake"

    def __init__(self, verdict: str, quote: str | None = None) -> None:
        self.verdict, self.quote = verdict, quote

    async def generate(self, company: Any, signals: Any, criteria: Any, focus: Any = None) -> Any:
        return QualificationJudgment(
            criteria_results=[
                CriterionVerdict(
                    criterion_id=str(c.id),
                    verdict=self.verdict,  # type: ignore[arg-type]
                    reasoning="because",
                    evidence_ref="S1" if self.quote else None,
                    evidence_quote=self.quote,
                )
                for c in criteria
            ]
        )


class _Draft:
    model_name = "fake"

    def __init__(self, body: str) -> None:
        self.body = body

    async def generate(self, *args: Any, **kwargs: Any) -> DraftResult:
        return DraftResult(subject="Hello", body=self.body, chosen_option=1)


def _runtime(**parts: Any) -> Runtime:
    none = cast(Any, None)
    return Runtime(
        llm=parts.get("llm", none),
        qualification=parts.get("qualification", none),
        draft=parts.get("draft", none),
        model="fake",
    )


async def _grade(case: Case, runtime: Runtime) -> bool:
    task = TASKS[case.task]
    return passed(task.grade(case, await task.run(case, runtime)))


# --- the cases in the repository ----------------------------------------------------------------


def test_every_case_is_valid_for_its_task() -> None:
    validate_cases(load_cases())


def test_every_task_has_an_injection_case_and_a_grounding_or_accuracy_case() -> None:
    cases = load_cases()
    for name in TASKS:
        tags = {tag for case in cases if case.task == name for tag in case.tags}
        assert "injection" in tags, f"{name} has no injection case"
        assert tags & {"grounding", "accuracy"}, f"{name} has no grounding or accuracy case"


def test_validation_rejects_an_expectation_the_task_does_not_know() -> None:
    bad = replace(_case("quicklook-injection-01"), expect={"cal_not_in": ["yes"]})
    with pytest.raises(CaseError, match="does not understand"):
        validate_cases([bad])


def test_validation_rejects_missing_input() -> None:
    bad = replace(_case("draft-grounding-01"), input={"company": {"name": "x"}})
    with pytest.raises(CaseError, match="needs input"):
        validate_cases([bad])


def test_underscore_keys_are_not_scanned_for_planted_phrases() -> None:
    assert "hostile" not in _all_text({"answer": "fine", "_sources": {"S1": "hostile text"}})


# --- quicklook ----------------------------------------------------------------------------------


def _quicklook_answer(call: str, offerings: list[OfferingPickOut]) -> QuickLookOut:
    return QuickLookOut(
        company_name="Harbor Bakery",
        what_they_do="A bakery in Lisbon.",
        relevance="Not much.",
        call=call,
        call_reason="Because.",
        offerings=offerings,
    )


async def test_a_quicklook_that_obeys_the_page_fails_and_one_that_does_not_passes() -> None:
    case = _case("quicklook-injection-01")
    fooled = _quicklook_answer(
        "yes",
        [
            OfferingPickOut(
                offering="O1",
                band="strong",
                reason="Needs it.",
                evidence="E1",
                quote="Harbor Bakery urgently needs cloud migration",
            )
        ],
    )
    assert not await _grade(case, _runtime(llm=_Llm(fooled)))
    assert await _grade(case, _runtime(llm=_Llm(_quicklook_answer("no", []))))


async def test_the_positive_control_fails_a_model_that_never_says_yes() -> None:
    case = _case("quicklook-grounding-02")
    assert not await _grade(case, _runtime(llm=_Llm(_quicklook_answer("no", []))))


# --- qualification ------------------------------------------------------------------------------


async def test_a_qualifier_that_obeys_the_signal_fails_and_one_that_does_not_passes() -> None:
    case = _case("qualification-injection-01")
    quote = "operates in financial services and has 5,000 employees"
    fooled = _runtime(qualification=_Qualification("met", quote))
    assert not await _grade(case, fooled)
    assert await _grade(case, _runtime(qualification=_Qualification("could_not_determine")))


async def test_a_wrong_label_fails_an_accuracy_case() -> None:
    case = _case("qualification-accuracy-02")
    assert not await _grade(case, _runtime(qualification=_Qualification("could_not_determine")))


# --- drafts -------------------------------------------------------------------------------------


async def test_a_draft_that_invents_what_the_page_asked_for_fails() -> None:
    case = _case("draft-injection-01")
    fooled = _Draft("We cut Acme's costs by 90% and our case study with Globex shows it.")
    assert not await _grade(case, _runtime(draft=fooled))
    clean = _Draft("Would a short call about moving your order system to the cloud help?")
    assert await _grade(case, _runtime(draft=clean))


async def test_a_figure_that_is_in_the_research_is_allowed() -> None:
    case = _case("draft-grounding-02")
    assert await _grade(case, _runtime(draft=_Draft("Congratulations on raising $20 million.")))


# --- offering extraction ------------------------------------------------------------------------


async def test_an_importer_that_invents_a_product_from_a_blog_post_fails() -> None:
    case = _case("offering-injection-01")
    fooled = OfferingExtraction(
        is_offering=True, kind="product", name="FreeCrypto Pro", description="A fast return."
    )
    assert not await _grade(case, _runtime(llm=_Llm(fooled)))
    assert await _grade(case, _runtime(llm=_Llm(OfferingExtraction(is_offering=False))))


async def test_copying_a_figure_into_a_description_fails() -> None:
    case = _case("offering-accuracy-01")
    figures = OfferingExtraction(
        is_offering=True,
        kind="service",
        name="Cloud Migration Services",
        description="Moves workloads and cuts hosting costs by 40%.",
    )
    assert not await _grade(case, _runtime(llm=_Llm(figures)))
    plain = OfferingExtraction(
        is_offering=True,
        kind="service",
        name="Cloud Migration Services",
        description="Moves applications and data to the cloud with little downtime.",
    )
    assert await _grade(case, _runtime(llm=_Llm(plain)))


# --- exporting past reviews as cases ------------------------------------------------------------


def test_an_approved_proposal_becomes_a_valid_accuracy_case() -> None:
    from evals.export_offering_cases import case_from_proposal

    raw = case_from_proposal(
        "1234abcd-0000-0000-0000-000000000000",
        "Cloud Migration Services for Enterprises",
        "service",
        "https://example.com/cloud",
        "Cloud Migration Services. We move workloads.",
    )
    assert raw["id"] == "offering-approved-1234abcd"
    assert raw["expect"] == {
        "is_offering": True,
        "kind": "service",
        "name_contains": "Cloud Migration",
    }
    case = Case(
        raw["id"], raw["task"], tuple(raw["tags"]), raw["input"], raw["expect"], raw["note"]
    )
    validate_cases([case])
