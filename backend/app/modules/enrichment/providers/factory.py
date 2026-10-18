"""Chooses the company-data and signal providers for every enrichment path, per the
`company_data_source` setting. Contacts always stay with the in-house scraper (it owns the
heading-based extraction); only firmographics and signals are swappable."""

import asyncio
import logging
from dataclasses import dataclass, replace
from typing import Any

from app.core.config import Settings
from app.modules.enrichment.completeness import (
    company_data_is_sufficient,
    missing_company_fields,
    signals_are_sufficient,
)
from app.modules.enrichment.providers.base import (
    CompanyDataProvider,
    ScrapedCompanyData,
    ScrapedSignal,
    SignalDataProvider,
)
from app.modules.enrichment.providers.context_dev import ContextDevProvider
from app.modules.enrichment.providers.website_scraper import WebsiteScraperProvider

logger = logging.getLogger(__name__)


class ScraperWithContextDevFallback(CompanyDataProvider):
    """Scraper first; context.dev fills only what the scraper left thin.

    - Scraper raised or got no pages: full context.dev fetch (brand + pages), so a failed
      homepage - the documented weak spot - can still end up enriched.
    - Scraper succeeded and its data is sufficient (real description plus industry or employee
      range, see `completeness.py`): context.dev is NOT called at all - no credits spent.
    - Scraper succeeded but the data is thin: one brand-only call, no re-scraping of pages the
      scraper already has, and only the missing fields are taken from it.

    Every call goes through the provider's per-run credit ceiling; once it is reached the run
    simply continues with scraper data."""

    def __init__(
        self,
        scraper: CompanyDataProvider,
        contextdev: ContextDevProvider,
        scraper_timeout_seconds: float = 45.0,
    ) -> None:
        self._scraper = scraper
        self._contextdev = contextdev
        self._scraper_timeout = scraper_timeout_seconds
        self.skipped_sufficient = 0  # companies where the scraper alone was enough

    def usage(self) -> dict[str, Any]:
        return {**self._contextdev.usage(), "skipped_sufficient": self.skipped_sufficient}

    async def fetch_company_data(self, domain: str) -> ScrapedCompanyData:
        primary: ScrapedCompanyData | None = None
        try:
            primary = await asyncio.wait_for(
                self._scraper.fetch_company_data(domain), timeout=self._scraper_timeout
            )
        except Exception as exc:  # noqa: BLE001 - any scraper failure (incl. a hang) -> fall back
            logger.info(
                "scraper failed for %s (%s), falling back to context.dev",
                domain,
                exc or "timed out",
            )

        if primary is None or not primary.pages_fetched:
            try:
                return await self._contextdev.fetch_company_data(domain)
            except Exception:
                if primary is not None:
                    return primary  # pages-less scraper result still beats nothing
                raise

        if company_data_is_sufficient(primary):
            self.skipped_sufficient += 1
            return primary

        missing = missing_company_fields(primary)
        try:
            brand = await self._contextdev.fetch_brand(domain)
        except Exception as exc:  # noqa: BLE001 - best-effort top-up, scraper data still stands
            logger.info("context.dev brand top-up failed for %s: %s", domain, exc)
            return primary

        sources = dict(primary.field_sources)
        merged: dict[str, Any] = {}
        for name in ("description", "employee_count_range", "industry"):
            if name in missing and getattr(brand, name):
                merged[name] = getattr(brand, name)
                sources[name] = brand.source_label
        # A description the scraper found but judged too thin is replaced by the brand's.
        return replace(primary, raw_brand=brand.raw_brand, field_sources=sources, **merged)


class ScraperFirstSignalProvider(SignalDataProvider):
    """Scraper signals first; the paid source is asked only when the scraper found too few real
    news-like items (menu text does not count). One provider failing never drops the other, and
    a spent credit budget just means no paid signals for the rest of the run."""

    def __init__(self, primary: SignalDataProvider, secondary: SignalDataProvider) -> None:
        self._primary = primary
        self._secondary = secondary

    async def fetch_signals(self, domain: str) -> list[ScrapedSignal]:
        signals: list[ScrapedSignal] = []
        try:
            signals = await self._primary.fetch_signals(domain)
        except Exception as exc:  # noqa: BLE001
            logger.info("primary signal provider failed for %s: %s", domain, exc)
        if signals_are_sufficient(signals):
            return signals
        try:
            signals = [*signals, *await self._secondary.fetch_signals(domain)]
        except Exception as exc:  # noqa: BLE001
            logger.info("secondary signal provider failed for %s: %s", domain, exc)
        return signals


@dataclass(frozen=True)
class CompanyProviders:
    company: CompanyDataProvider
    signals: SignalDataProvider


def build_company_providers(
    settings: Settings, scraper: WebsiteScraperProvider
) -> CompanyProviders:
    source = settings.company_data_source
    if source == "scraper":
        return CompanyProviders(company=scraper, signals=scraper)

    contextdev = ContextDevProvider(settings)
    if not contextdev.enabled:
        logger.warning(
            "company_data_source=%s but CONTEXT_DEV_API_KEY is unset; using in-house scraper",
            source,
        )
        return CompanyProviders(company=scraper, signals=scraper)

    if source == "contextdev":
        return CompanyProviders(company=contextdev, signals=contextdev)
    return CompanyProviders(
        company=ScraperWithContextDevFallback(
            scraper, contextdev, settings.scraper_company_timeout_seconds
        ),
        signals=ScraperFirstSignalProvider(scraper, contextdev),
    )
