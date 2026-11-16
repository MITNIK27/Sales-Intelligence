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
from app.modules.opportunity.llm_models import AreaJudgementsOut, AreaSuggestionsOut
from app.modules.opportunity.models import (
    GENERAL_AREA_KEY,
    ORIGIN_SUGGESTED,
    STATUS_SUGGESTED,
    CompanyOpportunity,
)
from app.modules.opportunity.prompts import build_area_judgement_prompt, build_area_prompt
from app.modules.opportunity.service import get_or_create_opportunity
from app.modules.products.models import STATUS_ACTIVE, Product

MAX_SUGGESTIONS = 5


@dataclass(frozen=True)
class SuggestedArea:
    label: str
    reason: str
    quote: str
    evidence_url: str | None
    # Filled in by `judge_areas`: the offering that serves the area best and how well the evidence
    # supports it ("clear", "partial"), empty when it was not judged.
    offering: str = ""
    support: str = ""


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
    focus: list[str] | None = None,
    widen: bool = False,
) -> list[SuggestedArea]:
    items = build_evidence_pack(company, records)
    if not items:
        return []
    answer = await llm.generate(
        build_area_prompt(
            company, industry, format_evidence(items), areas_we_cover, focus=focus, widen=widen
        ),
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


async def judge_areas(
    llm: StructuredLLM,
    company: Company,
    areas: list[SuggestedArea],
    offerings: list[tuple[str, list[str]]],
    focus: list[str],
) -> list[SuggestedArea]:
    """A second look at proposed areas, in one call: which offering serves each, and how well the
    evidence supports it. An area judged "none" is dropped. The model only labels; what is kept
    and in what order is decided by the caller from these labels. If the model leaves an area out
    it is kept unjudged rather than lost, since its quote was already verified."""
    if not areas:
        return []
    answer = await llm.generate(
        build_area_judgement_prompt(
            company, [(a.label, a.reason, a.quote) for a in areas], offerings, focus
        ),
        AreaJudgementsOut,
    )
    names = {name.strip().lower(): name for name, _ in offerings}
    by_key = {normalize_area_key(j.label): j for j in answer.areas}
    judged: list[SuggestedArea] = []
    for area in areas:
        verdict = by_key.get(normalize_area_key(area.label))
        if verdict is None:
            judged.append(area)
            continue
        support = verdict.support.strip().lower()
        if support == "none":
            continue
        offering = names.get(verdict.offering.strip().lower(), "")
        judged.append(
            SuggestedArea(
                label=area.label,
                reason=area.reason,
                quote=area.quote,
                evidence_url=area.evidence_url,
                offering=offering,
                support=support if support in ("clear", "partial") and offering else "",
            )
        )
    return judged


async def offering_catalogue(
    session: AsyncSession, organization_id: object
) -> list[tuple[str, list[str]]]:
    """Every active offering with its area tags, for judging which one an area is best served by."""
    products = (
        (
            await session.execute(
                select(Product)
                .where(Product.organization_id == organization_id, Product.status == STATUS_ACTIVE)
                .order_by(Product.name)
            )
        )
        .scalars()
        .all()
    )
    return [
        (
            p.name,
            [
                t.strip()
                for t in ((p.buyer_profile or {}).get("area_tags") or [])
                if isinstance(t, str) and t.strip()
            ],
        )
        for p in products
    ]
