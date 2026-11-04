"""The real places evidence is looked for. Each is a thin adapter from a provider's response to
`CollectedItem`s, so the collection logic can be tested against fakes without any network."""

import logging
from datetime import datetime
from typing import Any

import httpx

from app.core.config import Settings
from app.modules.enrichment.providers.context_dev import ContextDevProvider
from app.modules.enrichment.providers.search_serper import SerperSearchProvider
from app.modules.enrichment.providers.website_scraper import WebsiteScraperProvider
from app.modules.opportunity.research.ats import Board, find_board, parse_board
from app.modules.opportunity.research.types import (
    SIGNAL_NEWS,
    SIGNAL_WEB,
    CollectedItem,
    HiringResult,
    ResearchSources,
)

logger = logging.getLogger(__name__)

# Where a company's careers page usually lives; the first one that links to a board is used.
_CAREERS_PATHS = ("/careers", "/jobs", "/careers/", "/about/careers", "/company/careers")
_BOARD_TIMEOUT = 15.0


class ContextDevNewsSource:
    def __init__(self, provider: ContextDevProvider) -> None:
        self._provider = provider

    async def by_domain(self, domain: str, since: datetime, limit: int) -> list[CollectedItem]:
        """News about the company that owns this website (not every company with the same name)."""
        articles = await self._provider.search_company_news(
            domain, int(since.timestamp() * 1000), limit
        )
        return [
            CollectedItem(
                signal_type=SIGNAL_NEWS,
                text=a["title"],
                url=a["url"],
                date=a["published_at"],
                summary=a["description"],
                provider="contextdev",
            )
            for a in articles
        ]

    async def search(self, query: str, since: datetime, limit: int) -> list[CollectedItem]:
        articles = await self._provider.search_news(query, int(since.timestamp() * 1000), limit)
        return [
            CollectedItem(
                signal_type=SIGNAL_NEWS,
                text=a["title"],
                url=a["url"],
                date=a["published_at"],
                summary=a["description"],
                provider="contextdev",
            )
            for a in articles
        ]


class ContextDevWebSource:
    def __init__(self, provider: ContextDevProvider) -> None:
        self._provider = provider

    async def search(
        self, query: str, include_domains: list[str] | None, limit: int
    ) -> list[CollectedItem]:
        results = await self._provider.search_web(query, include_domains, limit)
        return [
            CollectedItem(
                signal_type=SIGNAL_WEB,
                text=r["title"],
                url=r["url"],
                summary=r["description"],
                provider="contextdev",
            )
            for r in results
        ]


class SerperWebSource:
    """Backup for when context.dev is not configured: ordinary web search through Serper. A domain
    limit becomes a `site:` operator. Results are undated unless Serper returns a date."""

    def __init__(self, serper: SerperSearchProvider) -> None:
        self._serper = serper

    async def search(
        self, query: str, include_domains: list[str] | None, limit: int
    ) -> list[CollectedItem]:
        scope = " OR ".join(f"site:{d}" for d in include_domains or [])
        hits = await self._serper.search_raw(f"{query} ({scope})" if scope else query, limit)
        items: list[CollectedItem] = []
        for hit in hits:
            title = (hit.get("title") or "").strip()
            if not title:
                continue
            items.append(
                CollectedItem(
                    signal_type=SIGNAL_WEB,
                    text=title,
                    url=hit.get("link"),
                    date=hit.get("date"),
                    summary=(hit.get("snippet") or "").strip() or None,
                    provider="serper",
                )
            )
        return items


class SerperNewsSource:
    """News through Serper: the backup when context.dev is not set up or is refusing requests."""

    def __init__(self, serper: SerperSearchProvider) -> None:
        self._serper = serper

    async def search(self, query: str, since: datetime, limit: int) -> list[CollectedItem]:
        hits = await self._serper.search_news_raw(query, limit)
        return [
            CollectedItem(
                signal_type=SIGNAL_NEWS,
                text=(hit.get("title") or "").strip(),
                url=hit.get("link"),
                date=hit.get("date"),
                summary=(hit.get("snippet") or "").strip() or None,
                provider="serper",
            )
            for hit in hits
            if (hit.get("title") or "").strip()
        ]


