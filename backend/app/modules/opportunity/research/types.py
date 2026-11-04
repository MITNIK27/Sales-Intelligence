from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

SIGNAL_NEWS = "news"
SIGNAL_JOB_POSTING = "job_posting"
SIGNAL_WEB = "web_result"

KIND_NEWS = "news"
KIND_HIRING = "hiring"
KIND_WEB = "web"


@dataclass(frozen=True)
class CollectedItem:
    """One piece of evidence found by a collector, before it is saved as an evidence record."""

    signal_type: str
    text: str
    url: str | None = None
    date: str | None = None  # as the source gave it; None when the source gives no date
    summary: str | None = None
    provider: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Posting:
    title: str
    url: str | None = None
    department: str | None = None
    location: str | None = None
    posted: str | None = None  # ISO date when the board states one (Lever does not)
    excerpt: str = ""


@dataclass(frozen=True)
class HiringResult:
    """What the job-board lookup found. `board` is None when the company's careers page did not
    point at a supported board, which is reported as such rather than guessed around."""

    postings: list[Posting]
    board: str | None  # for example "greenhouse:acme"
    searched: list[str]
    error: str | None = None


@dataclass
class SourceReport:
    """What one collector did, kept on the opportunity so the screen can say what was searched,
    how much was found and when, and so a repeat request within the freshness window is skipped."""

    kind: str
    searched: list[str] = field(default_factory=list)
    found: int = 0
    skipped: bool = False  # still fresh from an earlier run, so not searched again
    error: str | None = None
    note: str | None = None
    total_open: int | None = None  # hiring only: every open role on the board, not just matches
    board: str | None = None


class NewsSource(Protocol):
    async def search(self, query: str, since: datetime, limit: int) -> list[CollectedItem]: ...


class WebSource(Protocol):
    async def search(
        self, query: str, include_domains: list[str] | None, limit: int
    ) -> list[CollectedItem]: ...


class HiringSource(Protocol):
    async def postings(self, domain: str) -> HiringResult: ...


@dataclass
class ResearchSources:
    """Where evidence is looked for. Any of them may be absent (no key configured); an absent
    source is reported as not searched, never as "nothing found"."""

    news: NewsSource | None = None
    web: WebSource | None = None
    hiring: HiringSource | None = None
    extra: dict[str, Any] = field(default_factory=dict)
