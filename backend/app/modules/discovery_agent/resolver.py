"""Resolves accepted extracted company names to domains, reusing the existing precise
per-company domain lookup (`DomainDiscoveryProvider.find_domain`, e.g. `"{name} official
website"`) rather than reinventing search logic. Applies the same denylist used elsewhere as a
backstop, since `find_domain` itself does not filter it out."""

import asyncio

from app.modules.companies.service import is_denylisted_domain
from app.modules.discovery_agent.schemas import DiscoveredCompany, ExtractedCompany
from app.modules.enrichment.providers.base import DomainDiscoveryProvider


class CompanyResolver:
    def __init__(
        self,
        domain_provider: DomainDiscoveryProvider,
        denylist: list[str],
        concurrency: int = 5,
    ) -> None:
        self._domain_provider = domain_provider
        self._denylist = denylist
        self._semaphore = asyncio.Semaphore(concurrency)

    async def resolve(self, extracted: list[ExtractedCompany]) -> list[DiscoveredCompany]:
        resolved_or_none = await asyncio.gather(*(self._resolve_one(e) for e in extracted))

        seen_domains: set[str] = set()
        resolved: list[DiscoveredCompany] = []
        for company in resolved_or_none:
            if company is None or company.domain in seen_domains:
                continue
            seen_domains.add(company.domain)
            resolved.append(company)
        return resolved

    async def _resolve_one(self, extracted: ExtractedCompany) -> DiscoveredCompany | None:
        async with self._semaphore:
            match = await self._domain_provider.find_domain(extracted.name)
        if match is None or is_denylisted_domain(match.domain, self._denylist):
            return None
        return DiscoveredCompany(
            name=extracted.name, domain=match.domain, source_snippet=extracted.source_snippet
        )
