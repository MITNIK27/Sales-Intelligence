import pytest

from app.core.config import Settings
from app.modules.ai_recommendation.gemini_client import GeminiClientError
from app.modules.companies.models import Company
from app.modules.qualification import qualification_generator as qualgen_module
from app.modules.qualification.models import QualificationCriterion
from app.modules.qualification.qualification_generator import (
    CriterionVerdict,
    GeminiQualificationGenerator,
    QualificationJudgment,
)


def _settings() -> Settings:
    return Settings(gemini_api_key="key", gemini_model="gemini-3.6-flash")


class _FakeResponse:
    def __init__(self, parsed: object) -> None:
        self.parsed = parsed


class _FakeModels:
    def __init__(self, result: object = None, exc: Exception | None = None) -> None:
        self._result = result
        self._exc = exc
        self.received_model: str | None = None
        self.received_contents: str | None = None

    async def generate_content(self, model: str, contents: str, config: object) -> _FakeResponse:
        self.received_model = model
        self.received_contents = contents
        if self._exc is not None:
            raise self._exc
        return _FakeResponse(self._result)


class _FakeAio:
    def __init__(self, models: _FakeModels) -> None:
        self.models = models


class _FakeClient:
    def __init__(self, models: _FakeModels) -> None:
        self.aio = _FakeAio(models)


def _company(**overrides: object) -> Company:
    defaults: dict[str, object] = {
        "name": "Acme Inc",
        "domain": "acme.com",
        "industry": "SaaS",
        "employee_count_range": "50-200",
        "description": "Acme builds widgets.",
    }
    defaults.update(overrides)
    return Company(**defaults)  # type: ignore[arg-type]


def _criterion(**overrides: object) -> QualificationCriterion:
    defaults: dict[str, object] = {
        "name": "Minimum IT spend",
        "description": "Evidence of significant annual IT spend.",
        "is_disqualifying": True,
        "is_active": True,
    }
    defaults.update(overrides)
    return QualificationCriterion(**defaults)  # type: ignore[arg-type]


_RESULT = QualificationJudgment(
    criteria_results=[
        CriterionVerdict(criterion_id="abc", verdict="met", reasoning="Evidence found."),
    ]
)


async def test_generate_raises_clear_error_without_api_key() -> None:
    generator = GeminiQualificationGenerator(Settings(gemini_api_key=None))
    with pytest.raises(GeminiClientError, match="GEMINI_API_KEY"):
        await generator.generate(_company(), [], [_criterion()])


async def test_generate_assembles_prompt_with_company_and_criteria(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_models = _FakeModels(result=_RESULT)
    monkeypatch.setattr(
        qualgen_module.genai, "Client", lambda api_key: _FakeClient(fake_models)
    )

    generator = GeminiQualificationGenerator(_settings())
    company = _company()
    criterion = _criterion()

    await generator.generate(company, [], [criterion])

    prompt = fake_models.received_contents
    assert prompt is not None
    assert "Acme Inc" in prompt
    assert "Minimum IT spend" in prompt
    assert "Evidence of significant annual IT spend." in prompt
    assert fake_models.received_model == "gemini-3.6-flash"


async def test_generate_prompt_states_explicitly_when_signals_are_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_models = _FakeModels(result=_RESULT)
    monkeypatch.setattr(
        qualgen_module.genai, "Client", lambda api_key: _FakeClient(fake_models)
    )

    generator = GeminiQualificationGenerator(_settings())
    await generator.generate(_company(), [], [_criterion()])

    prompt = fake_models.received_contents
    assert prompt is not None
    assert "No recent buying signals found for this company." in prompt


async def test_generate_raises_on_request_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_models = _FakeModels(exc=RuntimeError("network down"))
    monkeypatch.setattr(
        qualgen_module.genai, "Client", lambda api_key: _FakeClient(fake_models)
    )

    generator = GeminiQualificationGenerator(_settings())
    with pytest.raises(GeminiClientError, match="Gemini request failed"):
        await generator.generate(_company(), [], [_criterion()])


async def test_generate_raises_on_malformed_response(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_models = _FakeModels(result=None)
    monkeypatch.setattr(
        qualgen_module.genai, "Client", lambda api_key: _FakeClient(fake_models)
    )

    generator = GeminiQualificationGenerator(_settings())
    with pytest.raises(GeminiClientError, match="did not return a valid structured response"):
        await generator.generate(_company(), [], [_criterion()])


def test_model_name_reflects_configured_gemini_model() -> None:
    generator = GeminiQualificationGenerator(_settings())
    assert generator.model_name == "gemini-3.6-flash"
