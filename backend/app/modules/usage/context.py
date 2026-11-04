"""Who a call is for. Set once where work starts (the worker sets it per job) and read where the
call is made, so the low-level clients never need to be told which company or run they serve."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class UsageContext:
    organization_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    task: str | None = None


_current: ContextVar[UsageContext | None] = ContextVar("usage_context", default=None)


def current_usage_context() -> UsageContext:
    return _current.get() or UsageContext()


@contextmanager
def usage_scope(**fields: Any) -> Iterator[None]:
    """Add to the current context for the duration of the block; empty values are ignored so a
    caller can pass optional ids without checking them first."""
    token = _current.set(replace(current_usage_context(), **{k: v for k, v in fields.items() if v}))
    try:
        yield
    finally:
        _current.reset(token)
