"""Runs evals against the real models. This spends free-tier quota (or money on a paid key), so it
does nothing until you add --yes; without it, it shows what it would run. It is never part of
pytest.

By default each task uses the same model the app uses for it, and only the FIRST vendor in that
order, so every answer comes from one model and a report can be compared with another. Add
--fallback to run the whole chain the way the app does.

Usage (from backend/, venv active, keys in backend/.env):
    python -m evals.run --task quicklook                 # shows the plan, runs nothing
    python -m evals.run --task quicklook --yes           # runs it and writes a report
    python -m evals.run --all --yes
    python -m evals.run --task draft --tag injection --yes
    python -m evals.run --task quicklook --repeat 3 --yes   # each case 3 times, shows flaky ones
    python -m evals.run --task quicklook --gemini-model gemini-2.5-flash --yes   # try a model
    python -m evals.run --task offering_extraction --llm-order gemini --yes
"""

import argparse
import asyncio
import sys
from typing import Any

from app.core.config import Settings, get_settings
from app.modules.ai_recommendation.recommendation_generator import GeminiRecommendationGenerator
from app.modules.draft.draft_generator import GeminiDraftGenerator
from app.modules.llm.structured import build_structured_llm
from app.modules.qualification.qualification_generator import GeminiQualificationGenerator
from app.modules.role_relevance.role_relevance_generator import GeminiRoleRelevanceGenerator
from evals.cases import Case, load_cases
from evals.report import Report, diff_reports, previous_report, to_dict, write_report
from evals.runner import run_task
from evals.tasks import TASKS, Runtime, validate_cases

MAX_REPEAT = 10  # a guard for quota; raise it deliberately if you need more
# Tasks whose app code calls Gemini directly (no vendor chain), so only a Gemini key is needed.
GEMINI_ONLY_TASKS = ("qualification", "draft", "recommendation", "role_relevance")


def _repeat_count(value: str) -> int:
    try:
        count = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} is not a whole number") from exc
    if not 1 <= count <= MAX_REPEAT:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_REPEAT}")
    return count


def _vendors_to_use(order: str, fallback: bool) -> str:
    names = [name.strip() for name in order.split(",") if name.strip()]
    return ",".join(names if fallback else names[:1])


def build_runtime(
    task: str, settings: Settings, llm_order: str | None, fallback: bool, groq_model: str | None
) -> tuple[Runtime, set[str]]:
    """The runtime for a task and the vendors it needs a key for. Quick Look and the offerings
    importer use the same order the app uses for them; qualification and drafts are Gemini only."""
    if task == "offering_extraction":
        order = llm_order or settings.offerings_llm_order
    else:
        order = llm_order or settings.opportunity_llm_order
    llm = build_structured_llm(settings, _vendors_to_use(order, fallback), groq_model)
    if task in GEMINI_ONLY_TASKS:
        label, needs = settings.gemini_model, {"gemini"}
    else:
        label = "+".join(model for _, model in llm.vendors) or "none"
        needs = {vendor for vendor, _ in llm.vendors}
    runtime = Runtime(
        llm=llm,
        qualification=GeminiQualificationGenerator(settings),
        draft=GeminiDraftGenerator(settings),
        model=label,
        recommendation=GeminiRecommendationGenerator(settings),
        role_relevance=GeminiRoleRelevanceGenerator(settings),
    )
    return runtime, needs


def _missing_keys(needs: set[str], settings: Settings) -> list[str]:
    keys = {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key}
    return sorted(f"{name.upper()}_API_KEY" for name in needs if not keys.get(name))


def _select(cases: list[Case], task: str, tags: list[str], ids: list[str]) -> list[Case]:
    chosen = [c for c in cases if c.task == task]
    if tags:
        chosen = [c for c in chosen if set(tags) & set(c.tags)]
    if ids:
        chosen = [c for c in chosen if c.id in ids]
    return chosen


