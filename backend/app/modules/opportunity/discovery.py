"""Finding opportunity areas when nobody named one: from the evidence we already have, propose the
few areas where the company shows real activity. Each proposal must cite evidence with a quote
that is really in it; a proposal that cannot is dropped. When the evidence is thin the honest
answer is no suggestions, and that is returned as such."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.enrichment.models import EnrichmentRecord
from app.modules.llm.structured import StructuredLLM
from app.modules.opportunity.areas import clean_area_label, normalize_area_key
from app.modules.opportunity.evidence import (
    build_evidence_pack,
    format_evidence,
    verify_citation,
)
from app.modules.opportunity.llm_models import AreaSuggestionsOut
from app.modules.opportunity.models import (
    GENERAL_AREA_KEY,
    ORIGIN_SUGGESTED,
    STATUS_SUGGESTED,
    CompanyOpportunity,
)
from app.modules.opportunity.prompts import build_area_prompt
from app.modules.opportunity.service import get_or_create_opportunity
from app.modules.products.models import STATUS_ACTIVE, Product

MAX_SUGGESTIONS = 5


@dataclass(frozen=True)
class SuggestedArea:
    label: str
    reason: str
    quote: str
    evidence_url: str | None


async def offering_areas(session: AsyncSession, organization_id: object) -> list[str]:
    """The opportunity areas InfoBeans' offerings say they belong to (their buyer profiles'
    area tags), so suggestions are anchored to things we can actually help with."""
    products = (
        (
            await session.execute(
                select(Product).where(
                    Product.organization_id == organization_id,
                    Product.status == STATUS_ACTIVE,
                    Product.buyer_profile.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    seen: dict[str, str] = {}
    for product in products:
        for tag in (product.buyer_profile or {}).get("area_tags", []):
            seen.setdefault(normalize_area_key(tag), tag)
    return sorted(seen.values(), key=str.lower)


async def suggest_areas(
    llm: StructuredLLM,
    company: Company,
    records: list[EnrichmentRecord],
    areas_we_cover: list[str],
    industry: str | None = None,
) -> list[SuggestedArea]:
    items = build_evidence_pack(company, records)
    if not items:
        return []
    answer = await llm.generate(
        build_area_prompt(company, industry, format_evidence(items), areas_we_cover),
        AreaSuggestionsOut,
    )
    by_label = {item.label: item for item in items}
    suggestions: list[SuggestedArea] = []
    seen_keys: set[str] = set()
    for proposed in answer.areas:
        label = clean_area_label(proposed.label)
        item = verify_citation(by_label, proposed.evidence, proposed.quote)
        key = normalize_area_key(label)
        if not label or item is None or key == GENERAL_AREA_KEY or key in seen_keys:
            continue
        seen_keys.add(key)
        suggestions.append(
            SuggestedArea(
                label=label,
                reason=proposed.reason.strip()[:500],
                quote=proposed.quote.strip(),
                evidence_url=item.url,
            )
        )
        if len(suggestions) == MAX_SUGGESTIONS:
            break
    return suggestions


async def save_suggestions(
    session: AsyncSession, company: Company, suggestions: list[SuggestedArea]
) -> list[CompanyOpportunity]:
    """Each suggestion becomes a suggested opportunity (nothing deep is researched for it until a
    person chooses it). An area the company already has an opportunity for is left as it is."""
    saved: list[CompanyOpportunity] = []
    for suggestion in suggestions:
        opportunity, _created = await get_or_create_opportunity(
            session,
            company,
            suggestion.label,
            origin=ORIGIN_SUGGESTED,
            status=STATUS_SUGGESTED,
            suggestion_reason=suggestion.reason,
        )
        saved.append(opportunity)
    return saved
