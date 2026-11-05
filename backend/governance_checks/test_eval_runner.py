"""The eval runner, with fake models. Nothing here calls a real model: the runtime is fake, and the
command-line tests use settings with no keys, so no call can be made."""

from typing import Any, cast

import pytest

from app.core.config import Settings
from app.modules.draft.draft_generator import DraftResult
from app.modules.usage import recorder
from app.modules.usage.recorder import record_usage
from evals import run as run_module
from evals.cases import Case, load_cases
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
