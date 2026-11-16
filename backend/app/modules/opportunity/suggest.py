"""Suggest opportunity areas for a company, starting from what the person searched for.

The list is ordered: first the areas for the offerings the company was searched for in Market
Discovery (their fit comes from stored judgments, never from new model text), then areas the
evidence supports that connect to those offerings or to ones the person selected, then, when the
searched offerings did not fit well, the next best areas elsewhere. The model proposes and labels;
this module keeps only verified areas and decides the order.

Suggesting is expensive, so it is done once per set of offerings: asking again returns the areas
already suggested. A refresh is an explicit second look that replaces them."""

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.modules.companies.models import Company
from app.modules.llm.structured import StructuredLLM
from app.modules.opportunity.areas import normalize_area_key
from app.modules.opportunity.discovery import (
    MAX_SUGGESTIONS,
    SuggestedArea,
    judge_areas,
    offering_areas,
    offering_catalogue,
    save_suggestions,
    suggest_areas,
)
from app.modules.opportunity.fit import latest_matches
from app.modules.opportunity.focus import (
    FocusOffering,
    best_known_match,
    fit_is_good,
    focus_hash,
    load_focus,
    overall_matches,
    searched_product_ids,
    searched_reason,
)
from app.modules.opportunity.models import (
    ORIGIN_MANUAL,
    ORIGIN_MARKET_DISCOVERY,
    SOURCE_EVIDENCE,
    SOURCE_NEXT_BEST,
    SOURCE_SEARCHED,
    STATUS_SUGGESTED,
    CompanyOpportunity,
    OpportunityOfferingMatch,
)
from app.modules.opportunity.service import (
    evidence_records_for,
    get_or_create_opportunity,
    list_opportunities,
)
from app.modules.usage.context import usage_scope

_SUPPORT_ORDER = {"clear": 0, "partial": 1, "": 2}


@dataclass
class SuggestionResult:
    areas: list[CompanyOpportunity]
    # One plain sentence for the screen: what was done, or why nothing new was found.
    notice: str


async def _in_use(session: AsyncSession, opportunity_id: uuid.UUID) -> bool:
    """Whether anything (an assessment, a match, a draft, evidence...) points at this opportunity.
    Read from the database's own foreign keys, so a table added later is covered."""
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            if fk.column.table.name == CompanyOpportunity.__tablename__:
                found = await session.scalar(
                    select(exists().where(table.c[fk.parent.name] == opportunity_id))
                )
                if found:
                    return True
    return False


async def _seed_searched(
    session: AsyncSession,
    company: Company,
    searched: list[FocusOffering],
    focus: str | None,
) -> list[CompanyOpportunity]:
    """One suggested area per offering the company was searched for, first in the list. The reason
    is built here from the stored fit. An area the person has already made active stays as it is.
    `focus` is recorded only once the evidence has been looked at too, see `suggest_with_notice`."""
    overall = await overall_matches(session, company.organization_id, company.id)
    saved: list[CompanyOpportunity] = []
    for rank, offering in enumerate(searched):
        opportunity, _ = await get_or_create_opportunity(
            session,
            company,
            offering.area_label,
            ORIGIN_MARKET_DISCOVERY,
            status=STATUS_SUGGESTED,
        )
        own = await latest_matches(session, opportunity.id)
        match = best_known_match(offering.product_id, overall, own)
        if opportunity.status == STATUS_SUGGESTED:
            opportunity.suggestion_reason = searched_reason(offering.name, match)
            opportunity.suggestion_source = SOURCE_SEARCHED
            opportunity.suggestion_rank = rank
            if focus is not None:
                opportunity.suggestion_focus = focus
        saved.append(opportunity)
    await session.flush()
    return saved


async def seed_searched_suggestions(session: AsyncSession, company: Company) -> int:
    """The searched areas as suggestions, without a model call, so the Brief opens with them.
    Returns how many were seeded."""
    searched = await load_focus(
        session,
        company.organization_id,
        await searched_product_ids(session, company.organization_id, company.id),
    )
    return len(await _seed_searched(session, company, searched, None))


async def _searched_fit_is_low(
    session: AsyncSession, company: Company, searched: list[FocusOffering]
) -> bool:
    """True when any searched offering has no good stored fit, on the overall view or in its own
    area. Then the next best areas are wanted too."""
    overall = await overall_matches(session, company.organization_id, company.id)
    opportunities = await list_opportunities(session, company.organization_id, company.id)
    for offering in searched:
        area_key = normalize_area_key(offering.area_label)
        own: dict[object, OpportunityOfferingMatch] = {}
        for opportunity in opportunities:
            if opportunity.area_key == area_key:
                own = await latest_matches(session, opportunity.id)
        if not fit_is_good(best_known_match(offering.product_id, overall, own)):
            return True
    return False


