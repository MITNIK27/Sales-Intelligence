"""Offering fit and the people who matter, for one opportunity: shortlist the offerings, judge
them, and for the best-fitting ones judge the contacts, widening the contact search around the area
when too few relevant people are known. Each part reuses what is still valid, so running it again
costs nothing unless something changed."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.enrichment.models import EnrichmentRecord
from app.modules.enrichment.providers.search_contacts import ContactSearchProvider
from app.modules.enrichment.service import _store_searched_contact
from app.modules.llm.structured import StructuredLLM
from app.modules.opportunity.fit import judge_offering_fit, latest_matches
from app.modules.opportunity.models import (
    BAND_POTENTIAL,
    BAND_STRONG,
    GENERAL_AREA_KEY,
    CompanyOpportunity,
    OpportunityOfferingMatch,
)
from app.modules.opportunity.pick import pick_offerings
from app.modules.opportunity.relevance import (
    judge_contact_relevance,
    relevant_count,
    resolve_relevance,
)
from app.modules.opportunity.service import latest_assessment
from app.modules.opportunity.shortlist import shortlist
from app.modules.products.models import STATUS_ACTIVE, Product
from app.modules.role_relevance.titles import load_search_titles

logger = logging.getLogger(__name__)

MIN_RELEVANT_PEOPLE = 2  # below this, search for more people around the area
MAX_OFFERINGS_FOR_CONTACTS = 1


@dataclass
class AnalysisResult:
    matches: list[OpportunityOfferingMatch] = field(default_factory=list)
    contact_products: list[Product] = field(default_factory=list)
    contacts_found: int = 0  # new people found by the area-aware search
    error: str | None = None
    product_names: dict[object, str] = field(default_factory=dict)
    # Why nothing was judged, when that is the case: one of the keys of OUTCOME_MESSAGES.
    reason: str | None = None


NO_ACTIVE_OFFERINGS = "no_active_offerings"
NO_SHORTLIST_MATCH = "no_shortlist_match"
NO_ANSWER = "no_answer"

# What a person is told when the analysis had nothing to judge. Written for the screen.
OUTCOME_MESSAGES = {
    NO_ACTIVE_OFFERINGS: (
        "There are no active offerings to compare. Add or activate offerings on the "
        "Our Offerings page, then work out the fit again."
    ),
    NO_ANSWER: "The model did not give an answer this time. Try again in a moment.",
    NO_SHORTLIST_MATCH: (
        "No offering stood out for this company from what is known about it. Pick offerings in "
        "the Offering filter, then work out the fit again."
    ),
}


def outcome_message(reason: str | None) -> str | None:
    return OUTCOME_MESSAGES.get(reason or "")


def shortlist_context(
    company: Company, opportunity: CompanyOpportunity, records: list[EnrichmentRecord]
) -> str:
    """The words the offerings are compared with: the company, the area and the evidence."""
    parts = [company.description or "", company.industry or "", opportunity.area_label]
    parts += [str((r.raw_payload or {}).get("text", "")) for r in records]
    return " ".join(parts)


async def active_offerings(session: AsyncSession, organization_id: object) -> list[Product]:
    return list(
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


async def company_contacts(session: AsyncSession, company_id: object) -> list[Contact]:
    return list(
        (await session.execute(select(Contact).where(Contact.company_id == company_id)))
        .scalars()
        .all()
    )


async def widen_contact_search(
    session: AsyncSession,
    company: Company,
    opportunity: CompanyOpportunity,
    provider: ContactSearchProvider | None,
    functions: list[str] | None = None,
) -> int:
    """Look for more people: the executives, the roles the offering is sold to (`functions`), and,
    for a named area, people tied to it. People found by search are never trusted: each is flagged
    for review. Where the results were lost is written to the opportunity's research log, so an
    empty answer can be explained. Returns how many new people were found."""
    if provider is None:
        return 0
    focus = None if opportunity.area_key == GENERAL_AREA_KEY else opportunity.area_label
    try:
        found = await provider.search_contacts(
            company.name,
            company.domain,
            focus=focus,
            functions=functions,
            titles=await load_search_titles(session, company.organization_id),
        )
    except Exception as exc:  # noqa: BLE001 - extra contacts are best-effort
        logger.info("contact search failed for %s: %s", company.id, exc)
        _log_people_search(opportunity, f"People search could not be completed ({exc})", 0)
        return 0
    created = 0
    for searched in found:
        async with session.begin_nested():
            if await _store_searched_contact(session, company.organization_id, company, searched):
                created += 1
    report = getattr(provider, "last_report", None)
    _log_people_search(
        opportunity,
        report.line(company.name) if report else f"People search found {len(found)} people.",
        created,
    )
    return created


def _log_people_search(opportunity: CompanyOpportunity, summary: str, created: int) -> None:
    log = dict(opportunity.research_log or {})
    log["people"] = {
        "at": datetime.now(UTC).isoformat(),
        "found": created,
        "searched": [],
        "error": None,
        "summary": summary,
    }
    opportunity.research_log = log  # a new dict, so the change is saved


def _buyer_functions(product: Product) -> list[str]:
    profile = product.buyer_profile or {}
    return [*(profile.get("buyer_functions") or []), *(profile.get("influencer_functions") or [])]


async def analyse_opportunity(
    session: AsyncSession,
    llm: StructuredLLM,
    company: Company,
    opportunity: CompanyOpportunity,
    records: list[EnrichmentRecord],
    *,
    chosen_ids: set[object] | None = None,
    with_contacts: bool = True,
    contact_search: ContactSearchProvider | None = None,
    force: bool = False,
    max_unchosen: int | None = None,
) -> AnalysisResult:
    result = AnalysisResult()
    catalog = await active_offerings(session, company.organization_id)
    by_words = shortlist(catalog, shortlist_context(company, opportunity, records), chosen_ids)
    existing = {} if force else await latest_matches(session, opportunity.id)
    if chosen_ids:
        candidates = [p for p in by_words if p.id in chosen_ids]  # exactly what the person chose
    elif not catalog:
        candidates = []
    elif existing:
        # Already matched: reuse those offerings (their judgements are cached) instead of asking
        # the model to choose again. "Check again" (force) chooses afresh.
        candidates = [p for p in catalog if p.id in existing]
    else:
        # Nothing chosen: word counts are a poor guide (long evidence shares common words with
        # unrelated offerings), so the model names the offerings worth judging, given what the
        # research found. The word match is only the fallback if it cannot.
        assessment = await latest_assessment(session, opportunity.id)
        findings = [
            str(f.get("statement", "")) for f in (assessment.findings if assessment else [])
        ]
        candidates = await pick_offerings(
            llm,
            company,
            opportunity,
            catalog,
            findings=[f for f in findings if f],
            fallback=by_words,
        )
        if max_unchosen is not None:
            candidates = candidates[:max_unchosen]
    if not candidates:
        result.reason = NO_SHORTLIST_MATCH if catalog else NO_ACTIVE_OFFERINGS
        return result
    result.product_names = {p.id: p.name for p in candidates}
    result.matches = await judge_offering_fit(
        session, llm, company, opportunity, records, candidates, force=force
    )
    if not result.matches:
        result.reason = NO_ANSWER
        return result
    if not with_contacts:
        return result

    by_id = {p.id: p for p in candidates}
    if chosen_ids:
        targets = [by_id[i] for i in chosen_ids if i in by_id][:MAX_OFFERINGS_FOR_CONTACTS]
    else:
        targets = [
            by_id[m.product_id] for m in result.matches if m.band in (BAND_STRONG, BAND_POTENTIAL)
        ][:MAX_OFFERINGS_FOR_CONTACTS]
    result.contact_products = targets

    for product in targets:
        contacts = await company_contacts(session, company.id)
        await judge_contact_relevance(session, llm, company, opportunity, product, contacts, force)
        resolved = await resolve_relevance(session, opportunity.id, product.id)
        if relevant_count(resolved) < MIN_RELEVANT_PEOPLE:
            added = await widen_contact_search(
                session, company, opportunity, contact_search, _buyer_functions(product)
            )
            if added:
                result.contacts_found += added
                contacts = await company_contacts(session, company.id)
                await judge_contact_relevance(
                    session, llm, company, opportunity, product, contacts, force
                )
    return result
