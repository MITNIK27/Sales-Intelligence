"""The label importer: what people type in a spreadsheet becomes valid eval cases, and the mistakes
people make are reported with the file and row. No model, no network, no keys."""

import json
from pathlib import Path

import pytest

from evals import import_labels
from evals.cases import load_cases
from evals.import_labels import LABELS_DIR, LabelError, build_all, main
from evals.tasks import validate_cases

QUALIFICATION_HEADER = (
    "case_id,company_name,company_domain,company_industry,company_size,company_description,"
    "evidence,criterion_name,criterion_description,label,why\n"
)
ROLE_HEADER = (
    "case_id,company_name,company_industry,company_description,contact_id,role_title,seniority,"
    "expected_category,why\n"
)
CATEGORY_HEADER = "name,description,is_primary_target\n"
CONTACT_HEADER = (
    "case_id,company_name,company_industry,area_label,offering_name,offering_description,"
    "contact_id,role_title,seniority,expected_roles,not_roles,why\n"
)


@pytest.fixture(autouse=True)
def _isolated_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Nothing here may write into the real cases folder."""
    cases = tmp_path / "cases"
    cases.mkdir()
    monkeypatch.setattr(import_labels, "CASES_DIR", cases)
    return cases


def _write(directory: Path, name: str, text: str) -> None:
    (directory / name).write_text(text, encoding="utf-8")


def test_the_templates_in_the_repository_import_nothing() -> None:
    assert build_all(LABELS_DIR) == {}  # only EXAMPLE rows, which are skipped


def test_qualification_rows_become_one_valid_case_per_company(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "qualification_labels.csv",
        QUALIFICATION_HEADER
        + 'a1,Northbank,northbank.example,Banking,1000-5000,"A regional bank, 400,000 customers.",,'
        "Operates in financial services,Banking or similar,met,a bank\n"
        "a1,,,,,,Hiring cloud engineers,Has more than 500 employees,Over 500,"
        "could_not_determine,no count\n"
        "a2,Tiny Tax Co,,,,A three person tax firm.,,Has more than 500 employees,Over 500,"
        "not_met,tiny\n",
    )
    built = build_all(tmp_path)
    first, second = built["qualification"]
    assert first["id"] == "qualification-label-a1" and first["tags"] == ["accuracy"]
    assert first["input"]["company"]["name"] == "Northbank"
    assert first["input"]["company"]["description"] == "A regional bank, 400,000 customers."
    assert first["input"]["signals"] == [{"signal_type": "news", "text": "Hiring cloud engineers"}]
    assert first["expect"] == {
        "verdicts": {
            "Operates in financial services": "met",
            "Has more than 500 employees": "could_not_determine",
        },
        "quotes_valid": True,
    }
    assert second["expect"]["verdicts"] == {"Has more than 500 employees": "not_met"}
    assert "tiny" in second["note"]


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ("a1,Acme,,,,,,Size,,maybe,\n", "label must be one of"),
        ("a1,,,,,,,Size,,met,\n", "has no company_name"),
        ("a1,Acme,,,,,,,,met,\n", "criterion_name must not be empty"),
        (",Acme,,,,,,Size,,met,\n", "case_id must not be empty"),
    ],
)
def test_a_mistake_is_reported_with_the_file_and_row(
    tmp_path: Path, row: str, message: str
) -> None:
    _write(tmp_path, "qualification_labels.csv", QUALIFICATION_HEADER + row)
    with pytest.raises(LabelError, match=message) as error:
        build_all(tmp_path)
    assert "qualification_labels.csv" in str(error.value)


def test_two_rows_of_one_case_that_disagree_about_the_company_are_an_error(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "qualification_labels.csv",
        QUALIFICATION_HEADER
        + "a1,Acme,,,,Bakes bread.,,Size,,met,\na1,Acme,,,,Sells cars.,,Money,,met,\n",
    )
    with pytest.raises(LabelError, match="different values for company_description"):
        build_all(tmp_path)


def test_the_same_criterion_twice_in_a_case_is_an_error(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "qualification_labels.csv",
        QUALIFICATION_HEADER + "a1,Acme,,,,,,Size,,met,\na1,,,,,,,Size,,not_met,\n",
    )
    with pytest.raises(LabelError, match="appears twice"):
        build_all(tmp_path)


def test_a_renamed_column_is_reported_not_silently_ignored(tmp_path: Path) -> None:
    _write(tmp_path, "qualification_labels.csv", "case_id,company,label\na1,Acme,met\n")
    with pytest.raises(LabelError, match=r"missing column\(s\)"):
        build_all(tmp_path)


def test_a_utf8_byte_order_mark_from_excel_does_not_break_the_header(tmp_path: Path) -> None:
    text = QUALIFICATION_HEADER + "a1,Acme,,,,,,Size,,met,\n"
    (tmp_path / "qualification_labels.csv").write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    assert len(build_all(tmp_path)["qualification"]) == 1


def test_role_labels_need_the_categories_and_only_accept_real_ones(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "role_labels.csv",
        ROLE_HEADER
        + "r1,Northbank,Banking,A bank.,p1,Head of IT Procurement,director,Vendor / IT,\n",
    )
    with pytest.raises(LabelError, match="needs role_categories.csv"):
        build_all(tmp_path)

    _write(
        tmp_path,
        "role_categories.csv",
        CATEGORY_HEADER + "Vendor / IT,People who buy IT services,yes\nFinance,Budget owners,no\n",
    )
    built = build_all(tmp_path)["role_relevance"]
    (case,) = built
    assert case["expect"] == {"matches": {"p1": "Vendor / IT"}, "all_answered": True}
    assert case["input"]["categories"][0] == {
        "name": "Vendor / IT",
        "description": "People who buy IT services",
        "is_primary_target": True,
    }

    _write(
        tmp_path,
        "role_labels.csv",
        ROLE_HEADER + "r1,Northbank,Banking,A bank.,p1,Head of IT,director,Procurement,\n",
    )
    with pytest.raises(LabelError, match="is not one of your categories"):
        build_all(tmp_path)


def test_role_labels_build_matches_and_the_word_none_means_no_match(tmp_path: Path) -> None:
    _write(tmp_path, "role_categories.csv", CATEGORY_HEADER + "Vendor / IT,Buyers,yes\n")
    _write(
        tmp_path,
        "role_labels.csv",
        ROLE_HEADER
        + "r1,Northbank,Banking,A bank.,p1,Head of IT Procurement,director,Vendor / IT,buys\n"
        + "r1,,,,p2,Pastry Chef,staff,none,no fit\n"
        + "r1,,,,p3,Receptionist,staff,,blank means no fit too\n",
    )
    (case,) = build_all(tmp_path)["role_relevance"]
    assert case["expect"]["matches"] == {"p1": "Vendor / IT", "p2": None, "p3": None}
    assert [c["id"] for c in case["input"]["contacts"]] == ["p1", "p2", "p3"]


def test_contact_labels_accept_several_roles_and_refuse_unknown_ones(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "contact_labels.csv",
        CONTACT_HEADER
        + "c1,Northbank,Banking,cloud migration,Cloud migration,Moves to the cloud,p1,CIO,c_level,"
        "decision_maker|influencer,,decides\n"
        + "c1,,,,,,p2,Marketing Head,director,,decision_maker,not theirs\n",
    )
    (case,) = build_all(tmp_path)["contact_relevance"]
    assert case["expect"] == {
        "roles_in": {"p1": ["decision_maker", "influencer"]},
        "roles_not": {"p2": ["decision_maker"]},
    }
    assert case["input"]["product"]["name"] == "Cloud migration"

    _write(
        tmp_path,
        "contact_labels.csv",
        CONTACT_HEADER + "c1,Northbank,Banking,cloud migration,,,p1,CIO,,boss,,\n",
    )
    with pytest.raises(LabelError, match="unknown role"):
        build_all(tmp_path)

    _write(
        tmp_path,
        "contact_labels.csv",
        CONTACT_HEADER + "c1,Northbank,Banking,cloud migration,,,p1,CIO,,,,\n",
    )
    with pytest.raises(LabelError, match="expected_roles or not_roles"):
        build_all(tmp_path)


def test_a_label_cannot_take_the_id_of_a_hand_written_case(
    tmp_path: Path, _isolated_cases: Path
) -> None:
    hand_written = {"id": "qualification-label-a1"}
    (_isolated_cases / "qualification.jsonl").write_text(
        json.dumps(hand_written) + "\n", encoding="utf-8"
    )
    _write(tmp_path, "qualification_labels.csv", QUALIFICATION_HEADER + "a1,Acme,,,,,,Size,,met,\n")
    with pytest.raises(LabelError, match="already used by a hand-written case"):
        build_all(tmp_path)


def test_a_dry_run_writes_nothing_and_yes_writes_cases_that_load_and_validate(
    tmp_path: Path, _isolated_cases: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    labels = tmp_path / "labels"
    labels.mkdir()
    _write(labels, "qualification_labels.csv", QUALIFICATION_HEADER + "a1,Acme,,,,,,Size,,met,\n")

    assert main(["--dir", str(labels)]) == 0
    assert "Dry run" in capsys.readouterr().out
    assert list(_isolated_cases.glob("*.jsonl")) == []

    assert main(["--dir", str(labels), "--yes"]) == 0
    written = _isolated_cases / "accuracy_qualification.jsonl"
    assert written.exists()
    cases = load_cases(_isolated_cases)
    validate_cases(cases)
    assert [c.id for c in cases] == ["qualification-label-a1"]
    # The person is told what to do next: the reports no longer cover the new cases.
    assert "predate the new cases" in capsys.readouterr().out


def test_a_mistake_stops_everything_and_exits_with_a_message(
    tmp_path: Path, _isolated_cases: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    labels = tmp_path / "labels"
    labels.mkdir()
    _write(
        labels, "qualification_labels.csv", QUALIFICATION_HEADER + "a1,Acme,,,,,,Size,,perhaps,\n"
    )
    assert main(["--dir", str(labels), "--yes"]) == 2
    assert "Cannot import the labels" in capsys.readouterr().err
    assert list(_isolated_cases.glob("*.jsonl")) == []
