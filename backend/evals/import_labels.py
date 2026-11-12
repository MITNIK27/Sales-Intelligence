"""Turns the team's labels into eval cases, so accuracy is measured against what people decided and
not against what we guessed.

People label in a spreadsheet (CSV files in `evals/labels/`, templates there); this checks every row
and writes `evals/cases/accuracy_<task>.jsonl`. It only reads the label files and writes case files:
no database, no model, no network.

Dry run by default: it reports what it found and writes nothing. Usage (from backend/, venv active):
    python -m evals.import_labels                 # check the labels and show what would be written
    python -m evals.import_labels --yes           # write the case files
    python -m evals.import_labels --dir path/to/labels

Rows whose case_id starts with EXAMPLE are the template's examples and are skipped. Anything wrong
is reported with the file and row, and nothing is written until all of it is right."""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from evals.cases import CASES_DIR, Case, CaseError
from evals.tasks import validate_cases

LABELS_DIR = Path(__file__).resolve().parent / "labels"

VERDICTS = ("met", "not_met", "could_not_determine")
ROLES = ("decision_maker", "influencer", "user", "not_relevant")


class LabelError(ValueError):
    """A label file is wrong. The message names the file and row, so it can be fixed in place."""


Rows = list[tuple[int, dict[str, str]]]  # (row number in the file, values)


