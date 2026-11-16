"""The offerings a company was searched for in Market Discovery, and what is already known about how
they fit. The Brief starts from these: the first areas it suggests are the ones the person searched
for, and their fit comes from stored judgments (computed in code), never from new model text."""

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.ingestion.models import IngestionRun, IngestionRunCompany
from app.modules.opportunity.fit import latest_matches
from app.modules.opportunity.models import (
    BAND_INSUFFICIENT,
    BAND_POTENTIAL,
    BAND_STRONG,
    BAND_WEAK,
    GENERAL_AREA_KEY,
    CompanyOpportunity,
    OpportunityOfferingMatch,
)
from app.modules.opportunity.shortlist import offering_weights, words
from app.modules.products.models import STATUS_ACTIVE, Product

BAND_LABEL = {
    BAND_STRONG: "Strong fit",
    BAND_POTENTIAL: "Possible fit",
    BAND_WEAK: "Weak fit",
    BAND_INSUFFICIENT: "Not enough evidence",
}
# The bands that count as a good answer for an offering. Anything else, or no answer yet, means the
# list should also offer the next best areas.
GOOD_BANDS = (BAND_STRONG, BAND_POTENTIAL)


@dataclass(frozen=True)
class FocusOffering:
    product_id: uuid.UUID
    name: str
    kind: str
    area_label: str
    area_tags: list[str]


def area_for_product(product: Product) -> str:
    """The area a brief around this offering researches: its first area tag (what it is sold into),
    or its own name. The same rule as `briefTargets` on the screen."""
    for tag in (product.buyer_profile or {}).get("area_tags", []) or []:
        if isinstance(tag, str) and tag.strip():
            return tag.strip()
    return product.name.strip()


def focus_hash(product_ids: list[uuid.UUID]) -> str:
    """A fingerprint of a set of offerings, order and repeats ignored."""
    joined = ",".join(sorted({str(p) for p in product_ids}))
    return hashlib.sha256(joined.encode()).hexdigest()[:32]


