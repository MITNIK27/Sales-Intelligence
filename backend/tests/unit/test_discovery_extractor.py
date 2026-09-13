import pytest

from app.core.config import Settings
from app.modules.discovery_agent import extractor as extractor_module
from app.modules.discovery_agent.extractor import (
    ExtractionModelError,
    GeminiCompanyExtractionModel,
)
from app.modules.discovery_agent.schemas import MarketCriteria, RawSearchResult


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


_RAW_RESULTS = [
    RawSearchResult(
        title="Best courier companies in Europe?",
        link="https://reddit.com/r/logistics/thread1",
        snippet="I think Acme Parcel and Globex Post are both solid options.",
    ),
    RawSearchResult(
        title="Acme Parcel - official site",
        link="https://acmeparcel.com",
        snippet="Acme Parcel is a leading European parcel delivery company.",
    ),
]


async def test_extract_raises_clear_error_without_api_key() -> None:
    model = GeminiCompanyExtractionModel(Settings(gemini_api_key=None))
    with pytest.raises(ExtractionModelError, match="GEMINI_API_KEY"):
        await model.extract(MarketCriteria(industry_keywords=["logistics"]), [])


async def test_extract_builds_prompt_from_criteria_and_search_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_models = _FakeModels(result=extractor_module._ExtractionResponse(companies=[]))
    monkeypatch.setattr(
        extractor_module.genai, "Client", lambda api_key: _FakeClient(fake_models)
    )

    model = GeminiCompanyExtractionModel(_settings())
    criteria = MarketCriteria(
        industry_keywords=["postal", "parcel"], location="Europe", employee_size_range="1000-1500"
    )
    await model.extract(criteria, _RAW_RESULTS)

    prompt = fake_models.received_contents
    assert prompt is not None
    assert "postal, parcel" in prompt
    assert "Europe" in prompt
    assert "1000-1500" in prompt
    assert "Acme Parcel is a leading European parcel delivery company." in prompt
    assert fake_models.received_model == "gemini-3.6-flash"


async def test_extract_uses_dedicated_model_override_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_models = _FakeModels(result=extractor_module._ExtractionResponse(companies=[]))
    monkeypatch.setattr(
        extractor_module.genai, "Client", lambda api_key: _FakeClient(fake_models)
    )

    model = GeminiCompanyExtractionModel(_settings(), model="gemini-3.6-pro")
    await model.extract(MarketCriteria(industry_keywords=["SaaS"]), [])

    assert fake_models.received_model == "gemini-3.6-pro"


async def test_extract_parses_grounded_and_matching_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = extractor_module._ExtractionResponse(
        companies=[
            extractor_module._ExtractedCompanyItem(
                name="Acme Parcel",
                source_snippet="Acme Parcel is a leading European parcel delivery company.",
                grounded_in_source=True,
                matches_criteria=True,
                reasoning="Named in the text and matches the postal/parcel, Europe criteria.",
            ),
            extractor_module._ExtractedCompanyItem(
                name="Reddit",
                source_snippet="r/logistics",
                grounded_in_source=False,
                matches_criteria=False,
                reasoning="Reddit is a forum, not a company.",
            ),
        ]
    )
    fake_models = _FakeModels(result=response)
    monkeypatch.setattr(
        extractor_module.genai, "Client", lambda api_key: _FakeClient(fake_models)
    )

    model = GeminiCompanyExtractionModel(_settings())
    extracted = await model.extract(
        MarketCriteria(industry_keywords=["postal", "parcel"], location="Europe"), _RAW_RESULTS
    )

    assert len(extracted) == 2
    accepted = [e for e in extracted if e.accepted]
    assert [e.name for e in accepted] == ["Acme Parcel"]
    rejected = [e for e in extracted if not e.accepted]
    assert rejected[0].name == "Reddit"
    assert rejected[0].grounded_in_source is False


async def test_extract_raises_on_request_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_models = _FakeModels(exc=RuntimeError("network down"))
    monkeypatch.setattr(
        extractor_module.genai, "Client", lambda api_key: _FakeClient(fake_models)
    )

    model = GeminiCompanyExtractionModel(_settings())
    with pytest.raises(ExtractionModelError, match="Gemini extraction failed"):
        await model.extract(MarketCriteria(industry_keywords=["SaaS"]), [])


async def test_extract_raises_on_malformed_response(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_models = _FakeModels(result=None)
    monkeypatch.setattr(
        extractor_module.genai, "Client", lambda api_key: _FakeClient(fake_models)
    )

    model = GeminiCompanyExtractionModel(_settings())
    with pytest.raises(ExtractionModelError, match="did not return a valid structured response"):
        await model.extract(MarketCriteria(industry_keywords=["SaaS"]), [])
