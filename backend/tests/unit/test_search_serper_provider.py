import httpx

from app.core.config import Settings
from app.modules.enrichment.providers.search_serper import SerperSearchProvider


def _settings() -> Settings:
    return Settings(serper_api_key="key")


async def test_find_candidates_dedupes_by_domain_and_returns_fuzzy_matches(monkeypatch) -> None:
    async def fake_post(self, url, headers=None, json=None, **kwargs):
        return httpx.Response(
            200,
            json={
                "organic": [
                    {"link": "https://acme.com/about", "title": "Acme Inc"},
                    {"link": "https://acme.com/", "title": "Acme Inc Home"},  # same domain
                    {"link": "https://globex.com", "title": "Globex Corp"},
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    provider = SerperSearchProvider(_settings())
    candidates = await provider.find_candidates("SaaS companies in Bangalore", limit=10)

    assert [c.domain for c in candidates] == ["acme.com", "globex.com"]
    assert all(c.confidence == "fuzzy" for c in candidates)
    assert candidates[0].title == "Acme Inc"


async def test_find_candidates_filters_out_denylisted_domains(monkeypatch) -> None:
    async def fake_post(self, url, headers=None, json=None, **kwargs):
        return httpx.Response(
            200,
            json={
                "organic": [
                    {"link": "https://www.linkedin.com/company/acme", "title": "Acme on LinkedIn"},
                    {"link": "https://acme.com", "title": "Acme Inc"},
                    {
                        "link": "https://www.crunchbase.com/organization/acme",
                        "title": "Acme - Crunchbase",
                    },
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    provider = SerperSearchProvider(_settings())
    candidates = await provider.find_candidates("acme company profile", limit=10)

    assert [c.domain for c in candidates] == ["acme.com"]


async def test_find_candidates_returns_empty_without_api_key() -> None:
    # Explicit override, not the bare default: local `.env` may have a real key set, and an
    # init kwarg takes priority over the dotenv value in pydantic-settings' source order.
    provider = SerperSearchProvider(Settings(serper_api_key=None))
    assert await provider.find_candidates("query") == []


async def test_find_candidates_returns_empty_on_request_failure(monkeypatch) -> None:
    async def fake_post(self, url, headers=None, json=None, **kwargs):
        raise httpx.ConnectError("boom", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    provider = SerperSearchProvider(_settings())
    assert await provider.find_candidates("query") == []


async def test_find_domain_returns_normalized_domain(monkeypatch) -> None:
    async def fake_post(self, url, headers=None, json=None, **kwargs):
        return httpx.Response(
            200,
            json={"organic": [{"link": "https://acme.com/about", "title": "Acme Inc"}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    provider = SerperSearchProvider(_settings())
    match = await provider.find_domain("Acme Inc")

    assert match is not None
    assert match.domain == "acme.com"
    assert match.confidence == "fuzzy"


async def test_find_domain_returns_none_without_api_key() -> None:
    provider = SerperSearchProvider(Settings(serper_api_key=None))
    assert await provider.find_domain("Acme Inc") is None


async def test_search_raw_returns_title_link_and_snippet_unfiltered(monkeypatch) -> None:
    async def fake_post(self, url, headers=None, json=None, **kwargs):
        return httpx.Response(
            200,
            json={
                "organic": [
                    {
                        "link": "https://www.linkedin.com/company/acme",
                        "title": "Acme on LinkedIn",
                        "snippet": "Acme's LinkedIn page.",
                    },
                    {
                        "link": "https://reddit.com/r/logistics/thread1",
                        "title": "Best courier companies?",
                        "snippet": "Acme Parcel and Globex Post are solid options.",
                    },
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    provider = SerperSearchProvider(_settings())
    results = await provider.search_raw("postal parcel companies in Europe", num=10)

    # Unlike find_candidates, search_raw is not domain-filtered/denylisted — the discovery
    # agent's own extraction+resolution stages do that interpretation, not this raw wrapper.
    assert len(results) == 2
    assert results[0]["link"] == "https://www.linkedin.com/company/acme"
    assert results[1]["snippet"] == "Acme Parcel and Globex Post are solid options."
