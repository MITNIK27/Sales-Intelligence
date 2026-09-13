"""In-memory test double for `CompanyDiscoveryAgentProtocol` — no network calls. Lives in the
app tree (not tests/), same convention as `enrichment/providers/mock.py`, so it's importable from
both unit and integration tests without duplicating this shape in each."""

from app.modules.discovery_agent.schemas import DiscoveredCompany, DiscoveryResult, MarketCriteria


class StubCompanyDiscoveryAgent:
    def __init__(self, companies: list[DiscoveredCompany] | None = None) -> None:
        self._companies = companies or []
        # Recorded for tests that want to assert what the caller passed in (criteria, limit),
        # e.g. the compounding-index tests that check the live call shrinks as the index fills.
        self.calls: list[tuple[MarketCriteria, int]] = []

    async def discover(self, criteria: MarketCriteria, limit: int) -> DiscoveryResult:
        self.calls.append((criteria, limit))
        companies = self._companies[:limit]
        return DiscoveryResult(
            companies=companies,
            raw_results_count=len(companies),
            extracted_count=len(companies),
            accepted_count=len(companies),
            resolved_count=len(companies),
            rejected=[],
        )
