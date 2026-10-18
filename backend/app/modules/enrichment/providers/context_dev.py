"""context.dev-backed CompanyDataProvider/SignalDataProvider (https://docs.context.dev).

Raw httpx rather than the vendor SDK: matches `search_serper.py`, stays testable with the same
`httpx.AsyncClient.post` monkeypatch, and adds no dependency to a provider that may well be
dropped after evaluation (docs/decisions/0012-context-dev-evaluation.md).

Endpoints used and their documented credit cost: brand/retrieve (10), web/scrape html (1),
news/search (1 per 10 results). people/enrich (20, paid plans only) is exposed separately as
`enrich_person` and is only used by the benchmark script, never by the pipeline."""

import logging
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


class ContextDevBudgetExceeded(RuntimeError):
    """The per-run credit ceiling was reached; the paid call was NOT made. Callers treat this as
    "context.dev unavailable for the rest of this run", never as a pipeline failure."""


class ContextDevProvider(CompanyDataProvider, SignalDataProvider):
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.context_dev_api_key
        self._timeout = settings.context_dev_timeout_seconds
        self._ceiling = settings.context_dev_max_credits_per_run
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

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """POST and return the JSON body; `None` for a 404 ("nothing known"). Any other failure
        raises `httpx.HTTPError` — callers decide whether that is fatal."""
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{_BASE_URL}{path}", headers=headers, json=payload)
        if resp.status_code == 404:
            return None
        if resp.status_code == 400:
            # A rejected request (e.g. a domain the vendor cannot resolve) means "no data", not a
            # provider outage; the body says why, so keep it in the log.
            logger.info("context.dev %s rejected the request: %s", path, resp.text[:200])
            return None
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            return None
        credits = (body.get("key_metadata") or {}).get("credits_consumed")
        if isinstance(credits, int):
            self.credits_used += credits
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

        description = brand.description or (
            extract_description(pages[0].text) if pages else None
        )
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
