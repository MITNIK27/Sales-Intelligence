"""Where the importer reads InfoBeans' own website from: context.dev first, the in-house scraper
as the fallback (order set by `OFFERINGS_SOURCE_ORDER`). Both give the same two things — the list
of page URLs, and a page's text — so the importer does not care which one answered."""

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import Settings
from app.modules.enrichment.providers.context_dev import ContextDevProvider
from app.modules.enrichment.providers.website_scraper import WebsiteScraperProvider
from app.modules.offerings.retry import RETRY_WAITS
from app.modules.offerings.sitemaps import SitemapEntry, read_sitemap
from app.modules.offerings.urls import canonical_url

logger = logging.getLogger(__name__)

_MAX_PAGE_CHARS = 20_000


class PageSourceError(RuntimeError):
    """This source could not list or read the site; the fallback chain tries the next one."""


class OfferingPageSource(ABC):
    name: str

    @abstractmethod
    async def list_urls(self) -> list[str]: ...

    @abstractmethod
    async def fetch_text(self, url: str) -> str | None: ...

    async def list_entries(self, sitemap_url: str) -> list[SitemapEntry]:
        """The pages of one sitemap with their last-modified times where the source knows them.
        The default knows only the addresses."""
        return [SitemapEntry(url=u, lastmod=None) for u in await self.list_urls()]

    async def describe(self, sitemap_url: str) -> dict[str, tuple[str | None, str | None]]:
        """address -> (title, description) for a sitemap's pages, when the source can say, so a
        page can be screened without being read. The default knows nothing."""
        return {}

    async def is_gone(self, url: str) -> bool:
        """True only when the site itself says the page no longer exists (404 or 410). The
        default never says so: a page is not called gone on a guess."""
        return False

    async def aclose(self) -> None:  # noqa: B027 - optional hook, nothing to release by default
        return None


async def url_is_gone(url: str, user_agent: str) -> bool:
    """Asks the page itself. Only a 404 or 410 counts; a redirect that lands on a live page, a
    timeout or any other answer means "not shown to be gone"."""
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": user_agent}, timeout=15.0, follow_redirects=True
        ) as client:
            resp = await client.get(url)
    except httpx.HTTPError:
        return False
    return resp.status_code in (404, 410)