class FallbackNewsSource:
    """Tries the first source and, when it fails or finds nothing, the second."""

    def __init__(self, primary: Any, backup: Any) -> None:
        self._primary, self._backup = primary, backup

    async def search(self, query: str, since: datetime, limit: int) -> list[CollectedItem]:
        try:
            found = await self._primary.search(query, since, limit)
        except Exception as exc:  # noqa: BLE001 - the backup is the point of this class
            logger.info("news source failed, using the backup: %s", exc)
            found = []
        return found or await self._backup.search(query, since, limit)

    async def by_domain(self, domain: str, since: datetime, limit: int) -> list[CollectedItem]:
        try:
            found = await self._primary.by_domain(domain, since, limit)
        except Exception as exc:  # noqa: BLE001
            logger.info("news by website failed, using the backup: %s", exc)
            found = []
        return found


class FallbackWebSource:
    """Tries the first web search and, when it fails (for example a rate limit) or finds nothing,
    the second."""

    def __init__(self, primary: Any, backup: Any) -> None:
        self._primary, self._backup = primary, backup

    async def search(
        self, query: str, include_domains: list[str] | None, limit: int
    ) -> list[CollectedItem]:
        try:
            found = await self._primary.search(query, include_domains, limit)
        except Exception as exc:  # noqa: BLE001 - the backup is the point of this class
            logger.info("web search failed, using the backup: %s", exc)
            found = []
        return found or await self._backup.search(query, include_domains, limit)


class JobBoardHiringSource:
    """Finds the company's job board from links on its own careers page and reads its public
    postings. LinkedIn and other sites whose terms forbid automated reading are never used. When
    the careers page links to no supported board, the result says so (`board` is None)."""

    def __init__(self, scraper: WebsiteScraperProvider, client: httpx.AsyncClient) -> None:
        self._scraper = scraper
        self._client = client

    async def _find_board(self, domain: str) -> tuple[Board | None, list[str]]:
        searched: list[str] = []
        for path in _CAREERS_PATHS:
            page = await self._scraper.fetch_page(domain, path)
            searched.append(f"{domain}{path}")
            if page is None:
                continue
            board = find_board(page.text)
            if board is not None:
                return board, searched
        return None, searched

    async def postings(self, domain: str) -> HiringResult:
        board, searched = await self._find_board(domain)
        if board is None:
            return HiringResult(postings=[], board=None, searched=searched)
        searched.append(f"{board.kind} job board")
        try:
            response = await self._client.get(board.url, timeout=_BOARD_TIMEOUT)
            response.raise_for_status()
            body: Any = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.info("job board %s failed: %s", board.label, exc)
            return HiringResult(
                postings=[],
                board=board.label,
                searched=searched,
                error=f"the {board.kind} job board could not be read",
            )
        return HiringResult(postings=parse_board(board, body), board=board.label, searched=searched)


def build_research_sources(
    settings: Settings, scraper: WebsiteScraperProvider
) -> tuple[ResearchSources, list[Any]]:
    """The real sources, plus the things the caller must close when done. context.dev is used for
    news and web search when a key is set; without one, web search falls back to Serper and news
    is simply not searched (reported as such)."""
    contextdev = ContextDevProvider(settings)
    http = httpx.AsyncClient(headers={"User-Agent": settings.scraper_user_agent})
    sources = ResearchSources(hiring=JobBoardHiringSource(scraper, http))
    serper = SerperSearchProvider(settings) if settings.serper_api_key else None
    if contextdev.enabled:
        sources.news = ContextDevNewsSource(contextdev)
        sources.web = ContextDevWebSource(contextdev)
        if serper is not None:
            # context.dev can refuse requests (rate limit, credits); Serper then covers.
            sources.news = FallbackNewsSource(sources.news, SerperNewsSource(serper))
            sources.web = FallbackWebSource(sources.web, SerperWebSource(serper))
    elif serper is not None:
        sources.web = SerperWebSource(serper)
        sources.news = SerperNewsSource(serper)
    return sources, [http]
