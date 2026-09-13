import pytest

from app.core.config import Settings
from app.modules.ai_recommendation import recommendation_generator as recgen_module
from app.modules.ai_recommendation.gemini_client import GeminiClientError
from app.modules.ai_recommendation.recommendation_generator import (
    GeminiRecommendationGenerator,
    RecommendationResult,
)
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.enrichment.models import EnrichmentRecord
from app.modules.products.models import Product


def _settings() -> Settings:
    return Settings(gemini_api_key="key", gemini_model="gemini-3.6-flash")


class _FakeResponse:
    def __init__(self, parsed: object) -> None:
        self.parsed = parsed


class _FakeModels:
    def __init__(self, result: object = None, exc: Exception | None = None) -> None:
        self._result = result
        self._exc = exc
        self.received_contents: str | None = None

    async def generate_content(self, model: str, contents: str, config: object) -> _FakeResponse:
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


def _product(**overrides: object) -> Product:
    defaults: dict[str, object] = {"name": "Widget Pro", "description": "The best widget."}
    defaults.update(overrides)
    return Product(**defaults)  # type: ignore[arg-type]


_RESULT = RecommendationResult(
    pitch_summary="Pitch Widget Pro to Acme.",
    why_this_company="Acme is a growing SaaS company that needs widgets.",
    talking_points=["Point one", "Point two", "Point three"],
)


async def test_generate_raises_clear_error_without_api_key() -> None:
    generator = GeminiRecommendationGenerator(Settings(gemini_api_key=None))
    with pytest.raises(GeminiClientError, match="GEMINI_API_KEY"):
        await generator.generate(_company(), [], [], _product())


async def test_generate_assembles_prompt_with_firmographics_contacts_signals_and_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_models = _FakeModels(result=_RESULT)
    monkeypatch.setattr(
        recgen_module.genai, "Client", lambda api_key: _FakeClient(fake_models)
    )

    generator = GeminiRecommendationGenerator(_settings())
    company = _company()
    contact = Contact(full_name="Jane Doe", role_title="VP Engineering")
    signal = EnrichmentRecord(
        raw_payload={"signal_type": "job_posting", "text": "Hiring a Sales Ops Manager"},
    )
    product = _product()

    result = await generator.generate(company, [contact], [signal], product)

    assert result == _RESULT
    prompt = fake_models.received_contents
    assert prompt is not None
    assert "Acme Inc" in prompt
    assert "SaaS" in prompt
    assert "Jane Doe" in prompt
    assert "VP Engineering" in prompt
    assert "Hiring a Sales Ops Manager" in prompt
    assert "Widget Pro" in prompt
    assert "The best widget." in prompt


async def test_generate_prompt_states_explicitly_when_contacts_and_signals_are_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_models = _FakeModels(result=_RESULT)
    monkeypatch.setattr(
        recgen_module.genai, "Client", lambda api_key: _FakeClient(fake_models)
    )

    generator = GeminiRecommendationGenerator(_settings())
    await generator.generate(_company(), [], [], _product())

    prompt = fake_models.received_contents
    assert prompt is not None
    assert "No known contacts at this company." in prompt
    assert "No recent buying signals found for this company." in prompt


async def test_generate_raises_on_request_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_models = _FakeModels(exc=RuntimeError("network down"))
    monkeypatch.setattr(
        recgen_module.genai, "Client", lambda api_key: _FakeClient(fake_models)
    )

    generator = GeminiRecommendationGenerator(_settings())
    with pytest.raises(GeminiClientError, match="Gemini request failed"):
        await generator.generate(_company(), [], [], _product())


async def test_generate_raises_on_malformed_response(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_models = _FakeModels(result=None)
    monkeypatch.setattr(
        recgen_module.genai, "Client", lambda api_key: _FakeClient(fake_models)
    )

    generator = GeminiRecommendationGenerator(_settings())
    with pytest.raises(GeminiClientError, match="did not return a valid structured response"):
        await generator.generate(_company(), [], [], _product())


def test_model_name_reflects_configured_gemini_model() -> None:
    generator = GeminiRecommendationGenerator(_settings())
    assert generator.model_name == "gemini-3.6-flash"
