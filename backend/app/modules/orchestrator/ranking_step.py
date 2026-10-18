"""The ranking stage of the auto pipeline: loads what each judged company looks like, scores it
with `qualification.ranking`, stores the score on its latest qualification result, and returns the
companies best-first. This is the only place that touches the database for ranking — the scoring
itself is pure and lives in `ranking.py`."""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.contacts.models import Contact, ContactChannel
from app.modules.enrichment.service import list_company_signals
from app.modules.qualification.models import QualificationResult
from app.modules.qualification.ranking import RankInputs, compute_priority

VERDICT_QUALIFIED = "qualified"
LINKEDIN_CHANNEL = "linkedin"


@dataclass
class RankedCompany:
    company_id: uuid.UUID
    verdict: str
    score: float
    excluded: bool


async def _latest_results(
    session: AsyncSession, company_ids: list[uuid.UUID]
) -> dict[uuid.UUID, QualificationResult]:
    latest: dict[uuid.UUID, QualificationResult] = {}
    rows = await session.execute(
        select(QualificationResult)
        .where(QualificationResult.company_id.in_(company_ids))
        .order_by(QualificationResult.created_at.asc())
    )
    for result in rows.scalars():
        latest[result.company_id] = result
    return latest


async def rank_judged_companies(
    session: AsyncSession,
    organization_id: uuid.UUID,
    company_ids: list[uuid.UUID],
    *,
    requested_keywords: list[str],
    requested_size: str | None,
) -> list[RankedCompany]:
    """Scores every company that has a qualification result, persists the score, and returns
    them ordered best-first. Fully qualified companies always come before ones that could not be
    verified; within each group, higher Priority Score first. Hard FAILs are returned too
    (excluded, score 0, last) so the caller can report them."""
    if not company_ids:
        return []
    results = await _latest_results(session, company_ids)

    contact_rows = await session.execute(
        select(Contact.company_id, func.count())
        .where(Contact.company_id.in_(company_ids))
        .group_by(Contact.company_id)
    )
    contact_counts = {row[0]: row[1] for row in contact_rows.all()}
    linkedin_rows = await session.execute(
        select(Contact.company_id, func.count(func.distinct(Contact.id)))
        .join(ContactChannel, ContactChannel.contact_id == Contact.id)
        .where(
            Contact.company_id.in_(company_ids),
            ContactChannel.channel_type == LINKEDIN_CHANNEL,
        )
        .group_by(Contact.company_id)
    )
    linkedin_counts = {row[0]: row[1] for row in linkedin_rows.all()}

    ranked: list[RankedCompany] = []
    for company_id in company_ids:
        result = results.get(company_id)
        company = await session.get(Company, company_id)
        if result is None or company is None:
            continue
        signals = await list_company_signals(session, organization_id, company_id)
        payloads: list[dict[str, Any]] = [dict(s.raw_payload or {}) for s in signals]
        outcome = compute_priority(
            RankInputs(
                criteria_results=[dict(c) for c in result.criteria_results or []],
                industry=company.industry,
                description=company.description,
                employee_count_range=company.employee_count_range,
                requested_keywords=requested_keywords,
                requested_size=requested_size,
                signal_dates=[p.get("date") for p in payloads],
                contact_count=contact_counts.get(company_id, 0),
                contacts_with_linkedin=linkedin_counts.get(company_id, 0),
            )
        )
        result.priority_score = outcome.score
        result.score_breakdown = outcome.breakdown
        ranked.append(
            RankedCompany(company_id, result.overall_verdict, outcome.score, outcome.excluded)
        )
    await session.flush()

    ranked.sort(
        key=lambda r: (
            r.excluded,
            r.verdict != VERDICT_QUALIFIED,
            -r.score,
        )
    )
    return ranked
