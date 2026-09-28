"""In-house search-based contact discovery — supplements `WebsiteScraperProvider`'s on-page
extraction for companies whose decision-makers aren't listed on their own website. Reuses
`SerperSearchProvider.search_raw` (already-built, already-paid-for infra) rather than a new
vendor integration, and deliberately never fetches or scrapes the trusted domains themselves —
only reads what Google's own index already shows in a result's title/snippet, the same technique
`SerperSearchProvider` already uses for domain/candidate discovery elsewhere in this app. This is
meaningfully different from scraping LinkedIn (or any trusted site) directly, which stays
excluded per ADR 0001.

Heuristic and low-confidence by nature — a search-result title is a much noisier signal than a
company's own team page — so every result stays reviewable (`Contact.needs_review=True`) rather
than treated as ground truth. See ADR 0010."""

from abc import ABC, abstractmethod

from app.core.config import Settings
from app.modules.enrichment.providers.base import (
    DECISION_MAKER_KEYWORDS,
    ScrapedContact,
    looks_like_person_name,
)
from app.modules.enrichment.providers.search_serper import SerperSearchProvider


def _quote_if_multiword(term: str) -> str:
    return f'"{term}"' if " " in term else term


def build_contact_search_query(company_name: str, trusted_domains: list[str]) -> str:
    """Composes the search string from the org-configurable trusted-domain allowlist and the
    shared decision-maker title vocabulary — deliberately not a freeform user-edited template, so
    the site scope stays a controlled, reviewable list rather than something a rep can widen by
    accident (typo, scope creep) into searching arbitrary/untrusted sites."""
    titles = " OR ".join(_quote_if_multiword(kw) for kw in DECISION_MAKER_KEYWORDS)
    sites = " OR ".join(f"site:{domain}" for domain in trusted_domains)
    return f'"{company_name}" ({titles}) ({sites})'


def _find_role_title(segments: list[str], snippet: str) -> str | None:
    for segment in segments:
        if any(kw in segment.lower() for kw in DECISION_MAKER_KEYWORDS):
            return segment
    snippet_lower = snippet.lower()
    for kw in DECISION_MAKER_KEYWORDS:
        if kw in snippet_lower:
            # No clean short phrase to extract from a snippet sentence — the keyword itself is a
            # better role_title than pulling in surrounding prose.
            return kw.title()
    return None


def _parse_result(item: dict[str, str]) -> ScrapedContact | None:
    """A LinkedIn-style search result title is consistently shaped
    "Name - Title - Company | LinkedIn" or "Name | LinkedIn" — split on " | " to drop the
    trailing site name, then on " - " for name/title/company segments. Rejects anything whose
    first segment doesn't look like a person's name, and (same guardrail as the website scraper)
    requires an actual decision-maker keyword hit somewhere before accepting the result at all —
    a name-only match with no evident title is too weak a signal to surface."""
    title = (item.get("title") or "").strip()
    if not title:
        return None
    segments = [s.strip() for s in title.split(" | ")[0].split(" - ") if s.strip()]
    if not segments:
        return None

    name = segments[0]
    if not looks_like_person_name(name):
        return None

    role_title = _find_role_title(segments[1:], item.get("snippet") or "")
    if role_title is None:
        return None

    return ScrapedContact(full_name=name, role_title=role_title, email=None)


class ContactSearchProvider(ABC):
    @abstractmethod
    async def search_contacts(
        self, company_name: str, domain: str | None
    ) -> list[ScrapedContact]: ...


class SerperContactSearchProvider(ContactSearchProvider):
    """Composition, not inheritance, over `SerperSearchProvider` — reuses its already-built HTTP
    client/API-key handling via `search_raw` rather than a new integration."""

    def __init__(self, settings: Settings, search: SerperSearchProvider) -> None:
        self._settings = settings
        self._search = search

    async def search_contacts(self, company_name: str, domain: str | None) -> list[ScrapedContact]:
        if not self._settings.contact_search_enabled:
            return []
        query = build_contact_search_query(
            company_name, self._settings.contact_search_trusted_domains
        )
        results = await self._search.search_raw(query, num=10)
        contacts: list[ScrapedContact] = []
        for item in results:
            contact = _parse_result(item)
            if contact is not None:
                contacts.append(contact)
        return contacts