def read_rows(path: Path, columns: tuple[str, ...]) -> Rows:
    """The label rows of one file, with surrounding spaces removed. Blank rows and the template's
    EXAMPLE rows are left out. Missing columns are an error: a renamed header must not silently
    drop a label."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in columns if c not in (reader.fieldnames or [])]
        if missing:
            raise LabelError(f"{path.name}: missing column(s) {missing}")
        rows: Rows = []
        for number, raw in enumerate(reader, start=2):  # row 1 is the header
            values = {k: (v or "").strip() for k, v in raw.items() if k}
            if not any(values.values()):
                continue
            if values.get("case_id", "").upper().startswith("EXAMPLE"):
                continue
            rows.append((number, values))
        return rows


def _need(where: str, values: dict[str, str], *names: str) -> None:
    empty = [n for n in names if not values.get(n)]
    if empty:
        raise LabelError(f"{where}: {', '.join(empty)} must not be empty")


def _group(path: Path, rows: Rows) -> dict[str, Rows]:
    groups: dict[str, Rows] = defaultdict(list)
    for number, values in rows:
        _need(f"{path.name} row {number}", values, "case_id")
        groups[values["case_id"]].append((number, values))
    return groups


def _same(path: Path, group: Rows, name: str) -> str:
    """One value per case for a company-level column: the first filled one, and a later row that
    disagrees is an error rather than a silent pick."""
    seen = {v[name] for _, v in group if v.get(name)}
    if len(seen) > 1:
        rows = [n for n, v in group if v.get(name)]
        raise LabelError(
            f"{path.name} rows {rows}: case {group[0][1]['case_id']!r} has different values for "
            f"{name}: {sorted(seen)}"
        )
    return next(iter(seen), "")


def _case(
    task: str, key: str, data: dict[str, Any], expect: dict[str, Any], note: str
) -> dict[str, Any]:
    return {
        "id": f"{task}-label-{key}",
        "task": task,
        "tags": ["accuracy"],
        "input": data,
        "expect": expect,
        "note": note or "Labelled by the team.",
    }


# --- qualification ------------------------------------------------------------------------------

QUALIFICATION_COLUMNS = (
    "case_id",
    "company_name",
    "company_domain",
    "company_industry",
    "company_size",
    "company_description",
    "evidence",
    "criterion_name",
    "criterion_description",
    "label",
    "why",
)


def build_qualification(path: Path, rows: Rows) -> list[dict[str, Any]]:
    cases = []
    for key, group in _group(path, rows).items():
        company_name = _same(path, group, "company_name")
        if not company_name:
            raise LabelError(f"{path.name}: case {key!r} has no company_name")
        criteria: dict[str, dict[str, str]] = {}
        verdicts: dict[str, str] = {}
        signals: list[dict[str, str]] = []
        notes: list[str] = []
        for number, values in group:
            where = f"{path.name} row {number}"
            _need(where, values, "criterion_name", "label")
            if values["label"] not in VERDICTS:
                raise LabelError(
                    f"{where}: label must be one of {list(VERDICTS)}, got {values['label']!r}"
                )
            name = values["criterion_name"]
            if name in verdicts:
                raise LabelError(f"{where}: criterion {name!r} appears twice for case {key!r}")
            verdicts[name] = values["label"]
            criteria[name] = {"name": name, "description": values.get("criterion_description", "")}
            if (
                values.get("evidence")
                and {"signal_type": "news", "text": values["evidence"]} not in signals
            ):
                signals.append({"signal_type": "news", "text": values["evidence"]})
            if values.get("why"):
                notes.append(f"{name}: {values['why']}")
        company = {
            "name": company_name,
            "domain": _same(path, group, "company_domain") or None,
            "industry": _same(path, group, "company_industry") or None,
            "employee_count_range": _same(path, group, "company_size") or None,
            "description": _same(path, group, "company_description") or None,
        }
        cases.append(
            _case(
                "qualification",
                key,
                {"company": company, "signals": signals, "criteria": list(criteria.values())},
                {"verdicts": verdicts, "quotes_valid": True},
                "; ".join(notes),
            )
        )
    return cases


# --- role relevance -----------------------------------------------------------------------------

ROLE_COLUMNS = (
    "case_id",
    "company_name",
    "company_industry",
    "company_description",
    "contact_id",
    "role_title",
    "seniority",
    "expected_category",
    "why",
)
CATEGORY_COLUMNS = ("name", "description", "is_primary_target")
NO_MATCH = {"", "none", "no match", "null"}


def read_categories(path: Path) -> list[dict[str, Any]]:
    categories = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in CATEGORY_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise LabelError(f"{path.name}: missing column(s) {missing}")
        for raw in reader:
            values = {k: (v or "").strip() for k, v in raw.items() if k}
            if not values.get("name") or values["name"].upper().startswith("EXAMPLE"):
                continue
            categories.append(
                {
                    "name": values["name"],
                    "description": values.get("description") or None,
                    "is_primary_target": values.get("is_primary_target", "").lower()
                    in ("yes", "true", "1", "y"),
                }
            )
    if not categories:
        raise LabelError(f"{path.name}: no role categories (copy your real ones from the app)")
    return categories


def build_role_relevance(
    path: Path, rows: Rows, categories: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    names = {c["name"] for c in categories}
    cases = []
    for key, group in _group(path, rows).items():
        company_name = _same(path, group, "company_name")
        if not company_name:
            raise LabelError(f"{path.name}: case {key!r} has no company_name")
        contacts: list[dict[str, Any]] = []
        matches: dict[str, str | None] = {}
        notes: list[str] = []
        for number, values in group:
            where = f"{path.name} row {number}"
            _need(where, values, "contact_id")
            contact_id = values["contact_id"]
            if contact_id in matches:
                raise LabelError(
                    f"{where}: contact_id {contact_id!r} appears twice in case {key!r}"
                )
            expected = values.get("expected_category", "")
            if expected.lower() in NO_MATCH:
                matches[contact_id] = None
            elif expected in names:
                matches[contact_id] = expected
            else:
                raise LabelError(
                    f"{where}: expected_category {expected!r} is not one of your categories "
                    f"{sorted(names)} (leave it blank when no category fits)"
                )
            contacts.append(
                {
                    "id": contact_id,
                    "role_title": values.get("role_title") or None,
                    "seniority": values.get("seniority") or None,
                }
            )
            if values.get("why"):
                notes.append(f"{contact_id}: {values['why']}")
        company = {
            "name": company_name,
            "industry": _same(path, group, "company_industry") or None,
            "description": _same(path, group, "company_description") or None,
        }
        cases.append(
            _case(
                "role_relevance",
                key,
                {"company": company, "contacts": contacts, "categories": categories},
                {"matches": matches, "all_answered": True},
                "; ".join(notes),
            )
        )
    return cases


# --- contact relevance --------------------------------------------------------------------------

CONTACT_COLUMNS = (
    "case_id",
    "company_name",
    "company_industry",
    "area_label",
    "offering_name",
    "offering_description",
    "contact_id",
    "role_title",
    "seniority",
    "expected_roles",
    "not_roles",
    "why",
)


def _roles(where: str, text: str) -> list[str]:
    roles = [r.strip() for r in text.replace(";", "|").split("|") if r.strip()]
    bad = [r for r in roles if r not in ROLES]
    if bad:
        raise LabelError(f"{where}: unknown role(s) {bad}; use {list(ROLES)} separated by |")
    return roles


def build_contact_relevance(path: Path, rows: Rows) -> list[dict[str, Any]]:
    cases = []
    for key, group in _group(path, rows).items():
        company_name = _same(path, group, "company_name")
        area = _same(path, group, "area_label")
        if not company_name or not area:
            raise LabelError(f"{path.name}: case {key!r} needs company_name and area_label")
        contacts: list[dict[str, Any]] = []
        allowed: dict[str, list[str]] = {}
        forbidden: dict[str, list[str]] = {}
        notes: list[str] = []
        for number, values in group:
            where = f"{path.name} row {number}"
            _need(where, values, "contact_id")
            contact_id = values["contact_id"]
            good = _roles(where, values.get("expected_roles", ""))
            bad = _roles(where, values.get("not_roles", ""))
            if not good and not bad:
                raise LabelError(f"{where}: give expected_roles or not_roles (or both)")
            if contact_id in {c["id"] for c in contacts}:
                raise LabelError(
                    f"{where}: contact_id {contact_id!r} appears twice in case {key!r}"
                )
            if good:
                allowed[contact_id] = good
            if bad:
                forbidden[contact_id] = bad
            contacts.append(
                {
                    "id": contact_id,
                    "role_title": values.get("role_title") or None,
                    "seniority": values.get("seniority") or None,
                }
            )
            if values.get("why"):
                notes.append(f"{contact_id}: {values['why']}")
        data: dict[str, Any] = {
            "company": {
                "name": company_name,
                "industry": _same(path, group, "company_industry") or None,
            },
            "area_label": area,
            "contacts": contacts,
        }
        offering = _same(path, group, "offering_name")
        if offering:
            data["product"] = {
                "name": offering,
                "description": _same(path, group, "offering_description") or None,
                "kind": "service",
            }
        expect: dict[str, Any] = {}
        if allowed:
            expect["roles_in"] = allowed
        if forbidden:
            expect["roles_not"] = forbidden
        cases.append(_case("contact_relevance", key, data, expect, "; ".join(notes)))
    return cases


# --- the whole import ---------------------------------------------------------------------------


def build_all(directory: Path) -> dict[str, list[dict[str, Any]]]:
    """Every label file present in `directory`, checked and turned into cases, by task. Raises
    `LabelError` for the first problem; nothing is half-built."""
    built: dict[str, list[dict[str, Any]]] = {}

    qualification = directory / "qualification_labels.csv"
    if qualification.exists():
        rows = read_rows(qualification, QUALIFICATION_COLUMNS)
        if rows:
            built["qualification"] = build_qualification(qualification, rows)

    roles = directory / "role_labels.csv"
    if roles.exists():
        rows = read_rows(roles, ROLE_COLUMNS)
        if rows:
            categories_file = directory / "role_categories.csv"
            if not categories_file.exists():
                raise LabelError(
                    "role_labels.csv needs role_categories.csv beside it (your real categories)"
                )
            built["role_relevance"] = build_role_relevance(
                roles, rows, read_categories(categories_file)
            )

    contacts = directory / "contact_labels.csv"
    if contacts.exists():
        rows = read_rows(contacts, CONTACT_COLUMNS)
        if rows:
            built["contact_relevance"] = build_contact_relevance(contacts, rows)

    # The cases must be valid for their tasks, and ids must not clash with the hand-written ones.
    existing = {
        json.loads(line)["id"]
        for p in CASES_DIR.glob("*.jsonl")
        if not p.name.startswith("accuracy_")
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    for cases in built.values():
        for raw in cases:
            if raw["id"] in existing:
                raise LabelError(f"case id {raw['id']!r} is already used by a hand-written case")
        validate_cases(
            [
                Case(r["id"], r["task"], tuple(r["tags"]), r["input"], r["expect"], r["note"])
                for r in cases
            ]
        )
    return built


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--dir", type=Path, default=LABELS_DIR, help="where the label CSV files are"
    )
    parser.add_argument("--yes", action="store_true", help="write the case files")
    args = parser.parse_args(argv)

    try:
        built = build_all(args.dir)
    except (LabelError, CaseError) as exc:
        print(f"Cannot import the labels: {exc}", file=sys.stderr)
        return 2
    if not built:
        print(f"No labels found in {args.dir} (templates only, or no label files yet).")
        return 0
    for task, cases in built.items():
        print(f"  {task}: {len(cases)} labelled case(s)")
    if not args.yes:
        print("\nDry run: nothing written. Add --yes to write the case files.")
        return 0
    for task, cases in built.items():
        path = CASES_DIR / f"accuracy_{task}.jsonl"
        path.write_text(
            "\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n", encoding="utf-8"
        )
        print(f"wrote {path.name}")
    print(
        "\nThe reports for these tasks now predate the new cases. Run "
        "`python -m evals.run --task <task> --repeat 3 --yes` and commit the reports."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
