import httpx

from app.core.config import Settings
from app.modules.enrichment.providers.search_google import GoogleCustomSearchProvider


def _settings() -> Settings:
    return Settings(google_search_api_key="key", google_search_engine_id="cx")


async def test_find_candidates_dedupes_by_domain_and_returns_fuzzy_matches(monkeypatch) -> None:
    async def fake_get(self, url, params=None, **kwargs):
        return httpx.Response(
            200,
            json={
                "items": [
                    {"link": "https://acme.com/about", "title": "Acme Inc"},
                    {"link": "https://acme.com/", "title": "Acme Inc Home"},  # same domain
                    {"link": "https://globex.com", "title": "Globex Corp"},
                ]
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    provider = GoogleCustomSearchProvider(_settings())
    candidates = await provider.find_candidates("SaaS companies in Bangalore", limit=10)

    assert [c.domain for c in candidates] == ["acme.com", "globex.com"]
    assert all(c.confidence == "fuzzy" for c in candidates)
    assert candidates[0].title == "Acme Inc"


async def test_find_candidates_returns_empty_without_api_key() -> None:
    provider = GoogleCustomSearchProvider(Settings())
    assert await provider.find_candidates("query") == []


async def test_find_candidates_returns_empty_on_request_failure(monkeypatch) -> None:
    async def fake_get(self, url, params=None, **kwargs):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    provider = GoogleCustomSearchProvider(_settings())
    assert await provider.find_candidates("query") == []
