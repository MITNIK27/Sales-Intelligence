"""LLM extraction stage, behind a model-agnostic interface. Only a free-tier Gemini
implementation exists today (this is a free-tier application — no paid model/API key), but the
interface is deliberately generic so a different backend can be added later without touching
`prompts.py`, `agent.py`, or anything upstream of this module. The prompt itself
(`prompts.build_extraction_prompt`) is written provider-neutrally for exactly that reason.

Imported at module scope (not lazily inside methods) so tests can monkeypatch
`extractor_module.genai.Client` the same way `recommendation_generator.py` already does."""

from abc import ABC, abstractmethod

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

from app.core.config import Settings
from app.modules.ai_recommendation.gemini_client import generate_content_with_retry
from app.modules.discovery_agent.prompts import build_extraction_prompt
from app.modules.discovery_agent.schemas import ExtractedCompany, MarketCriteria, RawSearchResult


class ExtractionModelError(RuntimeError):
    """Raised when the underlying model can't be called or doesn't return a valid structured
    response. No fallback to raw search results exists here by design — that would reintroduce
    the noise this module exists to eliminate. `agent.py` wraps this into `DiscoveryAgentError`
    for callers outside this module."""


class _ExtractedCompanyItem(BaseModel):
    name: str
    source_snippet: str
    grounded_in_source: bool
    matches_criteria: bool
    reasoning: str


class _ExtractionResponse(BaseModel):
    companies: list[_ExtractedCompanyItem]


def _to_extracted(items: list[_ExtractedCompanyItem]) -> list[ExtractedCompany]:
    return [
        ExtractedCompany(
            name=item.name,
            source_snippet=item.source_snippet,
            grounded_in_source=item.grounded_in_source,
            matches_criteria=item.matches_criteria,
            reasoning=item.reasoning,
        )
        for item in items
    ]


class CompanyExtractionModel(ABC):
    @abstractmethod
    async def extract(
        self, criteria: MarketCriteria, search_results: list[RawSearchResult]
    ) -> list[ExtractedCompany]: ...


class GeminiCompanyExtractionModel(CompanyExtractionModel):
    def __init__(self, settings: Settings, model: str | None = None) -> None:
        self._settings = settings
        # Allows this one failure-sensitive stage to use a different (still free-tier) Gemini
        # model than the rest of the app — e.g. a "pro" variant instead of "flash" — without
        # changing every other Gemini call. Falls back to the app-wide default.
        self._model = model or settings.gemini_model

    async def extract(
        self, criteria: MarketCriteria, search_results: list[RawSearchResult]
    ) -> list[ExtractedCompany]:
        if not self._settings.gemini_api_key:
            raise ExtractionModelError("GEMINI_API_KEY is not configured")

        prompt = build_extraction_prompt(criteria, search_results)
        client = genai.Client(api_key=self._settings.gemini_api_key)
        try:
            response = await generate_content_with_retry(
                client,
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_ExtractionResponse,
                ),
            )
        except genai_errors.APIError as exc:
            raise ExtractionModelError(f"Gemini extraction failed: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a clear failure
            raise ExtractionModelError(f"Gemini extraction failed: {exc}") from exc

        parsed = response.parsed
        if not isinstance(parsed, _ExtractionResponse):
            raise ExtractionModelError("Gemini did not return a valid structured response")
        return _to_extracted(parsed.companies)
