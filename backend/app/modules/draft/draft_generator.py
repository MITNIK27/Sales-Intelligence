"""Draft generation — reuses the shared Gemini client shape and `GeminiClientError` established
in `ai_recommendation/gemini_client.py` (its own docstring already anticipated this: "Phase 3's
pitch-recommendation layer will reuse it later"). Unlike Recommendation (internal sales-prep
notes), a Draft's `body` is customer-facing message copy — the prompt is explicit about that, and
about never inventing a proof point/case study it wasn't given."""

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
from app.modules.ai_recommendation.models import Recommendation
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.draft.models import DRAFT_TYPE_FIRST_TOUCH
from app.modules.draft.prompts import (
    FIRST_TOUCH_PROMPT_TEMPLATE,
    FOLLOW_UP_PROMPT_TEMPLATE,
    framing_instruction,
)
from app.modules.products.models import Product


class DraftResult(BaseModel):
    subject: str | None
    body: str


def _format_grounding(recommendation: Recommendation | None) -> tuple[str, str]:
    """Returns (grounding_section, grounding_instruction) — split so the instruction can be
    inlined into the structure bullet while the actual grounding content gets its own block."""
    if recommendation is None:
        return (
            "No pre-researched recommendation is available for this company/product pair.",
            "There is no pre-researched proof point available — do not invent a fabricated case "
            "study or project; keep this line general and credible instead.",
        )
    points = "\n".join(f"- {p}" for p in recommendation.talking_points) or "(none)"
    section = (
        "Pre-researched grounding for this pitch (use this, do not invent a different one):\n"
        f"- Why this company is a fit: {recommendation.why_this_company}\n"
        f"- Talking points:\n{points}"
    )
    return section, "Use the pre-researched proof point given below."


class DraftGenerator(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Persisted on `Draft.model_used` so history shows which model generated each draft."""
        ...

    @abstractmethod
    async def generate(
        self,
        company: Company,
        contact: Contact,
        product: Product,
        recommendation: Recommendation | None,
        framing_style: str,
        draft_type: str,
    ) -> DraftResult: ...


class GeminiDraftGenerator(DraftGenerator):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def model_name(self) -> str:
        return self._settings.gemini_model

    async def generate(
        self,
        company: Company,
        contact: Contact,
        product: Product,
        recommendation: Recommendation | None,
        framing_style: str,
        draft_type: str,
    ) -> DraftResult:
        if not self._settings.gemini_api_key:
            raise GeminiClientError("GEMINI_API_KEY is not configured")

        grounding_section, grounding_instruction = _format_grounding(recommendation)
        template = (
            FIRST_TOUCH_PROMPT_TEMPLATE
            if draft_type == DRAFT_TYPE_FIRST_TOUCH
            else FOLLOW_UP_PROMPT_TEMPLATE
        )
        prompt = template.format(
            contact_name=contact.full_name or "Unknown name",
            contact_role=contact.role_title or "unknown role",
            company_name=company.name,
            company_industry=company.industry or "unknown",
            company_description=company.description or "No description available.",
            product_name=product.name,
            product_description=product.description or "No description available.",
            grounding_section=grounding_section,
            grounding_instruction=grounding_instruction,
            framing_instruction=framing_instruction(framing_style),
        )

        client = genai.Client(api_key=self._settings.gemini_api_key)
        try:
            response = await generate_content_with_retry(
                client,
                model=self._settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=DraftResult,
                ),
            )
        except genai_errors.APIError as exc:
            raise GeminiClientError(format_gemini_error(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a clear failure
            raise GeminiClientError(f"Gemini request failed: {exc}") from exc

        parsed = response.parsed
        if not isinstance(parsed, DraftResult):
            raise GeminiClientError("Gemini did not return a valid structured response")
        return parsed
