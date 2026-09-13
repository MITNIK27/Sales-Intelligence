"""Role-relevance classification generation — reuses the same Gemini client shape and
`GeminiClientError` established in `gemini_client.py`. Mirrors `qualification_generator.py`
field-for-field: a single LLM reasoning call over already-loaded data.

The LLM outputs ONLY per-contact category matches — never a priority. See `prompts.py` and
`service.py` for why."""

from abc import ABC, abstractmethod

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
from app.modules.contacts.models import Contact
from app.modules.role_relevance.models import RoleCategory
from app.modules.role_relevance.prompts import build_role_relevance_prompt


class ContactRoleVerdict(BaseModel):
    contact_id: str
    matched_category_id: str | None
    reasoning: str


class RoleRelevanceJudgment(BaseModel):
    contact_results: list[ContactRoleVerdict]


class RoleRelevanceGenerator(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    async def generate(
        self,
        company: Company,
        contacts: list[Contact],
        categories: list[RoleCategory],
    ) -> RoleRelevanceJudgment: ...


class GeminiRoleRelevanceGenerator(RoleRelevanceGenerator):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def model_name(self) -> str:
        return self._settings.gemini_model

    async def generate(
        self,
        company: Company,
        contacts: list[Contact],
        categories: list[RoleCategory],
    ) -> RoleRelevanceJudgment:
        if not self._settings.gemini_api_key:
            raise GeminiClientError("GEMINI_API_KEY is not configured")

        prompt = build_role_relevance_prompt(company, contacts, categories)
        client = genai.Client(api_key=self._settings.gemini_api_key)
        try:
            response = await generate_content_with_retry(
                client,
                model=self._settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=RoleRelevanceJudgment,
                ),
            )
        except genai_errors.APIError as exc:
            raise GeminiClientError(format_gemini_error(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a clear failure
            raise GeminiClientError(f"Gemini request failed: {exc}") from exc

        parsed = response.parsed
        if not isinstance(parsed, RoleRelevanceJudgment):
            raise GeminiClientError("Gemini did not return a valid structured response")
        return parsed
