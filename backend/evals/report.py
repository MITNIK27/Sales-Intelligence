"""Results of one eval run, written as JSON next to the earlier ones so a change shows as a diff.

A report is named by task, prompt version and model (`evals/reports/<task>-<version>-<model>.json`).
The governance check for G5 looks for these files: a prompt version with no report has not been
measured."""

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.graders import Check

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


@dataclass
class CaseResult:
    case_id: str
    tags: tuple[str, ...]
    checks: list[Check] = field(default_factory=list)
    error: str | None = None  # the model call failed or returned nothing usable
    output: str | None = None  # the answer, kept (shortened) so a failure can be read
    # With --repeat: how many times the case ran and how many of those runs passed. `passed` is
    # strict (every run must pass); `flaky` is the in-between that one run cannot show.
    runs: int = 1
    passes: int | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and all(check.ok for check in self.checks)

    @property
    def flaky(self) -> bool:
        return self.runs > 1 and self.passes is not None and 0 < self.passes < self.runs


@dataclass
class Report:
    task: str
    prompt_version: str
    model: str
    results: list[CaseResult]
    usage: dict[str, float] = field(default_factory=dict)  # calls, tokens, estimated cost
    repeat: int = 1  # how many times each case was run
    date: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))

    def summary(self) -> dict[str, Any]:
        by_tag: dict[str, dict[str, int]] = {}
        for result in self.results:
            for tag in result.tags:
                counts = by_tag.setdefault(tag, {"passed": 0, "total": 0})
                counts["total"] += 1
                counts["passed"] += int(result.passed)
        return {
            "total": len(self.results),
            "passed": sum(result.passed for result in self.results),
            "errors": sum(result.error is not None for result in self.results),
            "flaky": sum(result.flaky for result in self.results),
            "by_tag": by_tag,
        }


def _safe(part: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", part).strip("-") or "unknown"


def report_filename(task: str, prompt_version: str, model: str) -> str:
    return f"{_safe(task)}-{_safe(prompt_version)}-{_safe(model)}.json"


def _result_dict(r: CaseResult) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "case_id": r.case_id,
        "tags": list(r.tags),
        "passed": r.passed,
        "error": r.error,
        "checks": [
            {"name": c.name, "ok": c.ok, **({"detail": c.detail} if c.detail else {})}
            for c in r.checks
        ],
    }
    if r.runs > 1:
        entry["runs"] = r.runs
        entry["passes"] = r.passes
    if not r.passed and r.output is not None:
        entry["output"] = r.output  # only for failures, so a report stays small
    return entry


def to_dict(report: Report) -> dict[str, Any]:
    return {
        "task": report.task,
        "prompt_version": report.prompt_version,
        "model": report.model,
        "date": report.date,
        **({"repeat": report.repeat} if report.repeat > 1 else {}),
        "summary": report.summary(),
        "usage": report.usage,
        "results": [_result_dict(r) for r in report.results],
    }


def write_report(report: Report, directory: Path = REPORTS_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / report_filename(report.task, report.prompt_version, report.model)
    path.write_text(json.dumps(to_dict(report), indent=2) + "\n", encoding="utf-8")
    return path


def previous_report(
    task: str, directory: Path = REPORTS_DIR, exclude: Path | None = None
) -> dict[str, Any] | None:
    """The most recent earlier report for this task (any prompt version or model), or None."""
    newest: dict[str, Any] | None = None
    for path in directory.glob(f"{_safe(task)}-*.json"):
        if exclude is not None and path.resolve() == exclude.resolve():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("task") == task and (newest is None or data["date"] > newest["date"]):
            newest = data
    return newest


def diff_reports(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Plain lines saying what changed between two reports of the same task."""
    lines = [
        f"compared with {old['prompt_version']} on {old['model']} ({old['date'][:10]}): "
        f"{old['summary']['passed']}/{old['summary']['total']} -> "
        f"{new['summary']['passed']}/{new['summary']['total']} passed"
    ]
    old_by_id = {r["case_id"]: r["passed"] for r in old["results"]}
    for result in new["results"]:
        before = old_by_id.get(result["case_id"])
        if before is True and not result["passed"]:
            lines.append(f"  now failing: {result['case_id']}")
        elif before is False and result["passed"]:
            lines.append(f"  now passing: {result['case_id']}")
    new_ids = {r["case_id"] for r in new["results"]}
    lines += [f"  no longer run: {case_id}" for case_id in old_by_id if case_id not in new_ids]
    return lines
