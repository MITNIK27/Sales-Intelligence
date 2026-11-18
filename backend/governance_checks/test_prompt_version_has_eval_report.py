"""G5: a prompt change comes with an eval report, so nobody ships a prompt nobody measured.

Every prompt version in the app is either measured by an eval task, which means a report for the
CURRENT version exists in `evals/reports/` and covers every current case, or listed in UNMEASURED
with a reason. A prompt version nobody has accounted for fails, and so does a measured one whose
report is missing or older than the cases. Bumping a version, or adding a case, therefore means
running the eval again (`python -m evals.run --task <task> --yes`) and committing the report.

Reports record what happened, including failures; this check asks that the measurement exists,
not that every case passed.

A new eval task has no report until someone runs it with real models (never automatic), so it
may be listed in AWAITING_FIRST_REPORT. That list only shrinks: once a report exists, the task
must be taken off it."""

import json
import re
from pathlib import Path
from typing import Any

from evals.cases import load_cases
from evals.report import REPORTS_DIR
from evals.tasks import TASKS

APP = Path(__file__).resolve().parent.parent / "app"

# The file that defines each measured prompt version, and the eval task that measures it.
MEASURED = {
    "modules/offerings/extractor.py": "offering_extraction",
    "modules/draft/prompts.py": "draft",
    "modules/draft/refine.py": "draft_refine",
    "modules/qualification/prompts.py": "qualification",
    "modules/quicklook/prompts.py": "quicklook",
    "modules/ai_recommendation/recommendation_generator.py": "recommendation",
    "modules/opportunity/prompts.py": "opportunity_assessment",
    "modules/opportunity/fit.py": "offering_fit",
    "modules/opportunity/relevance.py": "contact_relevance",
    "modules/role_relevance/prompts.py": "role_relevance",
}

# Prompt versions no eval task covers yet. Each one needs a task and cases to leave this list.
# (The area-suggestion prompt shares opportunity/prompts.py with the assessment and is not
# exercised by its own task yet.)
UNMEASURED: dict[str, str] = {}

# Tasks that exist and have cases but whose first report has not been committed yet. Run
# `python -m evals.run --task <task> --yes`, commit the report, and take the task off this list.
AWAITING_FIRST_REPORT = {
    "draft_refine": "run it once with real models and commit the report",
    "recommendation": "run it once with real models and commit the report",
    "opportunity_assessment": "run it once with real models and commit the report",
    "offering_fit": "run it once with real models and commit the report",
    "contact_relevance": "run it once with real models and commit the report",
    "role_relevance": "run it once with real models and commit the report",
}

_VERSION = re.compile(r'^[A-Z_]*PROMPT_VERSION = "', re.MULTILINE)


def _files_with_a_prompt_version() -> set[str]:
    return {
        path.relative_to(APP).as_posix()
        for path in APP.rglob("*.py")
        if _VERSION.search(path.read_text(encoding="utf-8"))
    }


def test_every_prompt_version_is_measured_or_listed_as_unmeasured() -> None:
    unknown = _files_with_a_prompt_version() - set(MEASURED) - set(UNMEASURED)
    assert not unknown, (
        f"{sorted(unknown)} define a prompt version no eval accounts for. Add an eval task and "
        "cases and list the file in MEASURED, or list it in UNMEASURED with a reason "
        "(docs/ai-governance.md, G5)."
    )


def test_unmeasured_files_still_define_a_prompt_version() -> None:
    stale = set(UNMEASURED) - _files_with_a_prompt_version()
    assert not stale, f"{sorted(stale)} no longer define a prompt version; remove from UNMEASURED"


def test_measured_files_name_a_real_task() -> None:
    assert set(MEASURED.values()) == set(TASKS), "every eval task must be tied to a prompt file"


def _report_for(task: str) -> dict[str, Any] | None:
    version = TASKS[task].prompt_version
    for path in sorted(REPORTS_DIR.glob(f"{task}-{version}-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("task") == task and data.get("prompt_version") == version:
            found: dict[str, Any] = data
            return found
    return None


def test_every_measured_prompt_version_has_a_report_that_covers_every_case() -> None:
    problems = []
    for task, definition in TASKS.items():
        report = _report_for(task)
        if report is None:
            if task in AWAITING_FIRST_REPORT:
                continue
            problems.append(
                f"{task} {definition.prompt_version}: no report. Run "
                f"`python -m evals.run --task {task} --yes` and commit it."
            )
            continue
        if task in AWAITING_FIRST_REPORT:
            problems.append(
                f"{task} now has a report. Remove it from AWAITING_FIRST_REPORT "
                "so the list only shrinks."
            )
        reported = {result["case_id"] for result in report["results"]}
        missing = {case.id for case in load_cases(task=task)} - reported
        if missing:
            problems.append(
                f"{task} {definition.prompt_version}: the report predates cases {sorted(missing)}. "
                f"Run `python -m evals.run --task {task} --yes` again."
            )
    assert not problems, "\n".join(problems)


def test_the_awaiting_list_only_names_real_tasks() -> None:
    assert set(AWAITING_FIRST_REPORT) <= set(TASKS)