async def company_runs(
    session: AsyncSession, organization_id: uuid.UUID, company_id: uuid.UUID
) -> list[IngestionRun]:
    """The Market Discovery runs this company belongs to, newest first. Membership rows first, then
    the run that created the company for companies older than the membership table."""
    run_ids = list(
        (
            await session.execute(
                select(IngestionRunCompany.run_id).where(
                    IngestionRunCompany.organization_id == organization_id,
                    IngestionRunCompany.company_id == company_id,
                )
            )
        ).scalars()
    )
    company = await session.get(Company, company_id)
    if company is not None and company.source_ingestion_run_id is not None:
        run_ids.append(company.source_ingestion_run_id)
    if not run_ids:
        return []
    runs = (
        (
            await session.execute(
                select(IngestionRun)
                .where(
                    IngestionRun.organization_id == organization_id,
                    IngestionRun.id.in_(set(run_ids)),
                )
                .order_by(IngestionRun.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(runs)


def run_product_ids(run: IngestionRun) -> list[uuid.UUID]:
    return [uuid.UUID(p) for p in ((run.context or {}).get("product_ids") or [])]


# An offering counts as matching the words searched for when it shares a word with its own keywords
# (2) or area tags (3), not just with its name or description, which are too loose.
MIN_KEYWORD_MATCH = 2
MAX_MATCHED_OFFERINGS = 3


def _own_match(product: Product, context: set[str]) -> int:
    """Points for shared words with the offering's own area tags and keywords only; words that
    appear just in its name or description do not count, they are too loose."""
    return sum(
        weight
        for word, weight in offering_weights(product).items()
        if word in context and weight >= MIN_KEYWORD_MATCH
    )


async def offerings_for_keywords(
    session: AsyncSession,
    organization_id: uuid.UUID,
    keywords: list[str],
    limit: int = MAX_MATCHED_OFFERINGS,
) -> list[uuid.UUID]:
    """The offerings that the words a search was about point to (for example "ServiceNow" or
    "digital transformation"), best match first. Free and explainable: shared words with each
    offering's own area tags and keywords, no model. Empty when nothing matches."""
    context = words(" ".join(keywords))
    if not context:
        return []
    products = (
        (
            await session.execute(
                select(Product).where(
                    Product.organization_id == organization_id, Product.status == STATUS_ACTIVE
                )
            )
        )
        .scalars()
        .all()
    )
    scored = sorted(
        ((_own_match(p, context), p.name.lower(), p) for p in products),
        key=lambda row: (-row[0], row[1]),
    )
    return [p.id for score, _name, p in scored if score >= MIN_KEYWORD_MATCH][:limit]


async def searched_for_run(session: AsyncSession, run: IngestionRun) -> tuple[list[uuid.UUID], str]:
    """The offerings a run is about, and how they were found: the ones chosen on the form
    ("chosen"), else the ones the searched words point to ("keywords")."""
    chosen = run_product_ids(run)
    if chosen:
        return chosen, "chosen"
    keywords = describe_run(run)["industry_keywords"]
    return await offerings_for_keywords(session, run.organization_id, keywords), "keywords"


async def searched_product_ids(
    session: AsyncSession, organization_id: uuid.UUID, company_id: uuid.UUID
) -> list[uuid.UUID]:
    """The offerings the most recent run that has any was about. Empty when the company never came
    from a run, or nothing in the search points to an offering."""
    for run in await company_runs(session, organization_id, company_id):
        ids, _how = await searched_for_run(session, run)
        if ids:
            return ids
    return []


async def load_focus(
    session: AsyncSession, organization_id: uuid.UUID, product_ids: list[uuid.UUID]
) -> list[FocusOffering]:
    """The offerings as focus entries, in the order asked for; unknown ids are skipped."""
    if not product_ids:
        return []
    rows = (
        (
            await session.execute(
                select(Product).where(
                    Product.organization_id == organization_id, Product.id.in_(set(product_ids))
                )
            )
        )
        .scalars()
        .all()
    )
    by_id = {p.id: p for p in rows}
    focus: list[FocusOffering] = []
    seen: set[uuid.UUID] = set()
    for pid in product_ids:
        product = by_id.get(pid)
        if product is None or pid in seen:
            continue
        seen.add(pid)
        tags = [
            t.strip()
            for t in ((product.buyer_profile or {}).get("area_tags") or [])
            if isinstance(t, str) and t.strip()
        ]
        focus.append(
            FocusOffering(
                product_id=product.id,
                name=product.name,
                kind=product.kind,
                area_label=area_for_product(product),
                area_tags=tags,
            )
        )
    return focus


async def overall_matches(
    session: AsyncSession, organization_id: uuid.UUID, company_id: uuid.UUID
) -> dict[object, OpportunityOfferingMatch]:
    """The newest stored fit judgment per offering on the company's overall view (where Market
    Discovery's fit stage keeps them)."""
    general = (
        await session.execute(
            select(CompanyOpportunity).where(
                CompanyOpportunity.organization_id == organization_id,
                CompanyOpportunity.company_id == company_id,
                CompanyOpportunity.area_key == GENERAL_AREA_KEY,
            )
        )
    ).scalar_one_or_none()
    if general is None:
        return {}
    return await latest_matches(session, general.id)


def best_known_match(
    product_id: uuid.UUID,
    overall: dict[object, OpportunityOfferingMatch],
    area_matches: dict[object, OpportunityOfferingMatch] | None = None,
) -> OpportunityOfferingMatch | None:
    """The stronger of what the overall view and the offering's own area say about it."""
    order = {BAND_STRONG: 3, BAND_POTENTIAL: 2, BAND_WEAK: 1, BAND_INSUFFICIENT: 0}
    candidates = [
        m for m in (overall.get(product_id), (area_matches or {}).get(product_id)) if m is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda m: (order.get(m.band, 0), m.score))


def first_sentence(text: str, limit: int = 220) -> str:
    cleaned = " ".join(text.split())
    for end in (". ", "! ", "? "):
        cut = cleaned.find(end)
        if 0 < cut < limit:
            return cleaned[: cut + 1]
    return cleaned[:limit].rstrip() + ("…" if len(cleaned) > limit else "")


def searched_reason(name: str, match: OpportunityOfferingMatch | None) -> str:
    """The sentence under a searched chip, built in code from the stored judgment."""
    base = f"You searched for {name} in Market Discovery."
    if match is None:
        return f"{base} Its fit has not been checked yet."
    label = BAND_LABEL.get(match.band, match.band)
    return f"{base} {label}: {first_sentence(match.reasoning)}"[:500]


def fit_is_good(match: OpportunityOfferingMatch | None) -> bool:
    return match is not None and match.band in GOOD_BANDS


def describe_run(run: IngestionRun) -> dict[str, Any]:
    """What was searched, from the run's parsed fields: keywords, location and size."""
    parsed = run.parsed_fields or {}

    def value(key: str) -> Any:
        return (parsed.get(key) or {}).get("value")

    return {
        "industry_keywords": value("industry_keywords") or [],
        "location": value("location"),
        "employee_size_range": value("employee_size_range"),
    }
