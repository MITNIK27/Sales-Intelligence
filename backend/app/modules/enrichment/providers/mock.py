"""Canned in-memory provider implementations for unit/integration tests — no network calls."""

from app.modules.enrichment.providers.base import (
    CompanyDataProvider,
    CompanyDiscoveryProvider,
    ContactDataProvider,
    DomainDiscoveryProvider,
    DomainMatch,
    FetchedPage,
    ScrapedCompanyData,
    ScrapedContact,
    ScrapedSignal,
    SignalDataProvider,
)


class MockDomainDiscoveryProvider(DomainDiscoveryProvider):
    def __init__(self, result: DomainMatch | None = None) -> None:
        self._result = result

    async def find_domain(self, company_name: str) -> DomainMatch | None:
        return self._result


class MockCompanyDataProvider(CompanyDataProvider):
    def __init__(self, result: ScrapedCompanyData | None = None) -> None:
        self._result = result or ScrapedCompanyData()

    async def fetch_company_data(self, domain: str) -> ScrapedCompanyData:
        return self._result


class MockContactDataProvider(ContactDataProvider):
    def __init__(self, contacts: list[ScrapedContact] | None = None) -> None:
        self._contacts = contacts or []

    async def fetch_contacts(
        self, domain: str, pages: list[FetchedPage]
    ) -> list[ScrapedContact]:
        return self._contacts


class MockSignalDataProvider(SignalDataProvider):
    def __init__(self, signals: list[ScrapedSignal] | None = None) -> None:
        self._signals = signals or []

    async def fetch_signals(self, domain: str) -> list[ScrapedSignal]:
        return self._signals


class MockCompanyDiscoveryProvider(CompanyDiscoveryProvider):
    def __init__(self, candidates: list[DomainMatch] | None = None) -> None:
        self._candidates = candidates or []

    async def find_candidates(self, query: str, limit: int = 10) -> list[DomainMatch]:
        return self._candidates[:limit]
