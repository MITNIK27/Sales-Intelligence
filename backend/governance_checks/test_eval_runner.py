"""The eval runner, with fake models. Nothing here calls a real model: the runtime is fake, and the
command-line tests use settings with no keys, so no call can be made."""

from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.core.config import Settings
from app.modules.draft.draft_generator import DraftResult
from app.modules.usage import recorder
from app.modules.usage.recorder import record_usage
from evals import run as run_module
from evals.cases import Case, load_cases
from evals.report import to_dict
from evals.runner import run_task
from evals.tasks import TASKS, Runtime

SECRET = "sk-test-secret-123"


class _Draft:
    """A fake drafter. Which body it returns depends on the case, so one run has a pass, a
    failure and an error."""

    model_name = "fake"

    async def generate(self, company: Any, *args: Any, **kwargs: Any) -> DraftResult:
        await record_usage(provider="gemini", kind="llm", tokens_in=100, tokens_out=20)
        description = company.description or ""
        if "evil.example" in description:
            raise RuntimeError(f"request to https://x?key={SECRET} failed")
        body = "We cut costs by 85% with Globex." if "Globex" in str(args) else "Short and clean."
        return DraftResult(subject="Hi", body=body, chosen_option=1)


def _runtime() -> Runtime:
    return Runtime(
        llm=cast(Any, None), qualification=cast(Any, None), draft=cast(Any, _Draft()), model="fake"
    )


def _draft_cases(*ids: str) -> list[Case]:
    wanted = set(ids)
    return [c for c in load_cases() if c.id in wanted]


async def test_a_run_reports_passes_failures_errors_and_usage() -> None:
    cases = _draft_cases("draft-grounding-01", "draft-injection-01", "draft-injection-02")
    report = await run_task(TASKS["draft"], cases, _runtime(), secrets=[SECRET])
    by_id = {r.case_id: r for r in report.results}

    assert by_id["draft-grounding-01"].passed
    assert not by_id["draft-injection-01"].passed  # the fake invents 85% and Globex
    assert by_id["draft-injection-01"].output and "85%" in by_id["draft-injection-01"].output
    assert by_id["draft-injection-02"].error is not None
    assert SECRET not in by_id["draft-injection-02"].error  # the key is redacted
    assert report.usage["calls"] == 3 and report.usage["tokens_in"] == 300
    assert report.summary()["errors"] == 1
    assert (report.task, report.prompt_version, report.model) == (
        "draft",
        TASKS["draft"].prompt_version,
        "fake",
    )


async def test_usage_is_collected_in_memory_and_the_previous_sink_is_restored() -> None:
    before = recorder._sink
    await run_task(TASKS["draft"], _draft_cases("draft-grounding-01"), _runtime())
    assert recorder._sink is before


# --- model choice -------------------------------------------------------------------------------


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {"gemini_api_key": None, "groq_api_key": None}
    base.update(overrides)
    settings: Settings = cast(Any, Settings)(_env_file=None, **base)  # ignores .env
    return settings


def test_only_the_first_vendor_is_used_unless_the_whole_chain_is_asked_for() -> None:
    assert run_module._vendors_to_use("gemini,groq", fallback=False) == "gemini"
    assert run_module._vendors_to_use("gemini,groq", fallback=True) == "gemini,groq"


def test_each_task_uses_the_model_the_app_uses_for_it() -> None:
    settings = _settings(gemini_model="gem-x", groq_model="groq-y")
    quick, _ = run_module.build_runtime("quicklook", settings, None, False, None)
    assert quick.model == "gem-x"  # the app tries Gemini first for opportunity research
    offering, needs = run_module.build_runtime("offering_extraction", settings, None, False, None)
    assert offering.model == "groq-y" and needs == {"groq"}  # the importer tries Groq first
    draft, needs = run_module.build_runtime("draft", settings, None, False, None)
    assert draft.model == "gem-x" and needs == {"gemini"}
    other, _ = run_module.build_runtime("offering_extraction", settings, "gemini", False, None)
    assert other.model == "gem-x"


def test_missing_keys_are_named_without_showing_values() -> None:
    assert run_module._missing_keys({"gemini", "groq"}, _settings()) == [
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
    ]
    assert run_module._missing_keys({"gemini"}, _settings(gemini_api_key="k")) == []


# --- the command --------------------------------------------------------------------------------


def test_a_task_or_all_is_required() -> None:
    with pytest.raises(SystemExit):
        run_module.parse_args([])
    assert run_module.parse_args(["--task", "draft"]).yes is False


