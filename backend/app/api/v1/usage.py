"""Read-only usage summary for the dashboard. GET only; nothing here writes."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.usage.service import summarize_usage

router = APIRouter(prefix="/usage", tags=["usage"])


class UsageLineOut(BaseModel):
    provider: str
    task: str
    calls: int
    errors: int
    tokens_in: int
    tokens_out: int
    units: int
    est_cost_usd: float


class UsageSummaryOut(BaseModel):
    days: int
    lines: list[UsageLineOut]
    total_est_cost_usd: float


@router.get("/summary", response_model=UsageSummaryOut)
async def get_usage_summary(
    days: int = Query(30, ge=1, le=365), session: AsyncSession = Depends(get_db)
) -> UsageSummaryOut:
    """Calls, tokens and estimated cost by provider and task. Estimates from published prices,
    shown at their paid-equivalent even on free tiers; not a bill. Not filtered by organisation,
    because calls made outside a job carry none (this is a single-organisation tool)."""
    since = datetime.now(UTC) - timedelta(days=days)
    lines = await summarize_usage(session, since)
    out = [UsageLineOut(**vars(line)) for line in lines]
    return UsageSummaryOut(
        days=days, lines=out, total_est_cost_usd=sum(line.est_cost_usd for line in out)
    )
