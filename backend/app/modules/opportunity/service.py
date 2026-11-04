import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.enrichment.models import ENTITY_TYPE_COMPANY, EnrichmentRecord
from app.modules.enrichment.service import list_company_signals
from app.modules.enrichment.signals import normalize_title
from app.modules.opportunity.areas import clean_area_label, normalize_area_key
from app.modules.opportunity.models import (
    GENERAL_AREA_KEY,
    STATUS_ACTIVE,
    CompanyOpportunity,
    OpportunityAssessment,
)
from app.modules.opportunity.research.types import CollectedItem

FOCUS_SEARCH_SOURCE = "opportunity:serper:focus"
FOCUS_SEARCH_TYPE = "focus_search"


async def get_or_create_opportunity(
    session: AsyncSession,
    company: Company,
    label: str | None,
    origin: str,
    status: str = STATUS_ACTIVE,
    created_by_run_id: uuid.UUID | None = None,
    suggestion_reason: str | None = None,
) -> tuple[CompanyOpportunity, bool]:
    """The opportunity for this company and area, created when it does not exist yet. Asking for
    the same area twice (however it is typed) finds the same row; an existing one is returned as
    it is, never overwritten."""
    area_key = normalize_area_key(label)
    existing = (
        await session.execute(
            select(CompanyOpportunity).where(
                CompanyOpportunity.organization_id == company.organization_id,
                CompanyOpportunity.company_id == company.id,
                CompanyOpportunity.area_key == area_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    opportunity = CompanyOpportunity(
        organization_id=company.organization_id,
        company_id=company.id,
        area_key=area_key,
        area_label=clean_area_label(label) or "Overall",
        origin=origin,
        status=status,
        industry_context=company.industry,
        created_by_run_id=created_by_run_id,
        suggestion_reason=suggestion_reason,
    )
    session.add(opportunity)
    await session.flush()
    return opportunity, True


async def get_opportunity(
    session: AsyncSession, organization_id: uuid.UUID, opportunity_id: uuid.UUID
) -> CompanyOpportunity | None:
    opportunity = await session.get(CompanyOpportunity, opportunity_id)
    if opportunity is None or opportunity.organization_id != organization_id:
        return None
    return opportunity


async def list_opportunities(
    session: AsyncSession, organization_id: uuid.UUID, company_id: uuid.UUID
) -> list[CompanyOpportunity]:
    stmt = (
        select(CompanyOpportunity)
        .where(
            CompanyOpportunity.organization_id == organization_id,
            CompanyOpportunity.company_id == company_id,
        )
        .order_by(CompanyOpportunity.area_key != GENERAL_AREA_KEY, CompanyOpportunity.created_at)
    )
    return list((await session.execute(stmt)).scalars().all())


async def latest_assessment(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> OpportunityAssessment | None:
    stmt = (
        select(OpportunityAssessment)
        .where(OpportunityAssessment.company_opportunity_id == opportunity_id)
        .order_by(OpportunityAssessment.version.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def next_version(session: AsyncSession, opportunity_id: uuid.UUID) -> int:
    current = (
        await session.execute(
            select(func.max(OpportunityAssessment.version)).where(
                OpportunityAssessment.company_opportunity_id == opportunity_id
            )
        )
    ).scalar_one()
    return (current or 0) + 1


async def area_evidence_records(
    session: AsyncSession, opportunity: CompanyOpportunity
) -> list[EnrichmentRecord]:
    """Evidence gathered for this area only, newest first."""
    stmt = (
        select(EnrichmentRecord)
        .where(EnrichmentRecord.company_opportunity_id == opportunity.id)
        .order_by(EnrichmentRecord.fetched_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def evidence_records_for(
    session: AsyncSession, opportunity: CompanyOpportunity
) -> list[EnrichmentRecord]:
    """Everything a judgment about this opportunity may use: the area's own evidence first, then
    the company-level signals every area shares. Company-level evidence is referenced, never
    copied into the area."""
    own = await area_evidence_records(session, opportunity)
    shared = await list_company_signals(
        session, opportunity.organization_id, opportunity.company_id
    )
    return [*own, *shared]


async def save_area_records(
    session: AsyncSession,
    company: Company,
    opportunity: CompanyOpportunity,
    source: str,
    items: list[CollectedItem],
) -> list[EnrichmentRecord]:
    """Keep what a collector found as evidence tagged with the opportunity, so it has an id and can
    be cited and re-audited. An item already stored for this area and source (same address and
    text) is not stored again; the stored record is returned instead."""
    known = {
        (
            (r.raw_payload or {}).get("url"),
            normalize_title(str((r.raw_payload or {}).get("text", ""))),
        ): r
        for r in await area_evidence_records(session, opportunity)
        if r.source == source
    }
    now = datetime.now(UTC)
    saved: list[EnrichmentRecord] = []
    for item in items:
        text = item.text.strip()
        if not text:
            continue
        key = (item.url, normalize_title(text))
        record = known.get(key)
        if record is None:
            record = EnrichmentRecord(
                organization_id=company.organization_id,
                entity_type=ENTITY_TYPE_COMPANY,
                entity_id=company.id,
                company_opportunity_id=opportunity.id,
                source=source,
                raw_payload={
                    "signal_type": item.signal_type,
                    "text": text,
                    "url": item.url,
                    "date": item.date,
                    "summary": item.summary,
                    "provider": item.provider,
                    **item.extra,
                },
                fetched_at=now,
            )
            session.add(record)
            known[key] = record
        saved.append(record)
    await session.flush()
    return saved


async def save_focus_evidence(
    session: AsyncSession,
    company: Company,
    opportunity: CompanyOpportunity,
    hits: list[dict[str, str]],
) -> list[EnrichmentRecord]:
    """The results of an area-focused web search (Quick Check's focus), kept as evidence."""
    items = []
    for hit in hits:
        title = (hit.get("title") or "").strip()
        snippet = (hit.get("snippet") or "").strip()
        if title or snippet:
            items.append(
                CollectedItem(
                    signal_type=FOCUS_SEARCH_TYPE,
                    text=f"{title}. {snippet}".strip(),
                    url=hit.get("link"),
                    date=hit.get("date"),
                    provider="serper",
                )
            )
    return await save_area_records(session, company, opportunity, FOCUS_SEARCH_SOURCE, items)
