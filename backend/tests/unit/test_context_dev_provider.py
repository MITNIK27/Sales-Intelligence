import httpx
import pytest

from app.core.config import Settings
from app.modules.enrichment.providers.base import (
    FetchedPage,
    ScrapedCompanyData,
    ScrapedSignal,
)
from app.modules.enrichment.providers.context_dev import ContextDevProvider
from app.modules.enrichment.providers.factory import (
    ScraperFirstSignalProvider,
    ScraperWithContextDevFallback,
    build_company_providers,
)
from app.modules.enrichment.providers.website_scraper import WebsiteScraperProvider

_BRAND = {
    "domain": "acme.com",
    "description": "Acme makes parcel lockers.",
    "employees": {"range": "51-200", "exact": 120},
    "industries": {"eic": [{"industry": "Logistics", "subindustry": "Parcel"}]},
    "socials": [{"type": "linkedin", "url": "https://linkedin.com/company/acme"}],
}
_HOME_HTML = "<html><body><h1>Acme</h1></body></html>"


def _settings(**overrides) -> Settings:
    return Settings(context_dev_api_key="key", **overrides)


def _router(monkeypatch, routes: dict[str, httpx.Response | Exception]) -> list[str]:
    """Patch AsyncClient.post to answer by URL suffix; returns the list of called paths."""
    called: list[str] = []

    async def fake_post(self, url, headers=None, json=None, **kwargs):
        path = url.removeprefix("https://api.context.dev/v1")
        called.append(path)
        outcome = routes.get(path, httpx.Response(404))
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(
            outcome.status_code, json=outcome.json() if outcome.content else None,
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return called


def _json(status: int, body: dict) -> httpx.Response:
    return httpx.Response(status, json=body)


def _scrape_ok(html: str) -> httpx.Response:
    return _json(200, {"html": {"requested": True, "success": True, "data": html}})


async def test_fetch_company_data_maps_brand_and_pages(monkeypatch) -> None:
    called = _router(
        monkeypatch,
        {
            "/brand/retrieve": _json(
                200, {**_BRAND, "key_metadata": {"credits_consumed": 10}}
            ),
            "/web/scrape": _scrape_ok(_HOME_HTML),
        },
    )
    provider = ContextDevProvider(_settings())

    data = await provider.fetch_company_data("acme.com")

    assert data.description == "Acme makes parcel lockers."
    assert data.industry == "Logistics"
    assert data.employee_count_range == "51-200"
    assert data.raw_brand is not None and data.raw_brand["socials"]
    assert data.source_label == "contextdev:scrape"
    assert len(data.pages_fetched) == 3  # homepage + /about + /team all return the stub
    assert called[0] == "/brand/retrieve"
    assert provider.credits_used == 10


async def test_brand_accepts_wrapped_response_and_exact_employee_count(monkeypatch) -> None:
    wrapped = {"brand": {"description": "d", "employees": {"exact": 42}}}
    _router(monkeypatch, {"/brand/retrieve": _json(200, wrapped)})
    data = await ContextDevProvider(_settings()).fetch_brand("acme.com")
    assert data.description == "d"
    assert data.employee_count_range == "42"
    assert data.industry is None


async def test_brand_404_is_empty_not_an_error(monkeypatch) -> None:
    _router(monkeypatch, {})
    data = await ContextDevProvider(_settings()).fetch_brand("nobody.example")
    assert data.raw_brand is None and data.description is None


async def test_description_falls_back_to_homepage_when_brand_has_none(monkeypatch) -> None:
    html = "<html><head><meta name='description' content='From the meta tag'></head></html>"
    _router(
        monkeypatch,
        {"/brand/retrieve": _json(200, {"domain": "acme.com"}), "/web/scrape": _scrape_ok(html)},
    )
    data = await ContextDevProvider(_settings()).fetch_company_data("acme.com")
    assert data.description == "From the meta tag"


async def test_everything_failing_raises(monkeypatch) -> None:
    _router(
        monkeypatch,
        {
            "/brand/retrieve": httpx.Response(500),
            "/web/scrape": httpx.Response(500),
        },
    )
    with pytest.raises(ValueError, match="no data"):
        await ContextDevProvider(_settings()).fetch_company_data("acme.com")


async def test_missing_key_returns_empty_without_calling_api(monkeypatch) -> None:
    called = _router(monkeypatch, {})
    provider = ContextDevProvider(Settings(context_dev_api_key=None))

    data = await provider.fetch_company_data("acme.com")

    assert data.pages_fetched == [] and data.raw_brand is None
    assert await provider.fetch_signals("acme.com") == []
    assert called == []


async def test_fetch_signals_maps_news_articles(monkeypatch) -> None:
    _router(
        monkeypatch,
        {
            "/news/search": _json(
                200,
                {
                    "data": [
                        {
                            "title": "Acme raises Series B",
                            "url": "https://news.example/acme",
                            "published_at": "2026-09-01T00:00:00Z",
                            "source": {"name": "News", "domain": "news.example"},
                        },
                        {"title": "", "url": "https://news.example/blank"},
                    ]
                },
            )
        },
    )
    signals = await ContextDevProvider(_settings()).fetch_signals("acme.com")

    assert len(signals) == 1
    assert signals[0].signal_type == "news"
    assert signals[0].text == "Acme raises Series B"
    assert signals[0].date == "2026-09-01T00:00:00Z"
    assert signals[0].source_label == "contextdev"


async def test_fetch_signals_returns_empty_on_server_error(monkeypatch) -> None:
    _router(monkeypatch, {"/news/search": httpx.Response(500)})
    assert await ContextDevProvider(_settings()).fetch_signals("acme.com") == []


async def test_enrich_person_reports_plan_gated_on_422(monkeypatch) -> None:
    _router(monkeypatch, {"/people/enrich": httpx.Response(422)})
    result = await ContextDevProvider(_settings()).enrich_person("Jane Doe", "acme.com")
    assert result == "plan_gated"


# -- fallback composite ------------------------------------------------------------------------


class _FakeScraper:
    def __init__(self, data: ScrapedCompanyData | Exception) -> None:
        self._data = data

    async def fetch_company_data(self, domain: str) -> ScrapedCompanyData:
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


class _FakeContextDev(ContextDevProvider):
    def __init__(self, brand: ScrapedCompanyData, full: ScrapedCompanyData | Exception) -> None:
        super().__init__(_settings())
        self._brand, self._full = brand, full
        self.calls: list[str] = []

    async def fetch_brand(self, domain: str) -> ScrapedCompanyData:
        self.calls.append("brand")
        return self._brand

    async def fetch_company_data(self, domain: str) -> ScrapedCompanyData:
        self.calls.append("full")
        if isinstance(self._full, Exception):
            raise self._full
        return self._full


_PAGE = FetchedPage(url="https://acme.com/", status_code=200, text="<html></html>")
_LONG = "Acme runs parcel and freight networks across Europe, serving retailers and shippers."


async def test_fallback_tops_up_industry_without_rescraping_pages() -> None:
    scraper = _FakeScraper(
        ScrapedCompanyData(
            description=_LONG, employee_count_range=None, pages_fetched=[_PAGE]
        )
    )
    contextdev = _FakeContextDev(
        brand=ScrapedCompanyData(
            description="brand desc", industry="Logistics", employee_count_range="51-200",
            raw_brand={"domain": "acme.com"}, source_label="contextdev:brand",
        ),
        full=ValueError("should not be called"),
    )

    data = await ScraperWithContextDevFallback(scraper, contextdev).fetch_company_data("acme.com")

    assert contextdev.calls == ["brand"]
    assert data.industry == "Logistics"
    assert data.description == _LONG  # scraper's real description is kept, brand only fills gaps
    assert data.employee_count_range == "51-200"
    assert data.field_sources == {
        "industry": "contextdev:brand",
        "employee_count_range": "contextdev:brand",
    }
    assert data.pages_fetched == [_PAGE]
    assert data.source_label == "scraper:companysite"
    assert data.raw_brand == {"domain": "acme.com"}


async def test_fallback_skips_contextdev_when_scraper_data_is_complete() -> None:
    complete = ScrapedCompanyData(
        description=_LONG, industry="i", employee_count_range="1-10", pages_fetched=[_PAGE]
    )
    contextdev = _FakeContextDev(ScrapedCompanyData(), ScrapedCompanyData())

    data = await ScraperWithContextDevFallback(
        _FakeScraper(complete), contextdev
    ).fetch_company_data("acme.com")

    assert data is complete
    assert contextdev.calls == []


async def test_fallback_uses_full_contextdev_fetch_when_scraper_raises() -> None:
    full = ScrapedCompanyData(description="recovered", pages_fetched=[_PAGE])
    contextdev = _FakeContextDev(ScrapedCompanyData(), full)

    data = await ScraperWithContextDevFallback(
        _FakeScraper(ValueError("could not fetch homepage for royalmail.com")), contextdev
    ).fetch_company_data("royalmail.com")

    assert contextdev.calls == ["full"]
    assert data is full


async def test_fallback_reraises_when_both_sources_fail() -> None:
    contextdev = _FakeContextDev(ScrapedCompanyData(), ValueError("context.dev returned no data"))
    with pytest.raises(ValueError, match="context.dev returned no data"):
        await ScraperWithContextDevFallback(
            _FakeScraper(ValueError("scraper down")), contextdev
        ).fetch_company_data("x.com")


async def test_fallback_keeps_scraper_result_when_brand_topup_fails() -> None:
    scraped = ScrapedCompanyData(description="d", pages_fetched=[_PAGE])
    contextdev = _FakeContextDev(ScrapedCompanyData(), ScrapedCompanyData())

    async def boom(domain: str) -> ScrapedCompanyData:
        raise httpx.ConnectError("down")

    contextdev.fetch_brand = boom  # type: ignore[method-assign]
    data = await ScraperWithContextDevFallback(
        _FakeScraper(scraped), contextdev
    ).fetch_company_data("acme.com")
    assert data is scraped


class _FakeSignals:
    def __init__(self, result: list[ScrapedSignal] | Exception) -> None:
        self._result = result

    async def fetch_signals(self, domain: str) -> list[ScrapedSignal]:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


async def test_signals_survive_the_primary_provider_failing() -> None:
    sig = ScrapedSignal(signal_type="news", text="Acme wins deal in Spain", url="https://x/1")
    both = ScraperFirstSignalProvider(_FakeSignals(RuntimeError("boom")), _FakeSignals([sig]))
    assert await both.fetch_signals("acme.com") == [sig]


# -- factory ----------------------------------------------------------------------------------


async def test_factory_selects_provider_per_setting() -> None:
    scraper = WebsiteScraperProvider(Settings())
    try:
        # Explicit, not the bare default: a local `.env` may set COMPANY_DATA_SOURCE, and an init
        # kwarg takes priority over the dotenv value.
        default = build_company_providers(_settings(company_data_source="scraper"), scraper)
        assert default.company is scraper and default.signals is scraper

        only = build_company_providers(_settings(company_data_source="contextdev"), scraper)
        assert isinstance(only.company, ContextDevProvider)

        both = build_company_providers(
            _settings(company_data_source="scraper_with_contextdev_fallback"), scraper
        )
        assert isinstance(both.company, ScraperWithContextDevFallback)
        assert isinstance(both.signals, ScraperFirstSignalProvider)

        # No key configured: degrade to the scraper rather than enriching with nothing.
        keyless = build_company_providers(
            Settings(context_dev_api_key=None, company_data_source="contextdev"), scraper
        )
        assert keyless.company is scraper
    finally:
        await scraper.aclose()


async def test_fallback_skips_contextdev_when_description_and_employees_are_enough() -> None:
    # No industry, but a real description plus an employee range is "sufficient": no credits.
    enough = ScrapedCompanyData(
        description=_LONG, employee_count_range="201-500", pages_fetched=[_PAGE]
    )
    contextdev = _FakeContextDev(ScrapedCompanyData(), ScrapedCompanyData())
    fallback = ScraperWithContextDevFallback(_FakeScraper(enough), contextdev)

    assert await fallback.fetch_company_data("acme.com") is enough
    assert contextdev.calls == []
    assert fallback.usage()["skipped_sufficient"] == 1


async def test_fallback_replaces_a_thin_description_and_records_field_sources() -> None:
    thin = ScrapedCompanyData(description="Acme", pages_fetched=[_PAGE])
    contextdev = _FakeContextDev(
        ScrapedCompanyData(
            description="Acme is a pan-European logistics provider with 40 hubs.",
            industry="Logistics",
            source_label="contextdev:brand",
        ),
        ValueError("unused"),
    )

    data = await ScraperWithContextDevFallback(_FakeScraper(thin), contextdev).fetch_company_data(
        "acme.com"
    )

    assert data.description.startswith("Acme is a pan-European")
    assert data.field_sources["description"] == "contextdev:brand"
    assert data.field_sources["industry"] == "contextdev:brand"


async def test_credit_ceiling_stops_paid_calls_and_the_run_keeps_scraper_data() -> None:
    contextdev = ContextDevProvider(_settings(context_dev_max_credits_per_run=5))
    thin = ScrapedCompanyData(description="Acme", pages_fetched=[_PAGE])

    data = await ScraperWithContextDevFallback(_FakeScraper(thin), contextdev).fetch_company_data(
        "acme.com"
    )

    assert data is thin  # brand costs 10 > ceiling 5: the paid call was never made
    assert contextdev.credits_used == 0
    assert contextdev.usage()["budget_exhausted"] is True


async def test_paid_signals_are_skipped_when_the_scraper_found_enough_real_ones() -> None:
    real = [
        ScrapedSignal(signal_type="news", text="Acme opens a new automated hub", url="u1"),
        ScrapedSignal(signal_type="news", text="Acme signs a five year deal", url="u2"),
    ]
    paid = _FakeSignals(RuntimeError("must not be called"))
    assert await ScraperFirstSignalProvider(_FakeSignals(real), paid).fetch_signals("a.com") == real


async def test_paid_signals_fill_in_when_the_scraper_found_only_navigation_text() -> None:
    nav = [
        ScrapedSignal(signal_type="news", text="Track shipment", url="u1"),
        ScrapedSignal(signal_type="news", text="Go to homepage", url="u2"),
    ]
    real = ScrapedSignal(signal_type="news", text="Acme opens a new hub in Lyon", url="u3")
    out = await ScraperFirstSignalProvider(_FakeSignals(nav), _FakeSignals([real])).fetch_signals(
        "a.com"
    )
    assert real in out


async def test_a_400_from_brand_lookup_is_no_data_not_an_error(monkeypatch) -> None:
    _router(monkeypatch, {"/brand/retrieve": httpx.Response(400, text='{"error":"bad domain"}')})
    data = await ContextDevProvider(_settings()).fetch_brand("weird.example")
    assert data.raw_brand is None and data.industry is None
