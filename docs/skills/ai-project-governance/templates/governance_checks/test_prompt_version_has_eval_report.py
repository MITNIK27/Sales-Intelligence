"""G5: a prompt change comes with an eval report, so nobody ships a prompt nobody measured.

Every prompt version in the app is either measured by an eval task (a report for the CURRENT
version exists and covers every current case) or listed in UNMEASURED with a reason. A task that has
cases but no report yet may wait in AWAITING_FIRST_REPORT; that list only shrinks, because the check
fails once a report exists and the entry is still there.

TODO: set APP, MEASURED (file that defines a prompt version -> eval task name), and import your
TASKS registry, REPORTS_DIR and case loader from the eval harness."""

import json
import re
from pathlib import Path
from typing import Any

from evals.cases import load_cases  # TODO
from evals.report import REPORTS_DIR  # TODO
from evals.tasks import TASKS  # TODO: dict of task name -> object with .prompt_version

APP = Path(__file__).resolve().parent.parent / "app"  # TODO

MEASURED: dict[str, str] = {}  # {"llm/prompts/summary.py": "summary", ...}
UNMEASURED: dict[str, str] = {}  # {"llm/prompts/other.py": "no eval task yet"}
AWAITING_FIRST_REPORT: dict[str, str] = {}  # {"task": "run it once and commit the report"}

_VERSION = re.compile(r'^[A-Z_]*PROMPT_VERSION = "', re.MULTILINE)


def _files_with_a_prompt_version() -> set[str]:
    return {
        path.relative_to(APP).as_posix()
        for path in APP.rglob("*.py")
        if _VERSION.search(path.read_text(encoding="utf-8"))
    }


def test_every_prompt_version_is_measured_or_listed_as_unmeasured() -> None:
    unknown = _files_with_a_prompt_version() - set(MEASURED) - set(UNMEASURED)
    assert not unknown, f"{sorted(unknown)} define a prompt version no eval accounts for (G5)"


def test_unmeasured_files_still_define_a_prompt_version() -> None:
    stale = set(UNMEASURED) - _files_with_a_prompt_version()
    assert not stale, f"{sorted(stale)} no longer define a prompt version; remove from UNMEASURED"


def test_every_task_is_tied_to_a_prompt_file() -> None:
    assert set(MEASURED.values()) == set(TASKS)


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
            if task not in AWAITING_FIRST_REPORT:
                problems.append(f"{task} {definition.prompt_version}: no report. Run the eval and commit it.")
            continue
        if task in AWAITING_FIRST_REPORT:
            problems.append(f"{task} now has a report. Remove it from AWAITING_FIRST_REPORT.")
        reported = {result["case_id"] for result in report["results"]}
        missing = {case.id for case in load_cases(task=task)} - reported
        if missing:
            problems.append(f"{task}: the report predates cases {sorted(missing)}. Run it again.")
    assert not problems, "\n".join(problems)
