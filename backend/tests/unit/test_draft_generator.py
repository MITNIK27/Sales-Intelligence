import pytest

from app.core.config import Settings
from app.modules.ai_recommendation.gemini_client import GeminiClientError
from app.modules.ai_recommendation.models import Recommendation
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.draft import draft_generator as draftgen_module
from app.modules.draft.draft_generator import DraftResult, GeminiDraftGenerator
from app.modules.draft.models import DRAFT_TYPE_FIRST_TOUCH, DRAFT_TYPE_FOLLOW_UP
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
        "industry": "SaaS",
        "description": "Acme builds widgets.",
    }
    defaults.update(overrides)
    return Company(**defaults)  # type: ignore[arg-type]


def _contact(**overrides: object) -> Contact:
    defaults: dict[str, object] = {"full_name": "Jane Doe", "role_title": "VP Engineering"}
    defaults.update(overrides)
    return Contact(**defaults)  # type: ignore[arg-type]


def _product(**overrides: object) -> Product:
    defaults: dict[str, object] = {"name": "Widget Pro", "description": "The best widget."}
    defaults.update(overrides)
    return Product(**defaults)  # type: ignore[arg-type]


_RESULT = DraftResult(subject="Quick idea for Acme", body="Hi Jane, ...")


async def test_generate_raises_clear_error_without_api_key() -> None:
    generator = GeminiDraftGenerator(Settings(gemini_api_key=None))
    with pytest.raises(GeminiClientError, match="GEMINI_API_KEY"):
        await generator.generate(
            _company(), _contact(), _product(), None, "business", DRAFT_TYPE_FIRST_TOUCH
        )


async def test_generate_uses_first_touch_template(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_models = _FakeModels(result=_RESULT)
    monkeypatch.setattr(draftgen_module.genai, "Client", lambda api_key: _FakeClient(fake_models))

    generator = GeminiDraftGenerator(_settings())
    result = await generator.generate(
        _company(), _contact(), _product(), None, "business", DRAFT_TYPE_FIRST_TOUCH
    )

    assert result == _RESULT
    prompt = fake_models.received_contents
    assert prompt is not None
    assert "max 7-8 lines" in prompt
    assert "Acme Inc" in prompt
    assert "Jane Doe" in prompt
    assert "Widget Pro" in prompt


async def test_generate_uses_follow_up_template(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_models = _FakeModels(result=_RESULT)
    monkeypatch.setattr(draftgen_module.genai, "Client", lambda api_key: _FakeClient(fake_models))

    generator = GeminiDraftGenerator(_settings())
    await generator.generate(
        _company(), _contact(), _product(), None, "business", DRAFT_TYPE_FOLLOW_UP
    )

    prompt = fake_models.received_contents
    assert prompt is not None
    assert "NOT" in prompt and "just following up" in prompt


async def test_generate_includes_business_or_technical_framing_instruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_models = _FakeModels(result=_RESULT)
    monkeypatch.setattr(draftgen_module.genai, "Client", lambda api_key: _FakeClient(fake_models))

    generator = GeminiDraftGenerator(_settings())
    await generator.generate(
        _company(), _contact(), _product(), None, "technical", DRAFT_TYPE_FIRST_TOUCH
    )
    assert fake_models.received_contents is not None
    assert "technical/KPI language" in fake_models.received_contents

    await generator.generate(
        _company(), _contact(), _product(), None, "business", DRAFT_TYPE_FIRST_TOUCH
    )
    assert fake_models.received_contents is not None
    assert "outcome/cost-savings language" in fake_models.received_contents


async def test_generate_without_recommendation_instructs_no_fabrication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_models = _FakeModels(result=_RESULT)
    monkeypatch.setattr(draftgen_module.genai, "Client", lambda api_key: _FakeClient(fake_models))

    generator = GeminiDraftGenerator(_settings())
    await generator.generate(
        _company(), _contact(), _product(), None, "business", DRAFT_TYPE_FIRST_TOUCH
    )

    prompt = fake_models.received_contents
    assert prompt is not None
    assert "do not invent a fabricated case study" in prompt


async def test_generate_with_recommendation_includes_its_grounding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_models = _FakeModels(result=_RESULT)
    monkeypatch.setattr(draftgen_module.genai, "Client", lambda api_key: _FakeClient(fake_models))

    recommendation = Recommendation(
        why_this_company="Acme just raised a Series B and is scaling engineering fast.",
        talking_points=["Point one", "Point two"],
        model_used="mock",
    )
    generator = GeminiDraftGenerator(_settings())
    await generator.generate(
        _company(), _contact(), _product(), recommendation, "business", DRAFT_TYPE_FIRST_TOUCH
    )

    prompt = fake_models.received_contents
    assert prompt is not None
    assert "Series B" in prompt
    assert "Point one" in prompt


async def test_generate_raises_on_request_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_models = _FakeModels(exc=RuntimeError("network down"))
    monkeypatch.setattr(draftgen_module.genai, "Client", lambda api_key: _FakeClient(fake_models))

    generator = GeminiDraftGenerator(_settings())
    with pytest.raises(GeminiClientError, match="Gemini request failed"):
        await generator.generate(
            _company(), _contact(), _product(), None, "business", DRAFT_TYPE_FIRST_TOUCH
        )


async def test_generate_raises_on_malformed_response(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_models = _FakeModels(result=None)
    monkeypatch.setattr(draftgen_module.genai, "Client", lambda api_key: _FakeClient(fake_models))

    generator = GeminiDraftGenerator(_settings())
    with pytest.raises(GeminiClientError, match="did not return a valid structured response"):
        await generator.generate(
            _company(), _contact(), _product(), None, "business", DRAFT_TYPE_FIRST_TOUCH
        )


def test_model_name_reflects_configured_gemini_model() -> None:
    generator = GeminiDraftGenerator(_settings())
    assert generator.model_name == "gemini-3.6-flash"
