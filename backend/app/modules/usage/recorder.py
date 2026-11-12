"""Writes usage rows. Recording must never break the call it measures: every failure here is
logged and swallowed. Rows are written in their own short session, independent of the caller's
transaction (the same way job progress is), so a rolled-back job still keeps its cost record."""

import logging
import re
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


_KEY_LIKE = re.compile(r"(?i)\b(api[_-]?key|key|token|authorization|bearer)\b\s*[=:]\s*\S+")
_GOOGLE_KEY = re.compile(r"AIza[0-9A-Za-z_\-]{20,}")
_GROQ_KEY = re.compile(r"gsk_[0-9A-Za-z]{20,}")


def short_error(source: object, limit: int = 200) -> str:
    """A failed call's reason in one short line that is safe to store: whitespace collapsed,
    anything that looks like a key or token replaced, and cut to `limit` characters. An exception
    is shown as its type and message."""
    if isinstance(source, BaseException):
        text = f"{type(source).__name__}: {source}"
    else:
        text = str(source)
    text = " ".join(text.split())
    text = _KEY_LIKE.sub(lambda m: f"{m.group(1)}=***", text)
    text = _GOOGLE_KEY.sub("***", text)
    text = _GROQ_KEY.sub("***", text)
    return text[:limit]


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
    cached_tokens: int | None = None,
    thinking_tokens: int | None = None,
    error: str | None = None,
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
            cached_tokens=cached_tokens,
            thinking_tokens=thinking_tokens,
            latency_ms=latency_ms,
            error=short_error(error) if status == "error" and error else None,
            est_cost_usd=estimate_cost_usd(provider, kind, tokens_in, tokens_out, units),
        )
        await _sink(row)
    except Exception:  # noqa: BLE001 - metering must never break the call it measures
        logger.warning("could not record %s usage", provider, exc_info=True)