def html_to_text(html: str) -> str:
    """Visible text of an HTML page, without scripts, styles and page furniture."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "form", "svg"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)[:_MAX_PAGE_CHARS]


def _path_excluded(url: str, excluded_prefixes: list[str]) -> bool:
    path = urlparse(url).path.rstrip("/") or "/"
    return any(path == p or path.startswith(p) for p in excluded_prefixes)


def filter_offering_urls(urls: list[str], domain: str, excluded_prefixes: list[str]) -> list[str]:
    """Same-site pages worth reading: drops other hosts, the homepage, and the never-an-offering
    paths (news, people, legal, events). Order is kept and duplicates removed."""
    seen: set[str] = set()
    kept: list[str] = []
    for url in urls:
        parsed = urlparse(url)
        host = parsed.netloc.lower().removeprefix("www.")
        if host != domain.lower().removeprefix("www."):
            continue
        if parsed.path.strip("/") == "" or _path_excluded(url, excluded_prefixes):
            continue
        clean = canonical_url(url)
        if clean not in seen:
            seen.add(clean)
            kept.append(clean)
    return kept


class ContextDevPageSource(OfferingPageSource):
    name = "contextdev"

    def __init__(self, settings: Settings) -> None:
        # Its own ceiling, so a sync can never use up the budget meant for discovery runs.
        capped = settings.model_copy(
            update={"context_dev_max_credits_per_run": settings.offerings_context_dev_max_credits}
        )
        self._provider = ContextDevProvider(capped)
        self._settings = settings

    @property
    def credits_used(self) -> int:
        return self._provider.credits_used

    async def _map(self, sitemap_url: str) -> list[dict[str, str | None]]:
        if not self._provider.enabled:
            raise PageSourceError("CONTEXT_DEV_API_KEY is not configured")
        try:
            return await self._provider.map_pages(
                self._settings.offerings_site_domain, sitemap_url=sitemap_url
            )
        except Exception as exc:  # noqa: BLE001 - budget, transport or server error: next source
            raise PageSourceError(f"context.dev could not list the site: {exc}") from exc

    async def list_urls(self) -> list[str]:
        pages = await self._map(self._settings.offerings_sitemap_url)
        return [str(page["url"]) for page in pages]

    async def list_entries(self, sitemap_url: str) -> list[SitemapEntry]:
        pages = await self._map(sitemap_url)
        return [SitemapEntry(url=str(page["url"]), lastmod=None) for page in pages]

    async def describe(self, sitemap_url: str) -> dict[str, tuple[str | None, str | None]]:
        pages = await self._map(sitemap_url)
        return {str(p["url"]): (p.get("title"), p.get("description")) for p in pages}

    async def fetch_text(self, url: str) -> str | None:
        try:
            text = await self._provider.scrape_markdown(url)
        except Exception as exc:  # noqa: BLE001 - e.g. budget reached: let the next source try
            logger.info("context.dev could not read %s: %s", url, exc)
            return None
        return text[:_MAX_PAGE_CHARS] if text else None


class WebsitePageSource(OfferingPageSource):
    """The in-house scraper: robots.txt-respecting, throttled, free."""

    name = "website"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._scraper = WebsiteScraperProvider(settings)

    async def list_entries(self, sitemap_url: str) -> list[SitemapEntry]:
        try:
            return await read_sitemap(sitemap_url, self._settings.scraper_user_agent)
        except (httpx.HTTPError, ET.ParseError) as exc:
            raise PageSourceError(f"could not read the sitemap: {exc}") from exc

    async def list_urls(self) -> list[str]:
        entries = await self.list_entries(self._settings.offerings_sitemap_url)
        return [entry.url for entry in entries]

    async def fetch_text(self, url: str) -> str | None:
        parsed = urlparse(url)
        path = parsed.path or "/"
        for wait in (*RETRY_WAITS, None):
            # The scraper remembers a host as "unreachable" after one network failure, which suits
            # a stranger's slow site but would fail every later page of our own site after one
            # blip. Forget it before each try.
            self._scraper._unreachable.discard(parsed.netloc)  # noqa: SLF001
            page = await self._scraper._fetch(parsed.netloc, path)  # noqa: SLF001
            if page is not None:
                return html_to_text(page.text)
            if parsed.netloc not in self._scraper._unreachable or wait is None:  # noqa: SLF001
                return None  # a real answer (not found, not allowed), or out of attempts
            await asyncio.sleep(wait)
        return None

    async def aclose(self) -> None:
        await self._scraper.aclose()


class FallbackPageSource(OfferingPageSource):
    """Lists the site from the first source that can, and reads each page from the first source
    that can, so one vendor being down or out of credit never stops a sync."""

    name = "fallback"

    def __init__(
        self, sources: list[OfferingPageSource], user_agent: str = "SalesIntelligenceBot/0.1"
    ) -> None:
        self._sources = sources
        self._user_agent = user_agent
        self.list_source: str | None = None
        self.text_sources: set[str] = set()

    async def list_urls(self) -> list[str]:
        errors: list[str] = []
        for source in self._sources:
            try:
                urls = await source.list_urls()
            except PageSourceError as exc:
                errors.append(f"{source.name}: {exc}")
                continue
            if urls:
                self.list_source = source.name
                return urls
            errors.append(f"{source.name}: no pages found")
        raise PageSourceError("; ".join(errors) or "no page source is configured")

    async def list_entries(self, sitemap_url: str) -> list[SitemapEntry]:
        """The sitemap read directly first (free, and the only way to get last-modified times),
        then whichever source can list it."""
        try:
            entries = await read_sitemap(sitemap_url)
        except (httpx.HTTPError, ET.ParseError) as exc:
            logger.info("direct sitemap read failed for %s: %s", sitemap_url, exc)
            entries = []
        if entries:
            self.list_source = "sitemap"
            return entries
        errors: list[str] = []
        for source in self._sources:
            try:
                found = await source.list_entries(sitemap_url)
            except PageSourceError as exc:
                errors.append(f"{source.name}: {exc}")
                continue
            if found:
                self.list_source = source.name
                return found
        raise PageSourceError("; ".join(errors) or "no page source could list the sitemap")

    async def describe(self, sitemap_url: str) -> dict[str, tuple[str | None, str | None]]:
        for source in self._sources:
            try:
                info = await source.describe(sitemap_url)
            except PageSourceError:
                continue
            if info:
                return info
        return {}

    async def is_gone(self, url: str) -> bool:
        return await url_is_gone(url, self._user_agent)

    async def fetch_text(self, url: str) -> str | None:
        for source in self._sources:
            text = await source.fetch_text(url)
            if text:
                self.text_sources.add(source.name)
                return text
        return None

    async def aclose(self) -> None:
        for source in self._sources:
            await source.aclose()

    @property
    def credits_used(self) -> int:
        return sum(getattr(s, "credits_used", 0) for s in self._sources)


def build_page_source(settings: Settings, order: str | None = None) -> FallbackPageSource:
    factories = {"contextdev": ContextDevPageSource, "website": WebsitePageSource}
    names = [n.strip().lower() for n in (order or settings.offerings_source_order).split(",")]
    return FallbackPageSource(
        [factories[n](settings) for n in names if n in factories], settings.scraper_user_agent
    )
