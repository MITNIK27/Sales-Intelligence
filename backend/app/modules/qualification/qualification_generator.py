"""Qualification judgment generation — the third Gemini consumer (per ADR 0002), reusing the
same client shape and `GeminiClientError` established in `gemini_client.py`. Mirrors
`ai_recommendation/recommendation_generator.py` field-for-field: this is a single LLM reasoning
call over already-loaded data, the same shape as recommendation generation, not the heavier
multi-stage `discovery_agent` pattern.

The LLM outputs ONLY per-criterion verdicts — never an overall qualified/not_qualified call. See
`prompts.py` and `service.py` for why."""

from abc import ABC, abstractmethod
from typing import Literal

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

from app.core.config import Settings
from app.modules.ai_recommendation.gemini_client import (
    GeminiClientError,
    format_gemini_error,
    generate_content_with_retry,
)
from app.modules.companies.models import Company
from app.modules.enrichment.models import EnrichmentRecord
from app.modules.qualification.models import QualificationCriterion
from app.modules.qualification.prompts import build_qualification_prompt

Verdict = Literal["met", "not_met", "could_not_determine"]


class CriterionVerdict(BaseModel):
    criterion_id: str
    verdict: Verdict
    reasoning: str


class QualificationJudgment(BaseModel):
    criteria_results: list[CriterionVerdict]


class QualificationGenerator(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    async def generate(
        self,
        company: Company,
        signals: list[EnrichmentRecord],
        criteria: list[QualificationCriterion],
    ) -> QualificationJudgment: ...


class GeminiQualificationGenerator(QualificationGenerator):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def model_name(self) -> str:
        return self._settings.gemini_model

    async def generate(
        self,
        company: Company,
        signals: list[EnrichmentRecord],
        criteria: list[QualificationCriterion],
    ) -> QualificationJudgment:
        if not self._settings.gemini_api_key:
            raise GeminiClientError("GEMINI_API_KEY is not configured")

        prompt = build_qualification_prompt(company, signals, criteria)
        client = genai.Client(api_key=self._settings.gemini_api_key)
        try:
            response = await generate_content_with_retry(
                client,
                model=self._settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=QualificationJudgment,
                ),
            )
        except genai_errors.APIError as exc:
            raise GeminiClientError(format_gemini_error(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a clear failure
            raise GeminiClientError(f"Gemini request failed: {exc}") from exc

        parsed = response.parsed
        if not isinstance(parsed, QualificationJudgment):
            raise GeminiClientError("Gemini did not return a valid structured response")
        return parsed
