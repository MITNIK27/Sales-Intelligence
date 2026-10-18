from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

# Shared between WebsiteScraperProvider's on-page heading heuristic and the search-based contact
# provider — same "which titles count as a decision-maker worth surfacing" vocabulary either way,
# a team page listing every employee shouldn't import every employee, only plausible sales
# targets.
DECISION_MAKER_KEYWORDS = (
    "ceo", "cto", "coo", "cfo", "founder", "co-founder", "president", "vp",
    "vice president", "director", "head of", "owner", "manager",
)

_PERSON_NAME_MIN_WORDS = 2
_PERSON_NAME_MAX_WORDS = 4

# Common company-name words that would otherwise pass the "2-4 capitalized words, no digits"
# shape check (e.g. "Acme Inc") — reject a candidate containing any of these rather than
# accepting an organization name as if it were a person.
_COMPANY_WORD_STOPLIST = frozenset(
    {
        "inc", "inc.", "llc", "ltd", "ltd.", "corp", "corp.", "co", "co.", "company",
        "group", "technologies", "solutions", "services", "partners", "holdings",
        "enterprises", "industries", "consulting",
    }
)


def looks_like_person_name(candidate: str) -> bool:
    """Shape-only heuristic for "is this plausibly a person's name, not a company/product/nav
    label/page title": 2-4 capitalized words, no digits, none of them a common company-suffix
    word. Shared by `website_scraper.py` (on-page headings) and `search_contacts.py`
    (search-result titles) — same noise, same guardrail, one implementation."""
    words = candidate.split()
    if not (_PERSON_NAME_MIN_WORDS <= len(words) <= _PERSON_NAME_MAX_WORDS):
        return False
    if any(ch.isdigit() for ch in candidate):
        return False
    if any(word.lower().strip(".,") in _COMPANY_WORD_STOPLIST for word in words):
        return False
    return all(word[0].isupper() for word in words if word)


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
    # Provenance prefix for the EnrichmentRecords written for `pages_fetched` — lets a record say
    # which provider actually produced a page when several can feed the same pipeline.
    source_label: str = "scraper:companysite"
    # Provider-specific raw firmographics blob (e.g. context.dev's brand JSON: logo, HQ, socials)
    # persisted verbatim in an EnrichmentRecord, so richer fields are kept without a schema change.
    raw_brand: dict[str, Any] | None = None
    # Which provider produced each filled field ({"industry": "contextdev:brand", ...}); fields
    # not listed came from `source_label`. Lets provenance stay accurate when providers are mixed.
    field_sources: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ScrapedContact:
    full_name: str
    role_title: str | None = None
    email: str | None = None
    # Set by search-based discovery: the person's public profile, how sure we are they work at
    # this company (0..1), the text that convinced us, and which provider produced it.
    linkedin_url: str | None = None
    confidence: float | None = None
    source_snippet: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class ScrapedSignal:
    signal_type: Literal["news", "job_posting"]
    text: str
    url: str
    date: str | None = None
    source_label: str = "scraper:companysite"
    summary: str | None = None


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
