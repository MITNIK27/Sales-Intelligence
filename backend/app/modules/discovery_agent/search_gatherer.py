"""Pure I/O stage: gathers raw web search results across multiple query variants. No
interpretation of what any result means or whether it's a real company — that's `extractor.py`'s
job. Kept deliberately dumb so it's trivial to test and trivial to swap the underlying search
backend without touching anything downstream."""

import asyncio
from collections.abc import Awaitable, Callable

from app.modules.discovery_agent.schemas import MarketCriteria, RawSearchResult

# (query, num_results) -> raw result dicts with "title"/"link"/"snippet" keys, same shape Serper
# returns. Matches `SerperSearchProvider.search_raw`.
RawSearchFn = Callable[[str, int], Awaitable[list[dict[str, str]]]]

# Several angles on the same market, not one query — a single broad query is exactly what
# produced the original bug (one page of mostly-noise results). Most of what these return is
# expected to be filtered out by the extraction stage, not kept.
_QUERY_TEMPLATES = (
    "{keywords} companies{location_suffix}",
    "leading {keywords} companies{location_suffix}",
    "{keywords} industry players{location_suffix}",
)


def _build_queries(criteria: MarketCriteria) -> list[str]:
    keywords = " ".join(criteria.industry_keywords) or "companies"
    location_suffix = f" in {criteria.location}" if criteria.location else ""
    return [
        template.format(keywords=keywords, location_suffix=location_suffix)
        for template in _QUERY_TEMPLATES
    ]


class SearchGatherer:
    def __init__(self, search_fn: RawSearchFn, results_per_query: int = 10) -> None:
        self._search_fn = search_fn
        self._results_per_query = results_per_query

    async def gather(self, criteria: MarketCriteria) -> list[RawSearchResult]:
        queries = _build_queries(criteria)
        batches = await asyncio.gather(
            *(self._search_fn(query, self._results_per_query) for query in queries)
        )

        seen_links: set[str] = set()
        results: list[RawSearchResult] = []
        for batch in batches:
            for item in batch:
                link = item.get("link")
                if not link or link in seen_links:
                    continue
                seen_links.add(link)
                results.append(
                    RawSearchResult(
                        title=item.get("title") or "",
                        link=link,
                        snippet=item.get("snippet") or "",
                    )
                )
        return results
