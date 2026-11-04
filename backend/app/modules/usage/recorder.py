"""Writes usage rows. Recording must never break the call it measures: every failure here is
logged and swallowed. Rows are written in their own short session, independent of the caller's
transaction (the same way job progress is), so a rolled-back job still keeps its cost record."""

import logging
import time
from collections.abc import Awaitable, Callable

from app.core.config import get_settings
from app.modules.usage.context import current_usage_context
from app.modules.usage.models import ApiUsage
from app.modules.usage.pricing import estimate_cost_usd

logger = logging.getLogger(__name__)

UsageSink = Callable[[ApiUsage], Awaitable[None]]


async def _database_sink(row: ApiUsage) -> None:
    from app.db.session import SessionLocal  # imported late: it opens the engine on import

    async with SessionLocal() as session:
        session.add(row)
        await session.commit()


_sink: UsageSink = _database_sink


def set_usage_sink(sink: UsageSink) -> UsageSink:
    """Replace where rows go (tests collect them in a list). Returns the previous sink."""
    global _sink
    previous, _sink = _sink, sink
    return previous


def started() -> float:
    return time.monotonic()


def elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


async def record_usage(
    *,
    provider: str,
    kind: str,
    status: str = "ok",
    model: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    units: int | None = None,
    latency_ms: int | None = None,
) -> None:
    try:
        if not get_settings().usage_logging_enabled:
            return
        ctx = current_usage_context()
        row = ApiUsage(
            organization_id=ctx.organization_id,
            job_id=ctx.job_id,
            run_id=ctx.run_id,
            company_id=ctx.company_id,
            opportunity_id=ctx.opportunity_id,
            provider=provider,
            kind=kind,
            model=model,
            task=ctx.task or "unspecified",
            status=status,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            units=units,
            latency_ms=latency_ms,
            est_cost_usd=estimate_cost_usd(provider, kind, tokens_in, tokens_out, units),
        )
        await _sink(row)
    except Exception:  # noqa: BLE001 - metering must never break the call it measures
        logger.warning("could not record %s usage", provider, exc_info=True)
