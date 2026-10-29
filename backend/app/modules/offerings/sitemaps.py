"""Reads a site's XML sitemap directly (a free, plain HTTP fetch) for each page's address and its
`lastmod`, the time the site says the page last changed. That time is what lets a later sync skip
a page that has not moved, without scraping it or calling a model."""

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from app.modules.offerings.retry import with_retries

logger = logging.getLogger(__name__)

# A sitemap index can point at other sitemaps; a couple of levels is plenty and stops a loop.
_MAX_DEPTH = 2


@dataclass(frozen=True)
class SitemapEntry:
    url: str
    lastmod: datetime | None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_lastmod(text: str | None) -> datetime | None:
    """A sitemap timestamp as an aware UTC datetime; `None` when absent or unreadable."""
    if not text or not text.strip():
        return None
    try:
        parsed = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_sitemap(xml_text: str) -> tuple[list[SitemapEntry], list[str]]:
    """(page entries, child sitemap addresses). Only a page's own `<loc>` counts: the image
    entries nested inside it carry a `<loc>` too and are not pages."""
    root = ET.fromstring(xml_text)  # noqa: S314 - the organisation's own sitemap, not user input
    entries: list[SitemapEntry] = []
    children: list[str] = []
    for item in root:
        kind = _local(item.tag)
        if kind not in ("url", "sitemap"):
            continue
        loc = next((c.text for c in item if _local(c.tag) == "loc" and c.text), None)
        if not loc:
            continue
        if kind == "sitemap":
            children.append(loc.strip())
            continue
        lastmod = next((c.text for c in item if _local(c.tag) == "lastmod"), None)
        entries.append(SitemapEntry(url=loc.strip(), lastmod=parse_lastmod(lastmod)))
    return entries, children


async def read_sitemap(
    url: str, user_agent: str = "SalesIntelligenceBot/0.1", _depth: int = 0
) -> list[SitemapEntry]:
    """Every page in a sitemap (following an index into its children). Raises
    `httpx.HTTPError` or `ET.ParseError` when the top-level sitemap cannot be read; a broken
    child is logged and skipped so one bad file does not lose the rest."""
    async def fetch() -> httpx.Response:
        async with httpx.AsyncClient(
            headers={"User-Agent": user_agent}, timeout=20.0, follow_redirects=True
        ) as client:
            return await client.get(url)

    resp = await with_retries(fetch, f"reading sitemap {url}")
    resp.raise_for_status()
    entries, children = parse_sitemap(resp.text)
    if _depth < _MAX_DEPTH:
        for child in children:
            try:
                entries.extend(await read_sitemap(child, user_agent, _depth + 1))
            except (httpx.HTTPError, ET.ParseError) as exc:
                logger.warning("could not read child sitemap %s: %s", child, exc)
    return entries
