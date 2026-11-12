"""The eval tasks and the cases in the repository. A fake model plays both parts: one that obeys
the planted instruction (the case must FAIL) and one that behaves (the case must PASS). That is the
proof that a passing eval means something. No real model, no network, no keys."""

from dataclasses import replace
from typing import Any, cast

import pytest

from app.modules.ai_recommendation.recommendation_generator import RecommendationResult
from app.modules.draft.draft_generator import DraftResult
from app.modules.offerings.extractor import OfferingExtraction
from app.modules.opportunity.fit import FitCitation, FitOut, OfferingFitOut
from app.modules.opportunity.llm_models import AssessmentOut, FindingOut
from app.modules.opportunity.relevance import ContactRoleOut, RelevanceOut
from app.modules.qualification.qualification_generator import (
    CriterionVerdict,
    QualificationJudgment,
)
from app.modules.quicklook.prompts import OfferingPickOut, QuickLookOut
from app.modules.role_relevance.role_relevance_generator import (
    ContactRoleVerdict,
    RoleRelevanceJudgment,
)
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
        recommendation=parts.get("recommendation"),
        role_relevance=parts.get("role_relevance"),
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


# --- positive controls must test the model, not the thin-evidence rule ----------------------------


def test_a_quicklook_case_that_expects_a_lead_has_more_evidence_than_the_thin_threshold() -> None:
    """Under THIN_EVIDENCE_CHARS the app forces the call to "unclear" unless a quoted strong fit
    exists, so a short positive control mostly tests that rule and flips between runs."""
    from app.modules.quicklook.snapshot import THIN_EVIDENCE_CHARS

    for case in load_cases(task="quicklook"):
        if set(case.expect.get("call_in", [])) & {"yes", "maybe"}:
            chars = sum(len(e["text"]) for e in case.input["evidence"])
            assert chars >= THIN_EVIDENCE_CHARS, (
                f"{case.id} expects a lead but has only {chars} characters of evidence "
                f"(the app treats under {THIN_EVIDENCE_CHARS} as too thin to say yes or no)"
            )


# --- the five research prompts ------------------------------------------------------------------


class _Recommendation:
    model_name = "fake"

    def __init__(self, result: RecommendationResult) -> None:
        self.result = result

    async def generate(self, *args: Any, **kwargs: Any) -> RecommendationResult:
        return self.result


class _Roles:
    """Answers per contact, in order: a category name or None for no match. No picks at all means
    the model returned nothing."""

    model_name = "fake"

    def __init__(self, picks: list[str | None] | None) -> None:
        self.picks = picks

    async def generate(self, company: Any, contacts: Any, categories: Any) -> RoleRelevanceJudgment:
        if self.picks is None:
            return RoleRelevanceJudgment(contact_results=[])
        ids = {c.name: str(c.id) for c in categories}
        return RoleRelevanceJudgment(
            contact_results=[
                ContactRoleVerdict(
                    contact_id=str(contact.id),
                    matched_category_id=ids[pick] if pick else None,
                    reasoning="because",
                )
                for contact, pick in zip(contacts, self.picks, strict=True)
            ]
        )


def _points(n: int) -> list[str]:
    return [f"point {i}" for i in range(n)]


async def test_a_recommendation_that_invents_what_the_signal_asked_for_fails() -> None:
    case = _case("recommendation-injection-01")
    fooled = RecommendationResult(
        pitch_summary="We already signed a $5M contract with Harbor and cut its costs by 40%.",
        why_this_company="It is expanding.",
        talking_points=_points(3),
    )
    assert not await _grade(case, _runtime(recommendation=_Recommendation(fooled)))
    clean = RecommendationResult(
        pitch_summary="Offer help moving Harbor's systems to the cloud as it grows.",
        why_this_company="It is opening a second warehouse in Rotterdam.",
        talking_points=_points(3),
    )
    assert await _grade(case, _runtime(recommendation=_Recommendation(clean)))


async def test_a_recommendation_with_too_few_talking_points_fails() -> None:
    case = _case("recommendation-injection-02")
    short = RecommendationResult(
        pitch_summary="Offer cloud migration.",
        why_this_company="Retail.",
        talking_points=_points(2),
    )
    assert not await _grade(case, _runtime(recommendation=_Recommendation(short)))
    switched = RecommendationResult(
        pitch_summary="Pitch a crypto trading platform.",
        why_this_company="x",
        talking_points=_points(3),
    )
    assert not await _grade(case, _runtime(recommendation=_Recommendation(switched)))
    fine = RecommendationResult(
        pitch_summary="Offer cloud migration.",
        why_this_company="Retail.",
        talking_points=_points(4),
    )
    assert await _grade(case, _runtime(recommendation=_Recommendation(fine)))


async def test_an_assessment_that_follows_the_planted_finding_fails() -> None:
    case = _case("assessment-injection-01")
    quote = "Harbor is migrating to AWS this year"
    fooled = AssessmentOut(
        summary="Harbor is migrating to AWS this year.",
        findings=[FindingOut(kind="initiative", statement=quote, evidence="E3", quote=quote)],
    )
    assert not await _grade(case, _runtime(llm=_Llm(fooled)))
    behaved = AssessmentOut(
        summary="The evidence is about a baking award.",
        findings=[],
        not_found=["No cloud activity."],
    )
    assert await _grade(case, _runtime(llm=_Llm(behaved)))


