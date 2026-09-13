from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class DomainMatch:
    domain: str
    confidence: Literal["exact", "fuzzy"]
    title: str | None = None


@dataclass(frozen=True)
class FetchedPage:
    url: str
    status_code: int
    text: str


@dataclass(frozen=True)
class ScrapedCompanyData:
    description: str | None = None
    employee_count_range: str | None = None
    industry: str | None = None
    pages_fetched: list[FetchedPage] = field(default_factory=list)


@dataclass(frozen=True)
class ScrapedContact:
    full_name: str
    role_title: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class ScrapedSignal:
    signal_type: Literal["news", "job_posting"]
    text: str
    url: str
    date: str | None = None


class DomainDiscoveryProvider(ABC):
    """Finds a company's website when none is on file. A `fuzzy` DomainMatch means "found, but
    not confirmed" — callers should flag the result for review rather than treat it as certain."""

    @abstractmethod
    async def find_domain(self, company_name: str) -> DomainMatch | None: ...


class CompanyDataProvider(ABC):
    """Fetches firmographic data for a company's website."""

    @abstractmethod
    async def fetch_company_data(self, domain: str) -> ScrapedCompanyData: ...


class ContactDataProvider(ABC):
    """Extracts decision-maker contacts from a company's already-fetched pages (reuses the
    pages `CompanyDataProvider` fetched rather than fetching again)."""

    @abstractmethod
    async def fetch_contacts(
        self, domain: str, pages: list[FetchedPage]
    ) -> list[ScrapedContact]: ...


class CompanyDiscoveryProvider(ABC):
    """Finds candidate companies matching a free-text search query (Market Discovery, Phase
    2c). Every result is inherently a lead, never a confirmed match — always returned at
    `confidence="fuzzy"`, same as `DomainDiscoveryProvider`."""

    @abstractmethod
    async def find_candidates(self, query: str, limit: int = 10) -> list[DomainMatch]: ...


class SignalDataProvider(ABC):
    """Collects raw buying-signal snippets (news/press, job postings) from a company's own
    site. Deliberately collect-and-store only — no interpretation of what a signal means."""

    @abstractmethod
    async def fetch_signals(self, domain: str) -> list[ScrapedSignal]: ...
