"""Runs the cases of one task against a runtime and builds the report. No command-line handling and
no choice of model here (that is `evals/run.py`), so it can be tested with fake models.

Cases run one after another, with an optional pause between them, because the free tiers limit how
many calls fit in a minute. A case whose model call fails is an error in the report, not a crash,
so one bad call does not lose the rest of the run. Usage rows are collected in memory and never
written to the database."""

import asyncio
import json
from collections.abc import Sequence

from app.modules.usage.context import usage_scope
from app.modules.usage.models import ApiUsage
from app.modules.usage.recorder import set_usage_sink
from evals.cases import Case
from evals.report import CaseResult, Report
from evals.tasks import Runtime, Task

_OUTPUT_CHARS = 2000


def _redacted(text: str, secrets: Sequence[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


async def _run_case(
    task: Task, case: Case, runtime: Runtime, secrets: Sequence[str]
) -> CaseResult:
    try:
        output = await task.run(case, runtime)
    except Exception as exc:  # noqa: BLE001 - a failed call is a result, not a crash
        message = _redacted(f"{type(exc).__name__}: {exc}", secrets)
        return CaseResult(case.id, case.tags, error=message)
    shown = json.dumps(output, ensure_ascii=False, default=str)[:_OUTPUT_CHARS]
    return CaseResult(case.id, case.tags, task.grade(case, output), output=shown)


def _usage(rows: list[ApiUsage]) -> dict[str, float]:
    llm = [row for row in rows if row.kind == "llm"]
    return {
        "calls": len(llm),
        "call_errors": sum(row.status == "error" for row in llm),
        "tokens_in": sum(row.tokens_in or 0 for row in llm),
        "tokens_out": sum(row.tokens_out or 0 for row in llm),
        "cached_tokens": sum(row.cached_tokens or 0 for row in llm),
        "est_cost_usd": round(sum(row.est_cost_usd or 0.0 for row in llm), 6),
    }


async def run_task(
    task: Task,
    cases: list[Case],
    runtime: Runtime,
    delay_seconds: float = 0.0,
    secrets: Sequence[str] = (),
) -> Report:
    rows: list[ApiUsage] = []

    async def collect(row: ApiUsage) -> None:
        rows.append(row)

    previous = set_usage_sink(collect)
    results: list[CaseResult] = []
    try:
        for position, case in enumerate(cases):
            if position and delay_seconds:
                await asyncio.sleep(delay_seconds)
            with usage_scope(task=f"eval:{task.name}"):
                results.append(await _run_case(task, case, runtime, secrets))
    finally:
        set_usage_sink(previous)
    return Report(task.name, task.prompt_version, runtime.model, results, usage=_usage(rows))
