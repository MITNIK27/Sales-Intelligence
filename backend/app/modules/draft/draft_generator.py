"""Draft generation — reuses the shared Gemini client shape and `GeminiClientError` established
in `ai_recommendation/gemini_client.py` (its own docstring already anticipated this: "Phase 3's
pitch-recommendation layer will reuse it later"). Unlike Recommendation (internal sales-prep
notes), a Draft's `body` is customer-facing message copy — the prompt is explicit about that, and
about never inventing a proof point/case study it wasn't given."""

from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.core.config import Settings
from app.modules.ai_recommendation.gemini_client import (
    MAX_OUTPUT_TOKENS,
    GeminiClientError,
    generate_structured,
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
from app.modules.draft.refine import RefineResult, build_refine_prompt
from app.modules.llm.untrusted import with_untrusted_notice, wrap_untrusted
from app.modules.products.models import Product


def first_name(full_name: str | None) -> str:
    """The only part of a person's name that is sent to the model: a greeting needs a first name,
    and the full name is personal data that does not need to leave this system."""
    parts = (full_name or "").split()
    return parts[0] if parts else "Unknown name"


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
    pairs = zip(products, recommendations, strict=True)
    for i, (product, recommendation) in enumerate(pairs, start=1):
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

    async def refine(
        self,
        company: Company,
        contact: Contact,
        product: Product,
        recommendation: Recommendation | None,
        framing_style: str,
        subject: str | None,
        body: str,
        instruction: str,
    ) -> RefineResult:
        """Rewrite `body` as the rep asked. A generator that cannot says so, not silently echoes."""
        raise NotImplementedError(f"{type(self).__name__} cannot rewrite drafts")


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
            contact_name=first_name(contact.full_name),
            contact_role=contact.role_title or "unknown role",
            company_name=company.name,
            company_industry=company.industry or "unknown",
            company_description=wrap_untrusted(
                company.description or "No description available.", "company description"
            ),
            product_options_section=_format_product_options(products, recommendations),
            evidence_section=wrap_untrusted(format_evidence(evidence), "evidence"),
            framing_instruction=framing_instruction(framing_style),
            sales_lens=SALES_LENS_INSTRUCTION,
            cta_instruction=cta_instruction(draft_type),
            previous_email_section=format_previous_emails(previous_emails),
            style_reference=STYLE_REFERENCE_EXAMPLES,
        )
        prompt = with_untrusted_notice(prompt)

        parsed = await generate_structured(
            api_key=self._settings.gemini_api_key,
            model=self._settings.gemini_model,
            prompt=prompt,
            schema=DraftResult,
            temperature=None,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        if not 1 <= parsed.chosen_option <= len(products):
            raise GeminiClientError(
                f"Gemini returned chosen_option={parsed.chosen_option}, outside the given "
                f"1-{len(products)} range of product options"
            )
        return parsed

    async def refine(
        self,
        company: Company,
        contact: Contact,
        product: Product,
        recommendation: Recommendation | None,
        framing_style: str,
        subject: str | None,
        body: str,
        instruction: str,
    ) -> RefineResult:
        if not self._settings.gemini_api_key:
            raise GeminiClientError("GEMINI_API_KEY is not configured")
        grounding_section, _ = _format_grounding(recommendation)
        prompt = build_refine_prompt(
            company=company,
            contact_first_name=first_name(contact.full_name),
            contact_role=contact.role_title,
            product=product,
            grounding_section=grounding_section,
            framing_style=framing_style,
            current_subject=subject,
            current_body=body,
            instruction=instruction,
        )
        parsed = await generate_structured(
            api_key=self._settings.gemini_api_key,
            model=self._settings.gemini_model,
            prompt=prompt,
            schema=RefineResult,
            temperature=None,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        if not parsed.body.strip():
            raise GeminiClientError("the rewrite came back empty")
        return parsed
