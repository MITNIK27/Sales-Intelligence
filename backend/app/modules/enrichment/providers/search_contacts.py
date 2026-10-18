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

import re
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


_COMPANY_SUFFIXES = frozenset(
    {
        "inc", "llc", "ltd", "limited", "corp", "corporation", "co", "company", "group", "gmbh",
        "ag", "sa", "se", "nv", "bv", "plc", "holding", "holdings", "the", "and",
    }
)
SOURCE_LABEL = "serper:linkedin"

# Confidence is built from independent pieces of evidence; each is worth a fixed share. Both the
# company AND the role in the profile headline (the segments after the name) is the strong case.
_W_PROFILE_URL = 0.2
_W_COMPANY_IN_TITLE, _W_COMPANY_IN_SNIPPET = 0.45, 0.25
_W_ROLE_IN_TITLE, _W_ROLE_IN_SNIPPET = 0.3, 0.15


def normalize_linkedin_profile_url(link: str | None) -> str | None:
    """A person's public profile (`linkedin.com/in/<handle>`) in canonical form, or None for a
    company page, job post, search page, or anything else that is not a person."""
    if not link:
        return None
    match = re.match(
        r"^https?://(?:[a-z]{2,3}\.)?(?:www\.)?linkedin\.com/in/([^/?#\s]+)", link.strip(), re.I
    )
    if not match:
        return None
    return f"https://www.linkedin.com/in/{match.group(1).lower()}"


def _company_tokens(company_name: str | None, domain: str | None) -> list[str]:
    """Phrases that identify the company in free text: its name without legal suffixes, and the
    first label of its domain (dpd.com -> dpd)."""
    tokens: list[str] = []
    if company_name:
        words = [w for w in re.split(r"[^a-z0-9]+", company_name.lower()) if w]
        core = [w for w in words if w not in _COMPANY_SUFFIXES]
        if core:
            tokens.append(" ".join(core))
    if domain:
        label = domain.lower().removeprefix("www.").split(".")[0]
        if len(label) >= 3 and label not in tokens:
            tokens.append(label)
    return tokens


def _mentions(text: str, tokens: list[str]) -> bool:
    lowered = text.lower()
    return any(re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", lowered) for t in tokens)


def _parse_result(
    item: dict[str, str], company_name: str | None = None, domain: str | None = None
) -> ScrapedContact | None:
    """A LinkedIn-style search result title is consistently shaped
    "Name - Title - Company | LinkedIn" or "Name | LinkedIn" — split on " | " to drop the
    trailing site name, then on " - " for name/title/company segments.

    Accepts a result only when it is a real person profile (`/in/<handle>` link), the first
    segment looks like a person's name, a decision-maker role is evident, and — when the company
    is known — the company appears in the profile headline or snippet OUTSIDE the person's own
    name (so "Jackie Hermes" never matches a search for the company Hermes). The returned
    confidence reflects how much of that was found in the headline versus only the snippet."""
    title = (item.get("title") or "").strip()
    if not title:
        return None
    profile_url = normalize_linkedin_profile_url(item.get("link"))
    if profile_url is None:
        return None
    segments = [s.strip() for s in title.split(" | ")[0].split(" - ") if s.strip()]
    if not segments:
        return None

    name = segments[0]
    if not looks_like_person_name(name):
        return None

    snippet = item.get("snippet") or ""
    role_title = _find_role_title(segments[1:], snippet)
    if role_title is None:
        return None

    headline = " - ".join(segments[1:])
    # The snippet usually opens with the person's name; blank it out before looking for the
    # company so a surname equal to the company name cannot count as a match.
    snippet_without_name = re.sub(re.escape(name), " ", snippet, flags=re.I)
    confidence = _W_PROFILE_URL
    if any(kw in headline.lower() for kw in DECISION_MAKER_KEYWORDS):
        confidence += _W_ROLE_IN_TITLE
    else:
        confidence += _W_ROLE_IN_SNIPPET

    tokens = _company_tokens(company_name, domain)
    if tokens:
        if _mentions(headline, tokens):
            confidence += _W_COMPANY_IN_TITLE
        elif _mentions(snippet_without_name, tokens):
            confidence += _W_COMPANY_IN_SNIPPET
        else:
            return None  # company association not established
    else:
        confidence += _W_COMPANY_IN_SNIPPET  # no company to check against: neutral, not strong

    return ScrapedContact(
        full_name=name,
        role_title=role_title,
        email=None,
        linkedin_url=profile_url,
        confidence=round(min(confidence, 1.0), 2),
        source_snippet=(snippet or title)[:300],
        source=SOURCE_LABEL,
    )


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
            contact = _parse_result(item, company_name, domain)
            if contact is not None and (
                contact.confidence is None
                or contact.confidence >= self._settings.contact_confidence_min
            ):
                contacts.append(contact)
        return contacts
