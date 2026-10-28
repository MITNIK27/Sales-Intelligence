"""Priority Score: weighted, normalized, evidence-scaled, hard-fail excluding."""

from datetime import UTC, datetime

from app.modules.qualification.ranking import (
    WEIGHTS,
    RankInputs,
    compute_priority,
    parse_size_range,
)

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def _hard(status: str, confidence: float | None = 0.9, name: str = "Operates in logistics"):
    return {
        "criterion_name": name,
        "is_disqualifying": True,
        "status": status,
        "verdict": {"PASS": "met", "FAIL": "not_met", "UNKNOWN": "could_not_determine"}[status],
        "confidence": confidence,
    }


def _strong() -> RankInputs:
    return RankInputs(
        criteria_results=[_hard("PASS", 0.95)],
        industry="Logistics & Supply Chain",
        employee_count_range="5,000-10,000",
        requested_keywords=["logistics", "parcel delivery"],
        requested_size="1,000-10,000",
        signal_dates=["2026-09-20", "2026-08-30", "2026-09-01"],
        contact_count=4,
        contacts_with_linkedin=2,
        now=NOW,
    )


def test_weights_sum_to_100() -> None:
    assert sum(WEIGHTS.values()) == 100


def test_parse_size_range() -> None:
    assert parse_size_range("1,000-10,000") == (1000, 10000)
    assert parse_size_range("10000+")[0] == 10000
    assert parse_size_range("about 250 employees") == (250, 250)
    assert parse_size_range("unknown") is None
    assert parse_size_range(None) is None


def test_strong_company_scores_high_and_explains_itself() -> None:
    result = compute_priority(_strong())
    assert not result.excluded
    assert result.score > 85
    components = result.breakdown["components"]
    assert set(components) == set(WEIGHTS)
    assert components["company_size"]["note"] == "inside the requested range"
    assert components["recent_news"]["note"] == "news in the last 90 days"


def test_hard_fail_excludes_regardless_of_other_strengths() -> None:
    inputs = _strong()
    inputs.criteria_results = [_hard("PASS"), _hard("FAIL", name="Not a competitor")]
    result = compute_priority(inputs)
    assert result.excluded and result.score == 0.0
    assert "Not a competitor" in result.breakdown["excluded"]


def test_unknown_hard_requirement_ranks_below_a_verified_one() -> None:
    verified = compute_priority(_strong())
    unverified_inputs = _strong()
    unverified_inputs.criteria_results = [_hard("UNKNOWN", None)]
    unverified = compute_priority(unverified_inputs)
    assert not unverified.excluded
    assert unverified.score < verified.score


def test_missing_data_is_neutral_not_punished_like_a_mismatch() -> None:
    unknown_size = _strong()
    unknown_size.employee_count_range = None
    far_size = _strong()
    far_size.employee_count_range = "2-10"
    unknown_score = compute_priority(unknown_size).score
    far_score = compute_priority(far_size).score
    assert far_score < unknown_score < compute_priority(_strong()).score


def test_well_evidenced_beats_weakly_evidenced_with_equal_data() -> None:
    strong_evidence = _strong()
    weak_evidence = _strong()
    weak_evidence.criteria_results = [_hard("PASS", 0.95), _hard("PASS", 0.2, name="Other")]
    assert compute_priority(weak_evidence).score < compute_priority(strong_evidence).score


def test_old_or_missing_news_scores_zero() -> None:
    old = _strong()
    old.signal_dates = ["2023-01-01"]
    none = _strong()
    none.signal_dates = [None]
    assert compute_priority(old).breakdown["components"]["recent_news"]["value"] == 0.0
    assert compute_priority(none).breakdown["components"]["recent_news"]["note"] == "no dated news"


def test_contact_availability_levels() -> None:
    inputs = _strong()
    values = {}
    for count, linkedin in ((0, 0), (3, 0), (3, 1)):
        inputs.contact_count, inputs.contacts_with_linkedin = count, linkedin
        values[(count, linkedin)] = compute_priority(inputs).breakdown["components"][
            "contact_availability"
        ]["value"]
    assert values == {(0, 0): 0.0, (3, 0): 0.5, (3, 1): 1.0}
