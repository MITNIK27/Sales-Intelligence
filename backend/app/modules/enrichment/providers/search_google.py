import logging

import httpx

from app.core.config import Settings
from app.modules.companies.service import normalize_domain
from app.modules.enrichment.providers.base import (
    CompanyDiscoveryProvider,
    DomainDiscoveryProvider,
    DomainMatch,
)

logger = logging.getLogger(__name__)

_ENDPOINT = "https://www.googleapis.com/customsearch/v1"


class GoogleCustomSearchProvider(DomainDiscoveryProvider, CompanyDiscoveryProvider):
    """Domain discovery via the Google Custom Search JSON API (free tier: 100 queries/day).
    A result is always returned as `confidence="fuzzy"` — a search hit is never treated as a
    confirmed match, only a lead worth flagging for review."""

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.google_search_api_key
        self._engine_id = settings.google_search_engine_id

    async def find_domain(self, company_name: str) -> DomainMatch | None:
        if not self._api_key or not self._engine_id:
            return None

        params: dict[str, str | int] = {
            "key": self._api_key,
            "cx": self._engine_id,
            "q": f"{company_name} official website",
            "num": 1,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(_ENDPOINT, params=params)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.info("google custom search failed for %r: %s", company_name, exc)
                return None

        items = resp.json().get("items") or []
        if not items:
            return None
        link = items[0].get("link")
        domain = normalize_domain(link) if link else None
        if not domain:
            return None
        return DomainMatch(domain=domain, confidence="fuzzy")

    async def find_candidates(self, query: str, limit: int = 10) -> list[DomainMatch]:
        if not self._api_key or not self._engine_id:
            return []

        params: dict[str, str | int] = {
            "key": self._api_key,
            "cx": self._engine_id,
            "q": query,
            "num": min(limit, 10),  # Custom Search's per-request max
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(_ENDPOINT, params=params)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.info("google custom search candidates failed for %r: %s", query, exc)
                return []

        items = resp.json().get("items") or []
        candidates: list[DomainMatch] = []
        seen_domains: set[str] = set()
        for item in items:
            domain = normalize_domain(item.get("link"))
            if not domain or domain in seen_domains:
                continue
            seen_domains.add(domain)
            candidates.append(
                DomainMatch(domain=domain, confidence="fuzzy", title=item.get("title"))
            )
        return candidates