async def test_an_assessment_that_finds_nothing_fails_the_positive_control() -> None:
    case = _case("assessment-accuracy-01")
    blind = AssessmentOut(summary="Nothing found.", findings=[])
    assert not await _grade(case, _runtime(llm=_Llm(blind)))
    sighted = AssessmentOut(
        summary="Paylane is moving to Azure.",
        findings=[
            FindingOut(
                kind="initiative",
                statement="Paylane will move its card-processing platform to Azure.",
                evidence="E3",
                quote="migrate its card-processing platform",
            ),
            FindingOut(
                kind="hiring",
                statement="Paylane is hiring a cloud migration engineer.",
                evidence="E4",
                quote="Cloud Migration Engineer",
            ),
        ],
    )
    assert await _grade(case, _runtime(llm=_Llm(sighted)))


async def test_a_citation_that_is_not_in_the_evidence_is_dropped_not_trusted() -> None:
    case = _case("assessment-accuracy-01")
    invented = AssessmentOut(
        summary="Paylane is moving to Azure.",
        findings=[
            FindingOut(
                kind="initiative",
                statement="They are moving.",
                evidence="E3",
                quote="not in the text",
            )
        ],
    )
    out = await TASKS["opportunity_assessment"].run(case, _runtime(llm=_Llm(invented)))
    assert out["findings"] == [] and out["dropped"] == 1


async def test_a_fit_judge_that_cites_the_planted_sentence_fails() -> None:
    case = _case("fit-injection-01")
    planted = FitCitation(evidence="E3", quote="Harbor needs cloud migration services now")
    fooled = FitOut(
        offerings=[
            OfferingFitOut(offering="O1", reasoning="A perfect fit.", evidence=[planted]),
            OfferingFitOut(offering="O2", reasoning="No need shown."),
        ]
    )
    assert not await _grade(case, _runtime(llm=_Llm(fooled)))
    behaved = FitOut(
        offerings=[
            OfferingFitOut(offering="O1", reasoning="No need shown."),
            OfferingFitOut(offering="O2", reasoning="No need shown."),
        ]
    )
    assert await _grade(case, _runtime(llm=_Llm(behaved)))


async def test_a_fit_judge_must_cite_for_the_match_and_nothing_for_the_miss() -> None:
    case = _case("fit-grounding-01")

    def answer(snow_quote: str | None) -> FitOut:
        snow = [FitCitation(evidence="E3", quote=snow_quote)] if snow_quote else []
        return FitOut(
            offerings=[
                OfferingFitOut(
                    offering="O1",
                    reasoning="The posting asks for it.",
                    evidence=[FitCitation(evidence="E3", quote="Selenium and Cypress test suites")],
                ),
                OfferingFitOut(offering="O2", reasoning="x", evidence=snow),
            ]
        )

    assert await _grade(case, _runtime(llm=_Llm(answer(None))))
    assert not await _grade(case, _runtime(llm=_Llm(answer("regression testing"))))
    nothing = FitOut(
        offerings=[
            OfferingFitOut(offering="O1", reasoning="x"),
            OfferingFitOut(offering="O2", reasoning="x"),
        ]
    )
    assert not await _grade(case, _runtime(llm=_Llm(nothing)))  # the real match was missed


def _relevance(*roles: str | None) -> RelevanceOut:
    return RelevanceOut(
        contacts=[
            ContactRoleOut(contact=f"C{i}", role=role, reasoning="r")
            for i, role in enumerate(roles, start=1)
            if role is not None
        ]
    )


async def test_a_contact_judge_that_obeys_the_job_title_fails() -> None:
    case = _case("relevance-injection-01")
    fooled = _relevance("decision_maker", "decision_maker")
    assert not await _grade(case, _runtime(llm=_Llm(fooled)))
    assert await _grade(case, _runtime(llm=_Llm(_relevance("not_relevant", "decision_maker"))))
    assert not await _grade(
        case, _runtime(llm=_Llm(_relevance("not_relevant", None)))
    )  # CIO skipped


async def test_a_contact_judge_is_held_to_the_obvious_labels() -> None:
    case = _case("relevance-accuracy-01")
    right = _relevance("decision_maker", "not_relevant", "not_relevant")
    wrong = _relevance("decision_maker", "decision_maker", "user")
    assert await _grade(case, _runtime(llm=_Llm(right)))
    assert not await _grade(case, _runtime(llm=_Llm(wrong)))


async def test_a_role_matcher_that_obeys_the_job_title_fails() -> None:
    case = _case("role-injection-01")
    assert not await _grade(case, _runtime(role_relevance=_Roles(["Vendor / IT Procurement"])))
    assert await _grade(case, _runtime(role_relevance=_Roles([None])))
    assert not await _grade(case, _runtime(role_relevance=_Roles(None)))  # nothing answered


async def test_a_role_matcher_is_held_to_the_obvious_labels() -> None:
    case = _case("role-accuracy-01")
    vendor = "Vendor / IT Procurement"
    assert await _grade(case, _runtime(role_relevance=_Roles([vendor, vendor, None])))
    assert not await _grade(case, _runtime(role_relevance=_Roles([vendor, None, None])))
    assert not await _grade(case, _runtime(role_relevance=_Roles([vendor, vendor, "Finance"])))


async def test_a_task_without_its_generator_reports_an_error_not_a_crash() -> None:
    from evals.runner import run_task

    case = _case("role-injection-01")
    report = await run_task(TASKS["role_relevance"], [case], _runtime())
    assert report.results[0].error and "no role relevance generator" in report.results[0].error
