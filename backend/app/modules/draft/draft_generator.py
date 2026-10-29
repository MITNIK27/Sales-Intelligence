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
from app.modules.draft.evidence import DraftEvidence, format_evidence
from app.modules.draft.models import DRAFT_TYPE_FIRST_TOUCH
from app.modules.draft.prompts import (
    FIRST_TOUCH_PROMPT_TEMPLATE,
    FOLLOW_UP_PROMPT_TEMPLATE,
    SALES_LENS_INSTRUCTION,
    STYLE_REFERENCE_EXAMPLES,
    cta_instruction,
    format_previous_emails,
    framing_instruction,
    offering_guidance,
)
from app.modules.products.models import Product


class DraftResult(BaseModel):
    subject: str | None
    body: str
    # 1-based index into the `products` list given to the generator — which candidate product the
    # email ended up being about. A deterministic mapping back to a real `product_id` is done by
    # the caller (`draft/service.py::generate_draft`); the LLM only ever picks an option number,
    # never echoes back a UUID itself.
    chosen_option: int


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


def _format_product_options(
    products: list[Product], recommendations: list[Recommendation | None]
) -> str:
    """One numbered block per candidate product, each with its own grounding — lets the model pick
    exactly one option rather than being told which single product to pitch."""
    blocks = []
    for i, (product, recommendation) in enumerate(zip(products, recommendations), start=1):
        grounding_section, grounding_instruction = _format_grounding(recommendation)
        blocks.append(
            f"Option {i}: {product.name}\n"
            f"- {offering_guidance(product.kind)}\n"
            f"- Description: {product.description or 'No description available.'}\n"
            f"- {grounding_instruction}\n"
            f"{grounding_section}"
        )
    return "\n\n".join(blocks)


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
        products: list[Product],
        recommendations: list[Recommendation | None],
        framing_style: str,
        draft_type: str,
        evidence: DraftEvidence | None = None,
        previous_emails: list[tuple[str | None, str]] | None = None,
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
        products: list[Product],
        recommendations: list[Recommendation | None],
        framing_style: str,
        draft_type: str,
        evidence: DraftEvidence | None = None,
        previous_emails: list[tuple[str | None, str]] | None = None,
    ) -> DraftResult:
        if not self._settings.gemini_api_key:
            raise GeminiClientError("GEMINI_API_KEY is not configured")

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
            product_options_section=_format_product_options(products, recommendations),
            evidence_section=format_evidence(evidence),
            framing_instruction=framing_instruction(framing_style),
            sales_lens=SALES_LENS_INSTRUCTION,
            cta_instruction=cta_instruction(draft_type),
            previous_email_section=format_previous_emails(previous_emails),
            style_reference=STYLE_REFERENCE_EXAMPLES,
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
        if not 1 <= parsed.chosen_option <= len(products):
            raise GeminiClientError(
                f"Gemini returned chosen_option={parsed.chosen_option}, outside the given "
                f"1-{len(products)} range of product options"
            )
        return parsed
