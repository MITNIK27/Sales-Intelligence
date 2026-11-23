"""Recommendation generation — the second Gemini consumer (per ADR 0002), reusing the same
client shape and `GeminiClientError` established in `gemini_client.py` (Market Discovery).
Unlike Market Discovery's per-field confidence extraction, a recommendation is inherently
generative prose, not a fact extracted from text — there's no `could_not_determine` concept
here. The prompt is explicit when an input (signals/contacts) is empty rather than pretending
data exists, so Gemini doesn't fabricate specifics it wasn't given."""

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
from app.modules.enrichment.models import EnrichmentRecord
from app.modules.llm.untrusted import with_untrusted_notice, wrap_untrusted
from app.modules.products.models import Product

# Recent signals are informative but unbounded EnrichmentRecord history isn't useful in a
# prompt — cap it the same way Market Discovery caps its candidate search.
MAX_SIGNALS_IN_PROMPT = 10


class RecommendationResult(BaseModel):
    pitch_summary: str
    why_this_company: str
    talking_points: list[str]


def _format_contacts(contacts: list[Contact]) -> str:
    if not contacts:
        return "No known contacts at this company."
    # Roles only: names are personal data and the prep notes do not need them.
    lines = [f"- {c.role_title or 'unknown role'}" for c in contacts]
    return "\n".join(lines)


def _format_signals(signals: list[EnrichmentRecord]) -> str:
    if not signals:
        return "No recent buying signals found for this company."
    lines = []
    for record in signals[:MAX_SIGNALS_IN_PROMPT]:
        signal_type = record.raw_payload.get("signal_type", "signal")
        text = record.raw_payload.get("text", "")
        lines.append(f"- [{signal_type}] {text}")
    return "\n".join(lines)


# Bump when the prompt text changes; stored on every row it produces (docs/ai-governance.md, G9).
PROMPT_VERSION = "v3"  # v3: passages from our own documents about the product, when there are any

_PROMPT_TEMPLATE = """You are helping a salesperson prepare to pitch a product to a company. \
Based on the company's firmographics, its known contacts, its recent buying signals, and the \
product being sold, write sales-prep intelligence for the rep to read before reaching out. \
This is internal prep material, not customer-facing message copy.

Company:
- Name: {company_name}
- Domain: {company_domain}
- Industry: {company_industry}
- Employee count range: {company_employee_count_range}
- Description: {company_description}

Known contacts at this company:
{contacts}

Recent buying signals:
{signals}

Product being pitched:
- Name: {product_name}
- Description: {product_description}
{opportunity_section}{knowledge_section}
Write:
- pitch_summary: a concise summary of what to pitch and why it's relevant right now.
- why_this_company: a paragraph explaining why this company specifically is a good fit, \
grounded in the information above. If contacts or signals are empty, do not invent any — say \
so plainly and reason from firmographics alone.
- talking_points: 3-5 specific talking points a rep can use in conversation.
"""

_KNOWLEDGE_SECTION = """
What our own documents say about this product (internal material: use it for what the product \
does and what it has delivered, never as a fact about the company; when you use a passage, put its \
label in the sentence, for example [K2]):
{block}
"""


class RecommendationGenerator(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Identifies which model produced a result — persisted on `Recommendation.model_used`
        so history shows which model generated each row."""
        ...

    @abstractmethod
    async def generate(
        self,
        company: Company,
        contacts: list[Contact],
        signals: list[EnrichmentRecord],
        product: Product,
        opportunity_context: str | None = None,
        knowledge: str | None = None,
    ) -> RecommendationResult:
        """`knowledge`, when given, is fenced passages from our own documents about the product.
        `opportunity_context`, when given, names the business area being discussed and what has
        been verified about the company in it, so the pitch is about that area."""
        ...


class GeminiRecommendationGenerator(RecommendationGenerator):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def model_name(self) -> str:
        return self._settings.gemini_model

    async def generate(
        self,
        company: Company,
        contacts: list[Contact],
        signals: list[EnrichmentRecord],
        product: Product,
        opportunity_context: str | None = None,
        knowledge: str | None = None,
    ) -> RecommendationResult:
        if not self._settings.gemini_api_key:
            raise GeminiClientError("GEMINI_API_KEY is not configured")

        prompt = _PROMPT_TEMPLATE.format(
            company_name=company.name,
            company_domain=company.domain or "unknown",
            company_industry=company.industry or "unknown",
            company_employee_count_range=company.employee_count_range or "unknown",
            company_description=wrap_untrusted(
                company.description or "No description available.", "company description"
            ),
            contacts=wrap_untrusted(_format_contacts(contacts), "contact titles"),
            signals=wrap_untrusted(_format_signals(signals), "signals"),
            product_name=product.name,
            product_description=product.description or "No description available.",
            opportunity_section=(f"\n{opportunity_context}\n" if opportunity_context else ""),
            knowledge_section=_KNOWLEDGE_SECTION.format(block=knowledge) if knowledge else "",
        )
        prompt = with_untrusted_notice(prompt)

        return await generate_structured(
            api_key=self._settings.gemini_api_key,
            model=self._settings.gemini_model,
            prompt=prompt,
            schema=RecommendationResult,
            temperature=None,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
