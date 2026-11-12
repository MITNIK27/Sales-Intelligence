"""context.dev-backed CompanyDataProvider/SignalDataProvider (https://docs.context.dev).

Raw httpx rather than the vendor SDK: matches `search_serper.py`, stays testable with the same
`httpx.AsyncClient.post` monkeypatch, and adds no dependency to a provider that may well be
dropped after evaluation (docs/decisions/0012-context-dev-evaluation.md).

Endpoints used and their documented credit cost: brand/retrieve (10), web/scrape html (1),
news/search (1 per 10 results). people/enrich (20, paid plans only) is exposed separately as
`enrich_person` and is only used by the benchmark script, never by the pipeline."""

import asyncio
import logging
import random
from datetime import datetime
from typing import Any

import httpx

from app.core.config import Settings
from app.modules.enrichment.providers.base import (
    CompanyDataProvider,
    FetchedPage,
    ScrapedCompanyData,
    ScrapedSignal,
    SignalDataProvider,
)
from app.modules.enrichment.providers.website_scraper import (
    extract_description,
    extract_employee_count,
)
from app.modules.usage.recorder import elapsed_ms, record_usage, started

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.context.dev/v1"
SOURCE_LABEL_SCRAPE = "contextdev:scrape"
SOURCE_LABEL_BRAND = "contextdev:brand"
SOURCE_LABEL_NEWS = "contextdev"

# Scraping is billed per page, so only the homepage plus these two about/team candidates are
# tried — fewer than the in-house scraper's list, since each miss on a processed 404 costs credit.
_ABOUT_TEAM_PATHS = ("/about", "/team")
_MAX_NEWS_RESULTS = 10
_DESCRIPTION_MAX = 500
_INDUSTRY_MAX = 255
_EMPLOYEE_RANGE_MAX = 50


_COST_BRAND = 10
_COST_SCRAPE = 1
_COST_NEWS = 1
_COST_MAP = 1
_SCRAPE_ATTEMPTS = 3
_SCRAPE_RETRY_WAIT = 1.0  # seconds, times the attempt number
# A 429 means "too many requests at once" and is not charged: wait as long as the API asks (kept
# within sensible bounds) and try again a few times before giving up.
_RATE_LIMIT_ATTEMPTS = 4
_RATE_LIMIT_MIN_WAIT = 0.5
_RATE_LIMIT_MAX_WAIT = 10.0
_limiters: dict[int, asyncio.Semaphore] = {}


def _limiter(size: int) -> asyncio.Semaphore:
    """One queue per event loop and process, shared by every provider instance, so parallel callers
    (a look-up searching news and the web at once) line up instead of tripping the limit."""
    key = id(asyncio.get_running_loop())
    if key not in _limiters:
        _limiters[key] = asyncio.Semaphore(max(1, size))
    return _limiters[key]


def _retry_wait(resp: httpx.Response) -> float:
    try:
        asked = float(resp.headers.get("retry-after", ""))
    except ValueError:
        asked = 1.0
    return min(max(asked, _RATE_LIMIT_MIN_WAIT), _RATE_LIMIT_MAX_WAIT) + random.uniform(0, 0.4)