async def test_without_yes_nothing_is_called(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(run_module, "get_settings", lambda: _settings(gemini_api_key="k"))

    async def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a model was called in a dry run")

    monkeypatch.setattr(run_module, "run_task", boom)
    assert await run_module.main(run_module.parse_args(["--all"])) == 0
    out = capsys.readouterr().out
    assert "Dry run: nothing was called" in out and "quicklook: 6 case(s)" in out


async def test_a_task_without_its_key_is_skipped_even_with_yes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(run_module, "get_settings", lambda: _settings())

    async def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a model was called without a key")

    monkeypatch.setattr(run_module, "run_task", boom)
    assert await run_module.main(run_module.parse_args(["--task", "draft", "--yes"])) == 0
    assert "MISSING GEMINI_API_KEY" in capsys.readouterr().out


async def test_an_unknown_case_id_is_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    args = run_module.parse_args(["--task", "draft", "--case", "nope"])
    assert await run_module.main(args) == 2


# --- running each case several times (--repeat) --------------------------------------------------


class _Sequence:
    """A fake drafter that answers with the next body in a list on every call."""

    model_name = "fake"

    def __init__(self, bodies: list[str]) -> None:
        self.bodies = bodies
        self.calls = 0

    async def generate(self, *args: Any, **kwargs: Any) -> DraftResult:
        await record_usage(provider="gemini", kind="llm", tokens_in=10, tokens_out=5)
        body = self.bodies[self.calls]
        self.calls += 1
        return DraftResult(subject="Hi", body=body, chosen_option=1)


CLEAN = "Would a short call help?"
INVENTED = "We cut costs by 85% last year."


def _runtime_with(drafter: Any) -> Runtime:
    return Runtime(
        llm=cast(Any, None), qualification=cast(Any, None), draft=cast(Any, drafter), model="fake"
    )


async def test_each_case_runs_the_requested_number_of_times() -> None:
    drafter = _Sequence([CLEAN] * 6)
    cases = _draft_cases("draft-grounding-01", "draft-grounding-02")
    report = await run_task(TASKS["draft"], cases, _runtime_with(drafter), repeat=3)
    assert drafter.calls == 6 and report.usage["calls"] == 6
    assert [(r.runs, r.passes) for r in report.results] == [(3, 3), (3, 3)]
    assert report.repeat == 3 and report.summary()["flaky"] == 0


async def test_a_case_that_passes_some_runs_is_flaky_and_fails_strictly() -> None:
    drafter = _Sequence([CLEAN, INVENTED, CLEAN])
    cases = _draft_cases("draft-grounding-01")
    report = await run_task(TASKS["draft"], cases, _runtime_with(drafter), repeat=3)
    (result,) = report.results
    assert (result.runs, result.passes) == (3, 2)
    assert result.flaky and not result.passed
    assert result.output and "85%" in result.output  # the failing run is the one shown
    assert report.summary()["flaky"] == 1 and report.summary()["passed"] == 0

    data = to_dict(report)
    assert data["repeat"] == 3
    assert (data["results"][0]["runs"], data["results"][0]["passes"]) == (3, 2)
    assert data["summary"]["flaky"] == 1


async def test_a_case_that_fails_every_run_is_broken_not_flaky() -> None:
    drafter = _Sequence([INVENTED] * 3)
    report = await run_task(
        TASKS["draft"], _draft_cases("draft-grounding-01"), _runtime_with(drafter), repeat=3
    )
    (result,) = report.results
    assert (result.passes, result.flaky, result.passed) == (0, False, False)


async def test_a_single_run_report_keeps_its_old_shape() -> None:
    report = await run_task(
        TASKS["draft"], _draft_cases("draft-grounding-01"), _runtime_with(_Sequence([CLEAN]))
    )
    data = to_dict(report)
    assert "repeat" not in data and "runs" not in data["results"][0]
    assert data["summary"]["flaky"] == 0


async def test_the_pause_applies_between_every_call_not_only_between_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pauses: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        pauses.append(seconds)

    monkeypatch.setattr("evals.runner.asyncio", SimpleNamespace(sleep=fake_sleep))
    cases = _draft_cases("draft-grounding-01", "draft-grounding-02")
    await run_task(
        TASKS["draft"], cases, _runtime_with(_Sequence([CLEAN] * 4)), delay_seconds=2.5, repeat=2
    )
    assert pauses == [2.5, 2.5, 2.5]  # four calls, three gaps, none before the first


async def test_a_repeat_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        await run_task(TASKS["draft"], [], _runtime_with(_Sequence([])), repeat=0)


def test_the_repeat_option_is_one_by_default_and_must_be_a_sensible_number() -> None:
    assert run_module.parse_args(["--task", "draft"]).repeat == 1
    assert run_module.parse_args(["--task", "draft", "--repeat", "3"]).repeat == 3
    for bad in ("0", "11", "-1", "many"):
        with pytest.raises(SystemExit):
            run_module.parse_args(["--task", "draft", "--repeat", bad])


async def test_the_plan_shows_how_many_runs_and_a_dry_run_calls_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(run_module, "get_settings", lambda: _settings(gemini_api_key="k"))

    async def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a model was called in a dry run")

    monkeypatch.setattr(run_module, "run_task", boom)
    args = run_module.parse_args(["--task", "draft", "--repeat", "3"])
    assert await run_module.main(args) == 0
    assert "draft: 4 case(s), 12 runs" in capsys.readouterr().out
