from app.modules.discovery_agent.schemas import MarketCriteria
from app.modules.discovery_agent.search_gatherer import SearchGatherer


async def test_gather_issues_multiple_query_variants_and_dedupes_by_link() -> None:
    calls: list[tuple[str, int]] = []

    async def fake_search(query: str, num: int) -> list[dict[str, str]]:
        calls.append((query, num))
        return [
            {"title": "Result for " + query, "link": "https://acme.com", "snippet": "s"},
            {"title": "Dup", "link": "https://acme.com", "snippet": "s2"},  # same link, dropped
        ]

    gatherer = SearchGatherer(fake_search, results_per_query=5)
    criteria = MarketCriteria(industry_keywords=["SaaS", "fintech"], location="Bangalore")

    results = await gatherer.gather(criteria)

    assert len(calls) >= 2  # multiple query variants issued
    assert all(num == 5 for _, num in calls)
    assert all("SaaS fintech" in query and "Bangalore" in query for query, _ in calls)
    # deduped across all variants down to the one unique link
    assert len(results) == 1
    assert results[0].link == "https://acme.com"


async def test_gather_handles_missing_location_and_keywords() -> None:
    async def fake_search(query: str, num: int) -> list[dict[str, str]]:
        return []

    gatherer = SearchGatherer(fake_search)
    criteria = MarketCriteria(industry_keywords=[], location=None)

    results = await gatherer.gather(criteria)

    assert results == []


async def test_gather_skips_results_with_no_link() -> None:
    async def fake_search(query: str, num: int) -> list[dict[str, str]]:
        return [{"title": "No link here"}]

    gatherer = SearchGatherer(fake_search)
    results = await gatherer.gather(MarketCriteria(industry_keywords=["SaaS"]))

    assert results == []
