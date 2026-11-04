"""Which offerings to judge when no word in common was found. The word-overlap shortlist is free but
literal: a company talking about "moving plants off old servers" shares no word with an offering
tagged "cloud migration". Rather than give up, the model is shown the catalogue and names the few
most worth judging. Its answer is only a shortlist: every name is checked against the catalogue, and
each pick is then judged against evidence like any other offering."""

import logging
import re

from pydantic import BaseModel

from app.modules.companies.models import Company
from app.modules.llm.structured import StructuredLLM
from app.modules.llm.untrusted import untrusted_aware, wrap_untrusted
from app.modules.opportunity.models import CompanyOpportunity
from app.modules.opportunity.shortlist import SHORTLIST_SIZE
from app.modules.products.models import Product

logger = logging.getLogger(__name__)

_MAX_CATALOGUE = 80
_DESCRIPTION_CHARS = 160


class OfferingPickOut(BaseModel):
    offerings: list[str]  # catalogue labels, best first, for example "O4"


def _line(label: str, product: Product) -> str:
    tags = ", ".join(((product.buyer_profile or {}).get("area_tags") or [])[:4])
    description = (product.description or "").strip().replace("\n", " ")[:_DESCRIPTION_CHARS]
    parts = [f"{label}: {product.name}"]
    if description:
        parts.append(description)
    if tags:
        parts.append(f"(sold into: {tags})")
    return " - ".join(parts)


@untrusted_aware
def build_pick_prompt(
    company: Company,
    opportunity: CompanyOpportunity,
    labelled: list[tuple[str, Product]],
    limit: int,
    findings: list[str] | None = None,
) -> str:
    about = " ".join(
        part for part in [company.description or "", company.industry or ""] if part
    ).strip()
    return (
        "You choose which of our offerings are worth considering for a company.\n"
        f"Company: {company.name}. {wrap_untrusted(about[:600], 'company description')}\n"
        f"Area being researched: {opportunity.area_label}\n"
        + (
            "What the research found:\n" + "\n".join(f"- {f}" for f in findings[:8]) + "\n"
            if findings
            else ""
        )
        + "\n"
        "Our offerings:\n" + "\n".join(_line(label, p) for label, p in labelled) + "\n\n"
        f"Name the {limit} offerings most likely to help this company with this area, best first. "
        'Answer with JSON: {"offerings": ["O1", "O2"]} using only the labels above.'
    )


async def pick_offerings(
    llm: StructuredLLM,
    company: Company,
    opportunity: CompanyOpportunity,
    catalogue: list[Product],
    limit: int = SHORTLIST_SIZE,
    findings: list[str] | None = None,
    fallback: list[Product] | None = None,
) -> list[Product]:
    """Up to `limit` offerings worth judging, from the model's choice, given what the research
    found. If the model cannot be reached or names nothing real, `fallback` (the word-match
    shortlist) is used, or failing that the first few offerings by name, so the person still gets
    a judgement to look at instead of an empty page."""
    ordered = sorted(catalogue, key=lambda p: p.name.lower())[:_MAX_CATALOGUE]
    labelled = [(f"O{i}", p) for i, p in enumerate(ordered, start=1)]
    by_label = {label: p for label, p in labelled}
    chosen: list[Product] = []
    try:
        out = await llm.generate(
            build_pick_prompt(company, opportunity, labelled, limit, findings), OfferingPickOut
        )
        for raw in getattr(out, "offerings", []):
            if not isinstance(raw, str):
                continue
            match = re.search(r"O\d+", raw.upper())
            product = by_label.get(match.group(0)) if match else None
            if product is not None and product not in chosen:
                chosen.append(product)
    except Exception as exc:  # noqa: BLE001 - a shortlist is best-effort
        logger.info("offering pick failed for %s: %s", company.id, exc)
    return (chosen or fallback or ordered)[:limit]
