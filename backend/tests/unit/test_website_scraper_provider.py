import httpx

from app.core.config import Settings
from app.modules.enrichment.providers.website_scraper import WebsiteScraperProvider


def _settings() -> Settings:
    return Settings(scraper_user_agent="TestBot/1.0", scraper_request_delay_seconds=0.0)


def _provider_with_transport(handler) -> WebsiteScraperProvider:
    provider = WebsiteScraperProvider(_settings())
    provider._client = httpx.AsyncClient(  # noqa: SLF001 - test wiring a fake transport
        transport=httpx.MockTransport(handler), headers={"User-Agent": "TestBot/1.0"}
    )
    return provider


async def test_robots_txt_disallowed_path_is_skipped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /team\n")
        if request.url.path == "/":
            return httpx.Response(200, text="<html><body>home</body></html>")
        if request.url.path == "/team":
            return httpx.Response(200, text="<html><body>team</body></html>")
        return httpx.Response(404)

    provider = _provider_with_transport(handler)
    try:
        data = await provider.fetch_company_data("example.com")
    finally:
        await provider.aclose()

    fetched_paths = {page.url for page in data.pages_fetched}
    assert "https://example.com/" in fetched_paths
    assert "https://example.com/team" not in fetched_paths


async def test_fetches_homepage_and_up_to_two_about_pages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)  # no robots.txt -> allow everything
        if request.url.path in ("/", "/about", "/about-us"):
            return httpx.Response(200, text=f"<html><body>{request.url.path}</body></html>")
        return httpx.Response(404)

    provider = _provider_with_transport(handler)
    try:
        data = await provider.fetch_company_data("example.com")
    finally:
        await provider.aclose()

    assert len(data.pages_fetched) == 3  # homepage + first 2 successful candidate paths


async def test_no_homepage_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    provider = _provider_with_transport(handler)
    try:
        raised = False
        try:
            await provider.fetch_company_data("example.com")
        except ValueError:
            raised = True
        assert raised
    finally:
        await provider.aclose()