def _published_ms(value: str) -> float:
    """When an article was published, in epoch milliseconds; a date that cannot be read counts as
    recent, so an odd format never hides an article."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000
    except ValueError:
        return float("inf")


class ContextDevBudgetExceeded(RuntimeError):
    """The per-run credit ceiling was reached; the paid call was NOT made. Callers treat this as
    "context.dev unavailable for the rest of this run", never as a pipeline failure."""


class ContextDevProvider(CompanyDataProvider, SignalDataProvider):
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.context_dev_api_key
        self._timeout = settings.context_dev_timeout_seconds
        self._ceiling = settings.context_dev_max_credits_per_run
        self._concurrency = settings.context_dev_max_concurrency
        self.budget_exhausted = False
        # Running total of `key_metadata.credits_consumed` across this instance's calls, so the
        # benchmark can report real spend per company rather than an estimate.
        self.credits_used = 0

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def usage(self) -> dict[str, Any]:
        return {
            "credits_used": self.credits_used,
            "credit_ceiling": self._ceiling,
            "budget_exhausted": self.budget_exhausted,
        }

    def _check_budget(self, cost: int) -> None:
        if self.credits_used + cost > self._ceiling:
            self.budget_exhausted = True
            raise ContextDevBudgetExceeded(
                f"context.dev credit ceiling reached ({self.credits_used} of {self._ceiling})"
            )

    async def _send(
        self, path: str, headers: dict[str, str], payload: dict[str, Any]
    ) -> httpx.Response:
        """One request, repeated after the wait the API asks for while it answers 429."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for attempt in range(_RATE_LIMIT_ATTEMPTS):
                resp = await client.post(f"{_BASE_URL}{path}", headers=headers, json=payload)
                if resp.status_code != 429 or attempt + 1 == _RATE_LIMIT_ATTEMPTS:
                    return resp
                wait = _retry_wait(resp)
                logger.info("context.dev %s is rate limited; retrying in %.1fs", path, wait)
                await asyncio.sleep(wait)
        return resp  # pragma: no cover - the loop always returns

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """POST and return the JSON body; `None` for a 404 ("nothing known"). Any other failure
        raises `httpx.HTTPError` — callers decide whether that is fatal."""
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        begin = started()
        async with _limiter(self._concurrency):
            resp = await self._send(path, headers, payload)
        if resp.status_code == 404:
            await record_usage(
                provider="contextdev", kind="credits", units=0, latency_ms=elapsed_ms(begin)
            )
            return None
        if resp.status_code == 400:
            await record_usage(
                provider="contextdev",
                kind="credits",
                status="error",
                units=0,
                latency_ms=elapsed_ms(begin),
            )
            # A rejected request (e.g. a domain the vendor cannot resolve) means "no data", not a
            # provider outage; the body says why, so keep it in the log.
            logger.info("context.dev %s rejected the request: %s", path, resp.text[:200])
            return None
        if resp.status_code >= 400:
            await record_usage(
                provider="contextdev",
                kind="credits",
                status="error",
                units=0,
                latency_ms=elapsed_ms(begin),
            )
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            return None
        credits = (body.get("key_metadata") or {}).get("credits_consumed")
        if isinstance(credits, int):
            self.credits_used += credits
        await record_usage(
            provider="contextdev",
            kind="credits",
            units=credits if isinstance(credits, int) else 0,
            latency_ms=elapsed_ms(begin),
        )
        return body

    # -- company data -------------------------------------------------------------------------

    async def fetch_brand(self, domain: str) -> ScrapedCompanyData:
        """Firmographics only (one 10-credit call, no pages). Empty result when unconfigured or
        unknown; raises on transport/server errors."""
        if not self.enabled:
            logger.info("context.dev brand skipped for %s: no API key configured", domain)
            return ScrapedCompanyData(source_label=SOURCE_LABEL_BRAND)
        self._check_budget(_COST_BRAND)
        body = await self._post("/brand/retrieve", {"domain": domain})
        if body is None:
            return ScrapedCompanyData(source_label=SOURCE_LABEL_BRAND)
        nested = body.get("brand")
        brand: dict[str, Any] = nested if isinstance(nested, dict) else body
        description = brand.get("description")
        return ScrapedCompanyData(
            description=(
                description.strip()[:_DESCRIPTION_MAX]
                if isinstance(description, str) and description.strip()
                else None
            ),
            employee_count_range=_employee_range(brand.get("employees")),
            industry=_industry(brand.get("industries")),
            source_label=SOURCE_LABEL_BRAND,
            raw_brand=brand,
        )

    async def _scrape_html(self, url: str) -> FetchedPage | None:
        self._check_budget(_COST_SCRAPE)
        try:
            body = await self._post("/web/scrape", {"url": url, "formats": {"html": True}})
        except httpx.HTTPError as exc:
            logger.info("context.dev scrape failed for %s: %s", url, exc)
            return None
        html = (body or {}).get("html")
        if not isinstance(html, dict) or not html.get("success") or not html.get("data"):
            return None
        return FetchedPage(url=url, status_code=200, text=str(html["data"]))

    async def fetch_company_data(self, domain: str) -> ScrapedCompanyData:
        """Brand firmographics plus homepage and about/team HTML (so the existing heading-based
        contact extraction keeps working on these pages unchanged)."""
        if not self.enabled:
            logger.info("context.dev skipped for %s: no API key configured", domain)
            return ScrapedCompanyData(source_label=SOURCE_LABEL_SCRAPE)

        brand = ScrapedCompanyData(source_label=SOURCE_LABEL_BRAND)
        try:
            brand = await self.fetch_brand(domain)
        except httpx.HTTPError as exc:
            logger.info("context.dev brand failed for %s: %s", domain, exc)

        pages: list[FetchedPage] = []
        homepage = await self._scrape_html(f"https://{domain}/")
        if homepage is not None:
            pages.append(homepage)
            for path in _ABOUT_TEAM_PATHS:
                page = await self._scrape_html(f"https://{domain}{path}")
                if page is not None:
                    pages.append(page)

        if brand.raw_brand is None and not pages:
            raise ValueError(f"context.dev returned no data for {domain}")

        description = brand.description or (extract_description(pages[0].text) if pages else None)
        employee_count_range = brand.employee_count_range
        if not employee_count_range:
            for page in pages:
                employee_count_range = extract_employee_count(page.text)
                if employee_count_range:
                    break

        return ScrapedCompanyData(
            description=description,
            employee_count_range=employee_count_range,
            industry=brand.industry,
            pages_fetched=pages,
            source_label=SOURCE_LABEL_SCRAPE,
            raw_brand=brand.raw_brand,
        )

    # -- signals ------------------------------------------------------------------------------

    async def fetch_signals(self, domain: str) -> list[ScrapedSignal]:
        if not self.enabled:
            return []
        payload = {
            "searchBy": {"type": "entity", "entity": {"type": "domain", "domain": domain}},
            "limit": _MAX_NEWS_RESULTS,
        }
        self._check_budget(_COST_NEWS)
        try:
            body = await self._post("/news/search", payload)
        except httpx.HTTPError as exc:
            logger.info("context.dev news failed for %s: %s", domain, exc)
            return []
        articles = (body or {}).get("data")
        if not isinstance(articles, list):
            return []
        signals: list[ScrapedSignal] = []
        for article in articles:
            if not isinstance(article, dict):
                continue
            title, url = article.get("title"), article.get("url")
            if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
                continue
            published = article.get("published_at")
            blurb = article.get("description") or article.get("summary")
            signals.append(
                ScrapedSignal(
                    signal_type="news",
                    text=title.strip()[:200],
                    url=url,
                    date=published if isinstance(published, str) else None,
                    source_label=SOURCE_LABEL_NEWS,
                    summary=(
                        blurb.strip()[:300] if isinstance(blurb, str) and blurb.strip() else None
                    ),
                )
            )
        return signals

    # -- opportunity research -----------------------------------------------------------------

    async def search_company_news(
        self, domain: str, since_ms: int, limit: int = 10
    ) -> list[dict[str, Any]]:
        """News about the company that owns `domain`, newest first, published since `since_ms`.
        Searching by the company's website, not its name, avoids other companies with the same
        name. 1 credit per 10 results."""
        if not self.enabled:
            return []
        self._check_budget(_COST_NEWS)
        payload = {
            "searchBy": {"type": "entity", "entity": {"type": "domain", "domain": domain}},
            "limit": limit,
        }
        body = await self._post("/news/search", payload)
        articles = (body or {}).get("data")
        found: list[dict[str, Any]] = []
        for article in articles if isinstance(articles, list) else []:
            if not isinstance(article, dict):
                continue
            title, url = article.get("title"), article.get("url")
            published = article.get("published_at")
            if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
                continue
            if isinstance(published, str) and _published_ms(published) < since_ms:
                continue
            description = article.get("description")
            found.append(
                {
                    "title": title.strip()[:200],
                    "url": url,
                    "published_at": published if isinstance(published, str) else None,
                    "description": (
                        description.strip()[:400]
                        if isinstance(description, str) and description.strip()
                        else None
                    ),
                }
            )
        return found

    async def search_news(self, query: str, since_ms: int, limit: int = 10) -> list[dict[str, Any]]:
        """News matching a natural-language query, published since `since_ms` (epoch ms). 1 credit
        per 10 results. Raises on transport or server errors, like the other calls here."""
        if not self.enabled:
            return []
        self._check_budget(_COST_NEWS)
        payload = {
            "searchBy": {"type": "natural_language", "query": query[:1000]},
            "filterBy": {"date": {"from": since_ms}},
            "limit": limit,
        }
        body = await self._post("/news/search", payload)
        articles = (body or {}).get("data")
        found: list[dict[str, Any]] = []
        for article in articles if isinstance(articles, list) else []:
            if not isinstance(article, dict):
                continue
            title, url = article.get("title"), article.get("url")
            if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
                continue
            description = article.get("description")
            published = article.get("published_at")
            found.append(
                {
                    "title": title.strip()[:200],
                    "url": url,
                    "published_at": published if isinstance(published, str) else None,
                    "description": (
                        description.strip()[:400]
                        if isinstance(description, str) and description.strip()
                        else None
                    ),
                }
            )
        return found

    async def search_web(
        self,
        query: str,
        include_domains: list[str] | None = None,
        limit: int = 10,
        freshness: str = "last_year",
    ) -> list[dict[str, Any]]:
        """Web search, optionally limited to some domains and to the last year. 1 credit per 10
        results. The response carries no publication date, so results are undated."""
        if not self.enabled:
            return []
        self._check_budget(_COST_NEWS)
        payload: dict[str, Any] = {
            "query": query[:500],
            "numResults": limit,
            "freshness": freshness,
        }
        if include_domains:
            payload["includeDomains"] = include_domains
        body = await self._post("/web/search", payload)
        results = (body or {}).get("results")
        found: list[dict[str, Any]] = []
        for item in results if isinstance(results, list) else []:
            if not isinstance(item, dict):
                continue
            title, url = item.get("title"), item.get("url")
            if not isinstance(title, str) or not title.strip() or not isinstance(url, str):
                continue
            description = item.get("description")
            found.append(
                {
                    "title": title.strip()[:200],
                    "url": url,
                    "description": (
                        description.strip()[:400]
                        if isinstance(description, str) and description.strip()
                        else None
                    ),
                }
            )
        return found

    # -- site pages (offerings importer) ------------------------------------------------------

    async def map_urls(
        self, domain: str, sitemap_url: str | None = None, exclude_regex: str | None = None
    ) -> list[str]:
        """URLs context.dev finds for a domain (1 credit). Raises on transport/server errors."""
        pages = await self.map_pages(domain, sitemap_url, exclude_regex)
        return [url for page in pages if (url := page["url"])]

    async def map_pages(
        self, domain: str, sitemap_url: str | None = None, exclude_regex: str | None = None
    ) -> list[dict[str, str | None]]:
        """Like `map_urls` but keeps each page's title and description when context.dev has
        them, which is enough to tell what a page is about without reading it."""
        if not self.enabled:
            return []
        self._check_budget(_COST_MAP)
        params: dict[str, Any] = {"domain": domain}
        if sitemap_url:
            params["sitemapUrl"] = sitemap_url
        if exclude_regex:
            params["excludeUrlRegex"] = exclude_regex
        headers = {"Authorization": f"Bearer {self._api_key}"}
        begin = started()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{_BASE_URL}/web/urls", headers=headers, params=params)
        if resp.status_code >= 400:
            await record_usage(
                provider="contextdev",
                kind="credits",
                status="error",
                units=0,
                latency_ms=elapsed_ms(begin),
            )
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            return []
        credits = (body.get("key_metadata") or {}).get("credits_consumed")
        if isinstance(credits, int):
            self.credits_used += credits
        await record_usage(
            provider="contextdev",
            kind="credits",
            units=credits if isinstance(credits, int) else 0,
            latency_ms=elapsed_ms(begin),
        )
        items = body.get("urls")
        if not isinstance(items, list):
            return []

        def text(value: Any) -> str | None:
            return value.strip() if isinstance(value, str) and value.strip() else None

        return [
            {
                "url": i["url"],
                "title": text(i.get("title")),
                "description": text(i.get("description")),
            }
            for i in items
            if isinstance(i, dict) and isinstance(i.get("url"), str)
        ]

    async def scrape_markdown(self, url: str) -> str | None:
        """A page as markdown (1 credit); `None` when it could not be read."""
        if not self.enabled:
            return None
        self._check_budget(_COST_SCRAPE)
        body = None
        for attempt in range(_SCRAPE_ATTEMPTS):
            try:
                body = await self._post("/web/scrape", {"url": url, "formats": {"markdown": True}})
                break
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                # A dropped connection or failed DNS lookup is a blip, not "the page is empty".
                logger.info("context.dev scrape hit a network problem for %s: %s", url, exc)
                if attempt + 1 < _SCRAPE_ATTEMPTS:
                    await asyncio.sleep(_SCRAPE_RETRY_WAIT * (attempt + 1))
            except httpx.HTTPError as exc:
                logger.info("context.dev markdown scrape failed for %s: %s", url, exc)
                return None
        markdown = (body or {}).get("markdown")
        if not isinstance(markdown, dict) or not markdown.get("success"):
            return None
        if not markdown.get("data"):
            return None
        return str(markdown["data"])

    # -- people (benchmark only) --------------------------------------------------------------

    async def enrich_person(
        self, full_name: str, company_domain: str
    ) -> dict[str, Any] | None | str:
        """Not wired into the pipeline. Returns the matched profile dict, `None` for no match, or
        the string "plan_gated" when the account is on a free plan (422 per the docs)."""
        if not self.enabled:
            return None
        first, _, last = full_name.strip().partition(" ")
        try:
            return await self._post(
                "/people/enrich",
                {"name": {"first": first, "last": last}, "company": company_domain},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 422:
                return "plan_gated"
            raise


def _employee_range(employees: Any) -> str | None:
    """Prefer the vendor's bucket ("51-200") — same shape the in-house scraper stores — over an
    exact integer, which is stored as a plain string."""
    if isinstance(employees, dict):
        bucket = employees.get("range")
        if isinstance(bucket, str) and bucket:
            return bucket[:_EMPLOYEE_RANGE_MAX]
        exact = employees.get("exact")
        if isinstance(exact, int) and exact > 0:
            return str(exact)
    elif isinstance(employees, int) and employees > 0:
        return str(employees)
    return None


def _industry(industries: Any) -> str | None:
    entries = industries.get("eic") if isinstance(industries, dict) else industries
    if not isinstance(entries, list) or not entries or not isinstance(entries[0], dict):
        return None
    industry = entries[0].get("industry")
    return industry[:_INDUSTRY_MAX] if isinstance(industry, str) and industry else None
