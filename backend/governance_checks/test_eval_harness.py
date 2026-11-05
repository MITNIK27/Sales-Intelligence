"""The eval harness itself: case loading, graders and reports. No model, no network, no keys."""

import json
from pathlib import Path
from typing import Any

import pytest

from evals.cases import CaseError, load_cases
from evals.graders import (
    Check,
    check_at_most,
    check_equal,
    check_no_leak,
    check_no_unsupported_claims,
    check_none_of,
    check_one_of,
    check_quotes_in_evidence,
    check_verdicts,
    passed,
)
from evals.report import (
    CaseResult,
    Report,
    diff_reports,
    previous_report,
    report_filename,
    to_dict,
    write_report,
)


def _line(**overrides: object) -> str:
    case: dict[str, object] = {
        "id": "ql-1",
        "task": "quicklook",
        "tags": ["injection"],
        "input": {"name": "Acme"},
        "expect": {"call_not_in": ["yes"]},
    }
    case.update(overrides)
    return json.dumps(case)


def _write(directory: Path, *lines: str, name: str = "cases.jsonl") -> None:
    (directory / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- case loading ------------------------------------------------------------------------------


def test_a_valid_case_loads(tmp_path: Path) -> None:
    _write(tmp_path, _line(), "", _line(id="ql-2", task="draft", tags=["grounding", "accuracy"]))
    cases = load_cases(tmp_path)
    assert [c.id for c in cases] == ["ql-1", "ql-2"]
    assert cases[1].tags == ("grounding", "accuracy")


def test_cases_can_be_filtered_by_task(tmp_path: Path) -> None:
    _write(tmp_path, _line(), _line(id="d-1", task="draft"))
    assert [c.id for c in load_cases(tmp_path, task="draft")] == ["d-1"]


@pytest.mark.parametrize(
    ("line", "message"),
    [
        (_line(extra="x"), "unknown key"),
        (_line(task="astrology"), "unknown task"),
        (_line(tags=["vibes"]), "'tags' must be"),
        (_line(tags=[]), "'tags' must be"),
        (_line(expect={}), "could never fail"),
        (_line(id=" "), "'id' must be"),
        ("{not json", "not valid JSON"),
        ("[1, 2]", "must be a JSON object"),
    ],
)
def test_a_malformed_case_is_rejected_with_its_location(
    tmp_path: Path, line: str, message: str
) -> None:
    _write(tmp_path, line)
    with pytest.raises(CaseError, match=message) as error:
        load_cases(tmp_path)
    assert "cases.jsonl:1" in str(error.value)


def test_a_missing_field_is_rejected(tmp_path: Path) -> None:
    raw = json.loads(_line())
    del raw["input"]
    _write(tmp_path, json.dumps(raw))
    with pytest.raises(CaseError, match="missing 'input'"):
        load_cases(tmp_path)


def test_a_duplicate_id_is_rejected_even_across_files(tmp_path: Path) -> None:
    _write(tmp_path, _line(), name="a.jsonl")
    _write(tmp_path, _line(), name="b.jsonl")
    with pytest.raises(CaseError, match="duplicate id 'ql-1'"):
        load_cases(tmp_path)


def test_the_cases_in_the_repository_are_all_valid() -> None:
    load_cases()  # raises on any malformed case, so a bad case cannot be committed


# --- graders ------------------------------------------------------------------------------------


def test_simple_comparisons() -> None:
    assert check_equal("x", 1, 1).ok and not check_equal("x", 1, 2).ok
    assert check_one_of("x", "maybe", ["yes", "maybe"]).ok
    assert not check_one_of("x", "no", ["yes", "maybe"]).ok
    assert check_none_of("x", "no", ["yes"]).ok and not check_none_of("x", "yes", ["yes"]).ok
    assert check_at_most("x", 1, 1).ok and not check_at_most("x", 2, 1).ok


def test_an_injected_phrase_in_the_answer_is_a_leak() -> None:
    assert check_no_leak("leak", "A plain summary.", ["perfect fit"]).ok
    leaked = check_no_leak("leak", "They are a PERFECT FIT for us.", ["perfect fit"])
    assert not leaked.ok and "perfect fit" in leaked.detail


def test_quotes_must_be_in_the_evidence_they_cite() -> None:
    sources = {"E1": "Acme is migrating its data platform to the cloud this year."}
    assert check_quotes_in_evidence("q", [("E1", "migrating its data platform")], sources).ok
    assert not check_quotes_in_evidence("q", [("E1", "launching a rocket")], sources).ok
    assert not check_quotes_in_evidence("q", [("E9", "migrating")], sources).ok


def test_unsupported_claims_reuse_the_draft_checker() -> None:
    assert check_no_unsupported_claims("c", "Would a short call help?", ["Acme sells widgets"]).ok
    assert not check_no_unsupported_claims("c", "We cut costs by 85%.", ["Acme sells widgets"]).ok


def test_verdicts_must_match_the_labels_and_a_skipped_item_fails() -> None:
    expected = {"Budget": "met", "Size": "not_met"}
    assert check_verdicts("v", {"Budget": "met", "Size": "not_met"}, expected).ok
    wrong = check_verdicts("v", {"Budget": "met"}, expected)
    assert not wrong.ok and "Size" in wrong.detail


def test_passed_needs_every_check_to_pass() -> None:
    assert passed([Check("a", True), Check("b", True)])
    assert not passed([Check("a", True), Check("b", False)])


# --- reports ------------------------------------------------------------------------------------


def _report(
    task: str = "quicklook", version: str = "v4", model: str = "gemini-x", **kw: Any
) -> Report:
    results = [
        CaseResult("a", ("injection",), [Check("leak", True)]),
        CaseResult("b", ("injection", "grounding"), [Check("leak", False, "repeats it")]),
        CaseResult("c", ("grounding",), error="the model call failed"),
    ]
    return Report(task, version, model, results, **kw)


def test_the_summary_counts_by_tag_and_treats_errors_as_failures() -> None:
    summary = _report().summary()
    assert summary["total"] == 3 and summary["passed"] == 1 and summary["errors"] == 1
    assert summary["by_tag"]["injection"] == {"passed": 1, "total": 2}
    assert summary["by_tag"]["grounding"] == {"passed": 0, "total": 2}


def test_the_filename_is_safe_and_names_task_version_and_model() -> None:
    assert report_filename("quicklook", "v4", "gemini-flash-lite-latest") == (
        "quicklook-v4-gemini-flash-lite-latest.json"
    )
    slashed = report_filename("draft", "v2", "openai/gpt-oss-120b")
    assert slashed == "draft-v2-openai-gpt-oss-120b.json"


def test_a_report_is_written_and_failing_detail_is_kept(tmp_path: Path) -> None:
    path = write_report(_report(), tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "quicklook-v4-gemini-x.json"
    assert data["summary"]["passed"] == 1
    failing = next(r for r in data["results"] if r["case_id"] == "b")
    assert failing["checks"][0]["detail"] == "repeats it"
    assert to_dict(_report())["results"][2]["error"] == "the model call failed"


def test_the_previous_report_is_the_newest_other_one_for_the_same_task(tmp_path: Path) -> None:
    old = write_report(_report(version="v3", date="2026-11-01T10:00:00+00:00"), tmp_path)
    mid = write_report(_report(version="v4", date="2026-11-03T10:00:00+00:00"), tmp_path)
    write_report(_report(task="draft", date="2026-11-04T10:00:00+00:00"), tmp_path)
    current = write_report(_report(version="v5", date="2026-11-05T10:00:00+00:00"), tmp_path)
    found = previous_report("quicklook", tmp_path, exclude=current)
    assert found is not None and found["prompt_version"] == "v4"
    assert old != mid
    assert previous_report("offering_extraction", tmp_path) is None


def test_the_diff_names_cases_that_changed() -> None:
    old = to_dict(_report(version="v3"))
    better = _report(version="v4")
    better.results[1] = CaseResult("b", ("injection",), [Check("leak", True)])
    better.results[0] = CaseResult("a", ("injection",), [Check("leak", False, "x")])
    lines = diff_reports(old, to_dict(better))
    assert "1/3 -> 1/3" in lines[0]
    assert "  now failing: a" in lines and "  now passing: b" in lines
