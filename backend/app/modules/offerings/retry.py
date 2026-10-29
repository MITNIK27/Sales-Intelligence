"""Retry for the short network blips (a DNS lookup failing, a connection reset) that should not
cost a whole sync. Only transport-level failures are retried; a real answer such as 404 never is."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)

# Seconds to wait before each further attempt (so three attempts in all). A module constant so
# tests can zero the waits.
RETRY_WAITS: tuple[float, ...] = (1.0, 3.0)


async def with_retries[T](call: Callable[[], Awaitable[T]], what: str) -> T:
    """Runs `call`, retrying on transport errors and timeouts; raises the last error."""
    for wait in RETRY_WAITS:
        try:
            return await call()
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            logger.info("%s hit a network problem (%s), retrying in %.0fs", what, exc, wait)
            await asyncio.sleep(wait)
    return await call()
