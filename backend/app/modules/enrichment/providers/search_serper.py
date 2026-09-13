import logging

import httpx

from app.core.config import Settings
from app.modules.companies.service import is_denylisted_domain, normalize_domain
from app.modules.enrichment.providers.base import (
    CompanyDiscoveryProvider,
    DomainDiscoveryProvider,
    DomainMatch,
)

logger = logging.getLogger(__name__)

_ENDPOINT = "https://google.serper.dev/search"


class SerperSearchProvider(DomainDiscoveryProvider, CompanyDiscoveryProvider):
    """Domain discovery via the Serper.dev API (wraps real Google search results, free tier: no
    card required). A result is always returned as `confidence="fuzzy"` — a search hit is never
    treated as a confirmed match, only a lead worth flagging for review."""

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.serper_api_key
        self._domain_denylist = settings.market_discovery_domain_denylist

    async def _search(self, query: str, num: int) -> list[dict[str, str]]:
        if not self._api_key:
            logger.info("serper search skipped for %r: no API key configured", query)
            return []

        headers = {"X-API-KEY": self._api_key, "Content-Type": "application/json"}
        payload = {"q": query, "num": num}
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(_ENDPOINT, headers=headers, json=payload)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.info("serper search failed for %r: %s", query, exc)
                return []

        organic = resp.json().get("organic") or []
        return [item for item in organic if isinstance(item, dict)]

    async def find_domain(self, company_name: str) -> DomainMatch | None:
        results = await self._search(f"{company_name} official website", num=1)
        if not results:
            return None
        link = results[0].get("link")
        domain = normalize_domain(link) if link else None
        if not domain:
            return None
        return DomainMatch(domain=domain, confidence="fuzzy")

    async def search_raw(self, query: str, num: int) -> list[dict[str, str]]:
        """Public entrypoint for callers that need raw title/link/snippet search results rather
        than resolved+denylist-filtered candidate domains — used by the discovery agent's
        `SearchGatherer`, which does its own interpretation of what a result means."""
        return await self._search(query, num)

    async def find_candidates(self, query: str, limit: int = 10) -> list[DomainMatch]:
        results = await self._search(query, num=limit)
        candidates: list[DomainMatch] = []
        seen_domains: set[str] = set()
        for item in results:
            domain = normalize_domain(item.get("link"))
            if not domain or domain in seen_domains:
                continue
            if is_denylisted_domain(domain, self._domain_denylist):
                continue
            seen_domains.add(domain)
            candidates.append(
                DomainMatch(domain=domain, confidence="fuzzy", title=item.get("title"))
            )
        return candidates