def _order(judged: list[SuggestedArea], focus_names: set[str]) -> list[tuple[SuggestedArea, str]]:
    """Areas linked to a focus offering first, then the rest as next best, each group strongest
    first. With no focus at all everything is plain evidence."""
    lowered = {n.lower() for n in focus_names}

    def key(area: SuggestedArea) -> int:
        return _SUPPORT_ORDER.get(area.support, 2)

    linked = sorted([a for a in judged if a.offering.lower() in lowered], key=key)
    other = sorted([a for a in judged if a.offering.lower() not in lowered], key=key)
    if not focus_names:
        return [(a, SOURCE_EVIDENCE) for a in [*linked, *other]]
    return [(a, SOURCE_EVIDENCE) for a in linked] + [(a, SOURCE_NEXT_BEST) for a in other]


def _reason(area: SuggestedArea) -> str:
    if area.offering and area.support:
        return f"{area.reason} Best served by {area.offering} ({area.support} support)."[:500]
    return area.reason[:500]


def _notice(searched: list[FocusOffering], widen: bool, found: int, had_evidence: bool) -> str:
    parts: list[str] = []
    if searched:
        names = ", ".join(f.name for f in searched)
        parts.append(f"Started with what you searched for in Market Discovery: {names}.")
    if widen:
        parts.append("Its fit was low or not checked, so the next best areas follow.")
    if found == 0:
        parts.append(
            "No other area is supported by the evidence yet."
            if had_evidence
            else "There is no evidence on file yet to suggest more areas from."
        )
    return " ".join(parts)


async def suggest_with_notice(
    session: AsyncSession,
    llm: StructuredLLM,
    company: Company,
    refresh: bool = False,
    selected_ids: list[uuid.UUID] | None = None,
) -> SuggestionResult:
    org = company.organization_id
    searched_ids = await searched_product_ids(session, org, company.id)
    extra_ids = [i for i in (selected_ids or []) if i not in set(searched_ids)]
    searched = await load_focus(session, org, searched_ids)
    selected = await load_focus(session, org, extra_ids)
    focus_names = [f.name for f in [*searched, *selected]]
    fhash = focus_hash([f.product_id for f in [*searched, *selected]])

    existing = [
        o
        for o in await list_opportunities(session, org, company.id)
        if o.status == STATUS_SUGGESTED
    ]
    no_focus = focus_hash([])
    if (
        existing
        and not refresh
        and all((o.suggestion_focus or no_focus) == fhash for o in existing)
    ):
        return SuggestionResult(
            existing, "Showing the areas already suggested. Press Refresh to look again."
        )

    general, _ = await get_or_create_opportunity(session, company, None, ORIGIN_MANUAL)
    seeded = await _seed_searched(session, company, searched, fhash)
    widen = bool(searched) and await _searched_fit_is_low(session, company, searched)
    taken = {normalize_area_key(o.area_label) for o in seeded}

    with usage_scope(company_id=company.id, opportunity_id=general.id):
        records = await evidence_records_for(session, general)
        areas = await offering_areas(session, org)
        industry = general.industry_context
        proposed = await suggest_areas(llm, company, records, areas, industry, focus=focus_names)
        if widen:
            more = await suggest_areas(
                llm, company, records, areas, industry, focus=focus_names, widen=True
            )
            known = {normalize_area_key(a.label) for a in proposed}
            proposed += [a for a in more if normalize_area_key(a.label) not in known]
        proposed = [a for a in proposed if normalize_area_key(a.label) not in taken]
        catalogue = await offering_catalogue(session, org)
        judged = (
            await judge_areas(llm, company, proposed, catalogue, focus_names) if proposed else []
        )

    ordered = _order(judged, set(focus_names))[:MAX_SUGGESTIONS]
    saved = await save_suggestions(session, company, [a for a, _ in ordered])
    by_key = {normalize_area_key(a.label): (a, source) for a, source in ordered}
    rank = len(seeded)
    for opportunity in saved:
        found = by_key.get(opportunity.area_key)
        if found is None or opportunity.status != STATUS_SUGGESTED:
            continue
        area, source = found
        opportunity.suggestion_reason = _reason(area)
        opportunity.suggestion_source = source
        opportunity.suggestion_rank = rank
        opportunity.suggestion_focus = fhash
        rank += 1

    keep = {o.id for o in seeded} | {o.id for o in saved}
    if refresh and not judged:
        # Nothing supported this time: keep what was suggested before rather than leave none.
        keep |= {o.id for o in existing}
    stale = [o for o in existing if o.id not in keep and not await _in_use(session, o.id)]
    if stale:
        await session.execute(
            delete(CompanyOpportunity).where(CompanyOpportunity.id.in_([o.id for o in stale]))
        )
    await session.flush()
    kept = existing if refresh and not judged else []
    shown = [o for o in [*seeded, *saved, *kept] if o.status == STATUS_SUGGESTED]
    unique = list({o.id: o for o in shown}.values())  # an area can be in both lists
    return SuggestionResult(unique, _notice(searched, widen, len(ordered), bool(records)))


async def suggest_for_company(
    session: AsyncSession,
    llm: StructuredLLM,
    company: Company,
    refresh: bool = False,
    selected_ids: list[uuid.UUID] | None = None,
) -> list[CompanyOpportunity]:
    return (await suggest_with_notice(session, llm, company, refresh, selected_ids)).areas
