"""Role-relevance classification generation — reuses the same Gemini client shape and
`GeminiClientError` established in `gemini_client.py`. Mirrors `qualification_generator.py`
field-for-field: a single LLM reasoning call over already-loaded data.

The LLM outputs ONLY per-contact category matches — never a priority. See `prompts.py` and
`service.py` for why."""

from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.core.config import Settings
from app.modules.ai_recommendation.gemini_client import (
    MAX_OUTPUT_TOKENS,
    GeminiClientError,
    generate_structured,
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
        return await generate_structured(
            api_key=self._settings.gemini_api_key,
            model=self._settings.gemini_model,
            prompt=prompt,
            schema=RoleRelevanceJudgment,
            temperature=None,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