def _print_report(report: Report, previous: dict[str, Any] | None, path: str | None) -> None:
    summary = report.summary()
    by_tag = sorted(summary["by_tag"].items())
    tags = ", ".join(f"{t} {c['passed']}/{c['total']}" for t, c in by_tag)
    print(f"\n{report.task}  {report.prompt_version}  {report.model}")
    print(f"  passed {summary['passed']}/{summary['total']}  ({tags})")
    if report.repeat > 1:
        flaky = summary["flaky"]
        print(f"  each case ran {report.repeat} times; flaky (some runs failed): {flaky}")
    usage = report.usage
    print(
        f"  usage: {int(usage.get('calls', 0))} calls "
        f"({int(usage.get('call_errors', 0))} failed), {int(usage.get('tokens_in', 0)):,} in, "
        f"{int(usage.get('tokens_out', 0)):,} out, {int(usage.get('cached_tokens', 0)):,} cached, "
        f"est ${usage.get('est_cost_usd', 0):.4f}"
    )
    for result in report.results:
        if result.passed:
            continue
        runs = f" (passed {result.passes} of {result.runs} runs)" if result.runs > 1 else ""
        print(f"  FAIL {result.case_id}{runs}")
        if result.error:
            print(f"    error: {result.error}")
        for check in result.checks:
            if not check.ok:
                print(f"    - {check.name}: {check.detail}")
        if result.output:
            print(f"    answer: {result.output[:400]}")
    if previous is not None:
        for line in diff_reports(previous, to_dict(report)):
            print(f"  {line}")
    if path:
        print(f"  report: {path}")


async def main(args: argparse.Namespace) -> int:
    settings = get_settings()
    if args.gemini_model:
        settings = settings.model_copy(update={"gemini_model": args.gemini_model})
    cases = load_cases()
    validate_cases(cases)

    names = list(TASKS) if args.all else args.task
    unknown_ids = set(args.case or []) - {c.id for c in cases}
    if unknown_ids:
        print(f"No such case id: {sorted(unknown_ids)}", file=sys.stderr)
        return 2

    plan: list[tuple[str, Runtime, list[Case], list[str]]] = []
    for name in names:
        runtime, needs = build_runtime(
            name, settings, args.llm_order, args.fallback, args.groq_model
        )
        selected = _select(cases, name, args.tag or [], args.case or [])
        if args.limit:
            selected = selected[: args.limit]
        plan.append((name, runtime, selected, _missing_keys(needs, settings)))

    print("Plan (this calls the real models and spends quota):")
    for name, runtime, selected, missing in plan:
        status = f"MISSING {', '.join(missing)}, will be skipped" if missing else "ready"
        calls = f", {len(selected) * args.repeat} runs" if args.repeat > 1 else ""
        print(f"  {name}: {len(selected)} case(s){calls} on {runtime.model} ({status})")
    if not args.yes:
        print("\nDry run: nothing was called. Add --yes to run it.")
        return 0

    secrets = [k for k in (settings.gemini_api_key, settings.groq_api_key) if k]
    failed = False
    for name, runtime, selected, missing in plan:
        if missing or not selected:
            continue
        report = await run_task(
            TASKS[name], selected, runtime, args.delay, secrets, args.repeat
        )
        previous = previous_report(name)
        path = None if args.no_write else str(write_report(report))
        _print_report(report, previous, path)
        failed = failed or report.summary()["passed"] < report.summary()["total"]
    return 1 if (failed and args.fail_on_failure) else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--task", action="append", choices=list(TASKS), help="a task (repeatable)")
    which.add_argument("--all", action="store_true", help="every task")
    parser.add_argument("--tag", action="append", help="only cases with this tag (repeatable)")
    parser.add_argument("--case", action="append", help="only this case id (repeatable)")
    parser.add_argument("--limit", type=int, help="at most N cases per task")
    parser.add_argument(
        "--repeat", type=_repeat_count, default=1, help=f"run each case N times, 1 to {MAX_REPEAT}"
    )
    parser.add_argument("--llm-order", help='vendors for Quick Look / offerings, "gemini,groq"')
    parser.add_argument("--fallback", action="store_true", help="use the whole vendor chain")
    parser.add_argument("--gemini-model", help="run with a different Gemini model")
    parser.add_argument("--groq-model", help="run with a different Groq model")
    parser.add_argument("--delay", type=float, default=3.0, help="seconds between cases (3)")
    parser.add_argument("--no-write", action="store_true", help="do not write a report file")
    parser.add_argument("--fail-on-failure", action="store_true", help="exit 1 if a case fails")
    parser.add_argument("--yes", action="store_true", help="actually run (calls the real models)")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
