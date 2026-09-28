import pytest

from app.modules.discovery_agent.agent import CompanyDiscoveryAgent, DiscoveryAgentError
from app.modules.discovery_agent.schemas import (
    DiscoveredCompany,
    ExtractedCompany,
    MarketCriteria,
    RawSearchResult,
)

_CRITERIA = MarketCriteria(industry_keywords=["postal", "parcel"], location="Europe")


class _StubGatherer:
    def __init__(
        self, results: list[RawSearchResult] | None = None, exc: Exception | None = None
    ) -> None:
        self._results = results or []
        self._exc = exc

    async def gather(self, criteria: MarketCriteria) -> list[RawSearchResult]:
        if self._exc:
            raise self._exc
        return self._results


class _StubExtractionModel:
    def __init__(
        self, extracted: list[ExtractedCompany] | None = None, exc: Exception | None = None
    ) -> None:
        self._extracted = extracted or []
        self._exc = exc

    async def extract(
        self, criteria: MarketCriteria, search_results: list[RawSearchResult]
    ) -> list[ExtractedCompany]:
        if self._exc:
            raise self._exc
        return self._extracted


class _StubResolver:
    def __init__(
        self, resolved: list[DiscoveredCompany] | None = None, exc: Exception | None = None
    ) -> None:
        self._resolved = resolved or []
        self._exc = exc

    async def resolve(self, extracted: list[ExtractedCompany]) -> list[DiscoveredCompany]:
        if self._exc:
            raise self._exc
        return self._resolved


class _CapturingResolver:
    """Records exactly what it was asked to resolve, so a test can assert on the accepted list's
    contents (e.g. `needs_review` flags) rather than only on the resolver's canned output."""

    def __init__(self, resolved: list[DiscoveredCompany] | None = None) -> None:
        self.received: list[ExtractedCompany] = []
        self._resolved = resolved or []

    async def resolve(self, extracted: list[ExtractedCompany]) -> list[DiscoveredCompany]:
        self.received = list(extracted)
        return self._resolved


def _extracted(name: str, accepted: bool = True) -> ExtractedCompany:
    return ExtractedCompany(
        name=name,
        source_snippet="s",
        grounded_in_source=accepted,
        matches_criteria=accepted,
        reasoning="r",
    )


async def test_discover_happy_path_returns_capped_companies_with_stats() -> None:
    raw = [RawSearchResult(title="t", link="l", snippet="s")]
    extracted = [_extracted("Acme", accepted=True), _extracted("Reddit", accepted=False)]
    resolved = [DiscoveredCompany(name="Acme", domain="acme.com", source_snippet="s")]

    agent = CompanyDiscoveryAgent(
        _StubGatherer(raw), _StubExtractionModel(extracted), _StubResolver(resolved)
    )
    result = await agent.discover(_CRITERIA, limit=10)

    assert result.companies == resolved
    assert result.raw_results_count == 1
    assert result.extracted_count == 2
    assert result.accepted_count == 1
    assert result.resolved_count == 1
    assert [r.name for r in result.rejected] == ["Reddit"]


async def test_discover_caps_at_limit() -> None:
    resolved = [
        DiscoveredCompany(name=f"Co {i}", domain=f"co{i}.com", source_snippet="s")
        for i in range(5)
    ]
    agent = CompanyDiscoveryAgent(
        _StubGatherer([]), _StubExtractionModel([]), _StubResolver(resolved)
    )
    result = await agent.discover(_CRITERIA, limit=2)

    assert len(result.companies) == 2


async def test_discover_wraps_gatherer_failure() -> None:
    agent = CompanyDiscoveryAgent(
        _StubGatherer(exc=RuntimeError("search API down")),
        _StubExtractionModel([]),
        _StubResolver([]),
    )
    with pytest.raises(DiscoveryAgentError, match="company search failed"):
        await agent.discover(_CRITERIA, limit=10)


async def test_discover_wraps_extraction_failure() -> None:
    agent = CompanyDiscoveryAgent(
        _StubGatherer([]),
        _StubExtractionModel(exc=RuntimeError("model overloaded")),
        _StubResolver([]),
    )
    with pytest.raises(DiscoveryAgentError, match="company extraction failed"):
        await agent.discover(_CRITERIA, limit=10)


async def test_discover_overrides_llm_accept_for_confident_listicle_title() -> None:
    """The extraction prompt already tells the model not to treat a listicle as a company, but
    that's the model's own self-report — this proves the deterministic backstop in `agent.py`
    (`heuristics.classify_candidate_name`) actually overrides an LLM `accepted=True` verdict
    rather than just documenting the intent."""
    extracted = [_extracted("Top 10 Courier Companies", accepted=True)]
    resolver = _CapturingResolver([])
    agent = CompanyDiscoveryAgent(_StubGatherer([]), _StubExtractionModel(extracted), resolver)

    result = await agent.discover(_CRITERIA, limit=10)

    assert result.accepted_count == 0
    assert resolver.received == []
    assert [r.name for r in result.rejected] == ["Top 10 Courier Companies"]
    assert result.rejected[0].accepted is False


async def test_discover_flags_but_keeps_structurally_suspicious_candidate() -> None:
    extracted = [_extracted("Best Logistics Companies in 2026", accepted=True)]
    resolver = _CapturingResolver([])
    agent = CompanyDiscoveryAgent(_StubGatherer([]), _StubExtractionModel(extracted), resolver)

    result = await agent.discover(_CRITERIA, limit=10)

    assert result.accepted_count == 1
    assert len(resolver.received) == 1
    flagged = resolver.received[0]
    assert flagged.needs_review is True
    assert flagged.needs_review_reason is not None


async def test_discover_wraps_resolution_failure() -> None:
    agent = CompanyDiscoveryAgent(
        _StubGatherer([]),
        _StubExtractionModel([_extracted("Acme")]),
        _StubResolver(exc=RuntimeError("resolution timeout")),
    )
    with pytest.raises(DiscoveryAgentError, match="domain resolution failed"):
        await agent.discover(_CRITERIA, limit=10)
