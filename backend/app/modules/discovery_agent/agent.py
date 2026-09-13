"""CompanyDiscoveryAgent — the module's single public interface. Composes gather -> extract ->
resolve -> dedupe/cap, containing any internal failure behind one typed `DiscoveryAgentError` so
`market_discovery.py` (or any future caller) never needs to know which search backend or model
produced a given run, and a failure in one stage can never propagate a partially-broken state
into `IngestionRun`/`Company`. No silent fallback to raw search links on failure — that would
reintroduce the bug this module exists to fix; the caller sees a clear error instead."""

from typing import Protocol

from app.core.config import Settings, get_settings
from app.modules.discovery_agent.extractor import (
    CompanyExtractionModel,
    ExtractionModelError,
    GeminiCompanyExtractionModel,
)
from app.modules.discovery_agent.resolver import CompanyResolver
from app.modules.discovery_agent.schemas import DiscoveryResult, MarketCriteria
from app.modules.discovery_agent.search_gatherer import SearchGatherer


class DiscoveryAgentError(RuntimeError):
    """The one error type this module ever raises to callers."""


class CompanyDiscoveryAgentProtocol(Protocol):
    """Structural interface callers depend on — lets tests inject a stub without inheriting from
    the real `CompanyDiscoveryAgent`, same spirit as the provider ABCs in `enrichment/providers`."""

    async def discover(self, criteria: MarketCriteria, limit: int) -> DiscoveryResult: ...


class CompanyDiscoveryAgent:
    def __init__(
        self,
        gatherer: SearchGatherer,
        extraction_model: CompanyExtractionModel,
        resolver: CompanyResolver,
    ) -> None:
        self._gatherer = gatherer
        self._extraction_model = extraction_model
        self._resolver = resolver

    async def discover(self, criteria: MarketCriteria, limit: int) -> DiscoveryResult:
        try:
            raw_results = await self._gatherer.gather(criteria)
        except Exception as exc:  # noqa: BLE001 - contained behind one typed error, see module docstring
            raise DiscoveryAgentError(f"company search failed: {exc}") from exc

        try:
            extracted = await self._extraction_model.extract(criteria, raw_results)
        except ExtractionModelError as exc:
            raise DiscoveryAgentError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise DiscoveryAgentError(f"company extraction failed: {exc}") from exc

        accepted = [e for e in extracted if e.accepted]
        rejected = [e for e in extracted if not e.accepted]

        try:
            resolved = await self._resolver.resolve(accepted)
        except Exception as exc:  # noqa: BLE001
            raise DiscoveryAgentError(f"domain resolution failed: {exc}") from exc

        return DiscoveryResult(
            companies=resolved[:limit],
            raw_results_count=len(raw_results),
            extracted_count=len(extracted),
            accepted_count=len(accepted),
            resolved_count=len(resolved),
            rejected=rejected,
        )


def _build_extraction_model(settings: Settings) -> CompanyExtractionModel:
    return GeminiCompanyExtractionModel(settings, model=settings.discovery_agent_extraction_model)


def get_default_discovery_agent(settings: Settings | None = None) -> CompanyDiscoveryAgent:
    """Real-provider wiring, mirroring `market_discovery.get_default_market_description_parser`."""
    settings = settings or get_settings()

    # Imported here (not at module top) to keep this module's import graph free of the concrete
    # search provider unless real wiring is actually requested — tests construct
    # `CompanyDiscoveryAgent` directly with fakes and never hit this function.
    from app.modules.enrichment.providers.search_serper import SerperSearchProvider

    search_provider = SerperSearchProvider(settings)
    gatherer = SearchGatherer(
        search_provider.search_raw, results_per_query=settings.discovery_agent_results_per_query
    )
    extraction_model = _build_extraction_model(settings)
    resolver = CompanyResolver(
        search_provider,
        settings.market_discovery_domain_denylist,
        concurrency=settings.discovery_agent_resolution_concurrency,
    )
    return CompanyDiscoveryAgent(gatherer, extraction_model, resolver)
