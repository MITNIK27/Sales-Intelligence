"""What the company is doing lately, for a Quick Look: recent news, open jobs, and a search for
their work in the areas we sell in. Every source is best-effort and time-boxed: one that is not set
up, is slow or fails only adds a plain note, and never stops the look-up."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.modules.enrichment.signals import looks_blocked
from app.modules.opportunity.research.types import ResearchSources
from app.modules.quicklook.snapshot import KIND_HIRING, KIND_NEWS, KIND_SEARCH, Evidence

logger = logging.getLogger(__name__)

NEWS_DAYS = 365
NEWS_ITEMS = 5
HIRING_ITEMS = 5
WEB_ITEMS = 5
AREA_TAGS_IN_QUERY = 4
NEWS_WEB_TIMEOUT = 15.0
HIRING_TIMEOUT = 20.0


def _text(title: str | None, summary: str | None) -> str:
    return f"{(title or '').strip()}. {(summary or '').strip()}".strip(". ").strip()


async def _news(
    sources: ResearchSources, name: str, domain: str, now: datetime
) -> tuple[list[Evidence], list[str]]:
    if sources.news is None:
        return [], ["Recent news was not searched (news search is not set up)."]
    since = now - timedelta(days=NEWS_DAYS)
    try:
        # By website when the source can (news about this company, not others sharing its name),
        # then by name.
        by_domain = getattr(sources.news, "by_domain", None)
        items = []
        if by_domain is not None:
            items = await asyncio.wait_for(by_domain(domain, since, NEWS_ITEMS), NEWS_WEB_TIMEOUT)
        if not items:
            items = await asyncio.wait_for(
                sources.news.search(f'"{name}"', since, NEWS_ITEMS), NEWS_WEB_TIMEOUT
            )
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.info("quick look news failed for %s: %s", name, exc)
        return [], ["Recent news could not be searched just now."]
    found = [
        Evidence("", i.url or name, KIND_NEWS, _text(i.text, i.summary), i.date)
        for i in items
        if i.text and not looks_blocked(i.text)
    ]
    return found, []


async def _hiring(sources: ResearchSources, domain: str) -> tuple[list[Evidence], list[str]]:
    if sources.hiring is None:
        return [], []
    try:
        result = await asyncio.wait_for(sources.hiring.postings(domain), HIRING_TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.info("quick look hiring failed for %s: %s", domain, exc)
        return [], ["Their open jobs could not be checked just now."]
    notes = [f"Open jobs: {result.error}."] if result.error else []
    found: list[Evidence] = []
    for posting in result.postings[:HIRING_ITEMS]:
        where = ", ".join(x for x in (posting.department, posting.location) if x)
        detail = f" ({where})" if where else ""
        text = f"Open role: {posting.title}{detail}. {posting.excerpt[:200]}".strip()
        found.append(Evidence("", posting.url or domain, KIND_HIRING, text, posting.posted))
    return found, notes


async def _related_work(
    sources: ResearchSources, name: str, area_tags: list[str]
) -> tuple[list[Evidence], list[str]]:
    """A search for the company together with the areas we sell in, to find what they are building
    or buying there."""
    if sources.web is None:
        return [], []
    tags = " ".join(area_tags[:AREA_TAGS_IN_QUERY]) or "technology"
    try:
        items = await asyncio.wait_for(
            sources.web.search(f"{name} {tags}", None, WEB_ITEMS), NEWS_WEB_TIMEOUT
        )
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.info("quick look related-work search failed for %s: %s", name, exc)
        return [], []
    found = [
        Evidence("", i.url or name, KIND_SEARCH, _text(i.text, i.summary), i.date)
        for i in items
        if i.summary and not looks_blocked(i.summary)
    ]
    return found, []


async def gather_research(
    sources: ResearchSources,
    name: str,
    domain: str,
    area_tags: list[str],
    now: datetime | None = None,
) -> tuple[list[Evidence], list[str]]:
    """News, open jobs and related-work results, searched at the same time."""
    moment = now or datetime.now(UTC)
    parts: list[tuple[list[Evidence], list[str]]] = await asyncio.gather(
        _news(sources, name, domain, moment),
        _hiring(sources, domain),
        _related_work(sources, name, area_tags),
    )
    evidence: list[Evidence] = []
    notes: list[str] = []
    for found, part_notes in parts:
        evidence.extend(found)
        notes.extend(part_notes)
    return evidence, notes
