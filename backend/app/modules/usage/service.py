import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.usage.models import ApiUsage


@dataclass(frozen=True)
class UsageLine:
    provider: str
    task: str
    calls: int
    errors: int
    tokens_in: int
    tokens_out: int
    units: int
    est_cost_usd: float


async def summarize_usage(
    session: AsyncSession,
    since: datetime,
    organization_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
) -> list[UsageLine]:
    """Calls, tokens, queries or credits and estimated cost, grouped by provider and task. Each
    retry attempt is its own row, so `calls` counts attempts and `errors` the failed ones."""
    stmt = select(ApiUsage).where(ApiUsage.created_at >= since)
    if organization_id is not None:
        stmt = stmt.where(ApiUsage.organization_id == organization_id)
    if run_id is not None:
        stmt = stmt.where(ApiUsage.run_id == run_id)
    rows = (await session.execute(stmt)).scalars().all()

    grouped: dict[tuple[str, str], list[ApiUsage]] = {}
    for row in rows:
        grouped.setdefault((row.provider, row.task), []).append(row)
    return [
        UsageLine(
            provider=provider,
            task=task,
            calls=len(items),
            errors=sum(1 for r in items if r.status == "error"),
            tokens_in=sum(r.tokens_in or 0 for r in items),
            tokens_out=sum(r.tokens_out or 0 for r in items),
            units=sum(r.units or 0 for r in items),
            est_cost_usd=sum(r.est_cost_usd or 0.0 for r in items),
        )
        for (provider, task), items in sorted(grouped.items())
    ]


@dataclass(frozen=True)
class CompanyCost:
    companies: int
    total_est_cost_usd: float
    average_est_cost_usd: float
    most_expensive: list[tuple[uuid.UUID, float]]


async def cost_per_company(session: AsyncSession, since: datetime, top: int = 5) -> CompanyCost:
    """What each company cost to research, from calls tagged with a company. Calls made outside a
    company (for example parsing a market prompt) are not counted here."""
    rows = (
        await session.execute(
            select(ApiUsage.company_id, ApiUsage.est_cost_usd).where(
                ApiUsage.created_at >= since, ApiUsage.company_id.is_not(None)
            )
        )
    ).all()
    totals: dict[uuid.UUID, float] = {}
    for company_id, cost in rows:
        totals[company_id] = totals.get(company_id, 0.0) + (cost or 0.0)
    total = sum(totals.values())
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])[:top]
    return CompanyCost(
        companies=len(totals),
        total_est_cost_usd=total,
        average_est_cost_usd=total / len(totals) if totals else 0.0,
        most_expensive=ranked,
    )
