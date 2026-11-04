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
from dataclasses import dataclass

from app.core.config import Settings
from app.modules.enrichment.providers.base import (
    DECISION_MAKER_KEYWORDS,
    ScrapedContact,
    SearchTitles,
    looks_like_person_name,
)
from app.modules.enrichment.providers.search_serper import SerperSearchProvider


def _quote_if_multiword(term: str) -> str:
    return f'"{term}"' if " " in term else term


def build_contact_search_query(
    company_name: str, trusted_domains: list[str], focus: str | None = None
) -> str:
    """Composes the search string from the org-configurable trusted-domain allowlist and the
    shared decision-maker title vocabulary — deliberately not a freeform user-edited template, so
    the site scope stays a controlled, reviewable list rather than something a rep can widen by
    accident (typo, scope creep) into searching arbitrary/untrusted sites."""
    titles = " OR ".join(_quote_if_multiword(kw) for kw in DECISION_MAKER_KEYWORDS)
    sites = " OR ".join(f"site:{domain}" for domain in trusted_domains)
    area = f" {_quote_if_multiword(focus.strip())}" if focus and focus.strip() else ""
    return f'"{company_name}"{area} ({titles}) ({sites})'


# The search recognises more titles than the shared decision-maker list, which the website scraper
# also uses and is left alone. Chiefs of a function and managing-level titles matter here.
SEARCH_TITLE_KEYWORDS = (
    *DECISION_MAKER_KEYWORDS,
    "chief",
    "cio",
    "cmo",
    "chro",
    "cpo",
    "svp",
    "evp",
    "managing director",
    "general manager",
    "head",
    "lead",
    "partner",
    "principal",
)


def _has_keyword(text: str, keyword: str) -> bool:
    """The keyword as a whole word or phrase, so "cio" does not match "precious"."""
    return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text) is not None


def _find_role_title(
    segments: list[str], snippet: str, vocabulary: tuple[str, ...] | list[str] | None = None
) -> str | None:
    words = vocabulary or SEARCH_TITLE_KEYWORDS
    for segment in segments:
        lowered = segment.lower()
        if any(_has_keyword(lowered, kw) for kw in words):
            return segment
    snippet_lower = snippet.lower()
    for kw in words:
        if _has_keyword(snippet_lower, kw):
            # No clean short phrase to extract from a snippet sentence — the keyword itself is a
            # better role_title than pulling in surrounding prose.
            return kw.title()
    return None


_COMPANY_SUFFIXES = frozenset(
    {
        "inc",
        "llc",
        "ltd",
        "limited",
        "corp",
        "corporation",
        "co",
        "company",
        "group",
        "gmbh",
        "ag",
        "sa",
        "se",
        "nv",
        "bv",
        "plc",
        "holding",
        "holdings",
        "the",
        "and",
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


def _classify(
    item: dict[str, str],
    company_name: str | None = None,
    domain: str | None = None,
    vocabulary: list[str] | None = None,
) -> tuple[ScrapedContact | None, str]:
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
        return None, "not_a_profile"
    profile_url = normalize_linkedin_profile_url(item.get("link"))
    if profile_url is None:
        return None, "not_a_profile"
    segments = [s.strip() for s in title.split(" | ")[0].split(" - ") if s.strip()]
    if not segments:
        return None, "not_a_profile"

    name = segments[0]
    if not looks_like_person_name(name):
        return None, "not_a_person"

    snippet = item.get("snippet") or ""
    role_title = _find_role_title(segments[1:], snippet, vocabulary)
    if role_title is None:
        return None, "no_role"

    headline = " - ".join(segments[1:])
    # The snippet usually opens with the person's name; blank it out before looking for the
    # company so a surname equal to the company name cannot count as a match.
    snippet_without_name = re.sub(re.escape(name), " ", snippet, flags=re.I)
    confidence = _W_PROFILE_URL
    words = vocabulary or SEARCH_TITLE_KEYWORDS
    if any(_has_keyword(headline.lower(), kw) for kw in words):
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
            return None, "other_company"  # company association not established
    else:
        confidence += _W_COMPANY_IN_SNIPPET  # no company to check against: neutral, not strong

    contact = ScrapedContact(
        full_name=name,
        role_title=role_title,
        email=None,
        linkedin_url=profile_url,
        confidence=round(min(confidence, 1.0), 2),
        source_snippet=(snippet or title)[:300],
        source=SOURCE_LABEL,
    )
    return contact, "ok"


def _parse_result(
    item: dict[str, str], company_name: str | None = None, domain: str | None = None
) -> ScrapedContact | None:
    return _classify(item, company_name, domain)[0]


@dataclass
class SearchReport:
    """Where a people search lost its results, so an empty answer can be explained. Each count is
    after the step named: results returned, person profiles, a role evident, the company
    established, and finally accepted."""

    queries: int = 0
    results: int = 0
    profiles: int = 0
    persons: int = 0
    with_role: int = 0
    at_company: int = 0
    accepted: int = 0
    no_titles: bool = False

    def line(self, company_name: str) -> str:
        if self.no_titles:
            return (
                "People search had no job titles to look for. Add example titles "
                '(after "e.g.") to your role categories.'
            )
        if self.queries == 0:
            return "People search was switched off."
        if self.results == 0:
            return f"People search: {self.queries} queries, no results from the search engine."
        return (
            f"People search: {self.results} results from {self.queries} "
            f"{'query' if self.queries == 1 else 'queries'}, {self.profiles} were LinkedIn "
            f"profiles, {self.at_company} looked like people at {company_name} in a leadership "
            f"role, {self.accepted} kept."
        )


class ContactSearchProvider(ABC):
    last_report: SearchReport | None = None

    @abstractmethod
    async def search_contacts(
        self,
        company_name: str,
        domain: str | None,
        focus: str | None = None,
        functions: list[str] | None = None,
        titles: SearchTitles | None = None,
    ) -> list[ScrapedContact]:
        """People at the company found through search. `titles` come from the organisation's role
        categories; `functions` (for example "Head of Procurement") are the roles an offering is
        sold to and get a query of their own; `focus` (a business area) narrows one query."""
        ...


MAX_QUERIES = 3
ENOUGH_PEOPLE = 6
MAX_TERMS = 8

# Words that show a result names a senior role, whatever the department. These are seniority
# words, not job titles: the titles searched for come from the role categories.
SENIORITY_WORDS = (
    "chief",
    "head",
    "director",
    "vp",
    "svp",
    "evp",
    "vice president",
    "president",
    "manager",
    "lead",
    "founder",
    "owner",
    "partner",
    "principal",
)


def build_contact_queries(
    company_name: str,
    trusted_domains: list[str],
    focus: str | None = None,
    functions: list[str] | None = None,
    titles: SearchTitles | None = None,
) -> list[str]:
    """Up to three searches built from the organisation's own role categories: the first-reach
    titles; then the roles the offering is sold to (or the other categories' titles); then, for a
    named area, the first-reach titles tied to it. Each stays inside the trusted-site list, so
    the scope is never widened by accident. No titles anywhere means nothing to search for."""
    sites = " OR ".join(f"site:{domain}" for domain in trusted_domains)
    company = f'"{company_name}"'
    titles = titles or SearchTitles()

    def terms(items: tuple[str, ...] | list[str]) -> str:
        return " OR ".join(_quote_if_multiword(t) for t in list(items)[:MAX_TERMS])

    first = titles.primary or titles.other
    wanted = [f.strip() for f in (functions or []) if f and f.strip()]
    second = tuple(wanted) or (titles.other if titles.primary else ())
    queries = []
    if first:
        queries.append(f"{company} ({terms(first)}) ({sites})")
    if second:
        queries.append(f"{company} ({terms(second)}) ({sites})")
    if focus and focus.strip() and first:
        queries.append(f"{company} {_quote_if_multiword(focus.strip())} ({terms(first)}) ({sites})")
    return queries[:MAX_QUERIES]


class SerperContactSearchProvider(ContactSearchProvider):
    """Composition, not inheritance, over `SerperSearchProvider` — reuses its already-built HTTP
    client/API-key handling via `search_raw` rather than a new integration."""

    def __init__(self, settings: Settings, search: SerperSearchProvider) -> None:
        self._settings = settings
        self._search = search

    async def search_contacts(
        self,
        company_name: str,
        domain: str | None,
        focus: str | None = None,
        functions: list[str] | None = None,
        titles: SearchTitles | None = None,
    ) -> list[ScrapedContact]:
        report = SearchReport()
        self.last_report = report
        if not self._settings.contact_search_enabled:
            return []
        queries = build_contact_queries(
            company_name, self._settings.contact_search_trusted_domains, focus, functions, titles
        )
        if not queries:
            report.no_titles = True
            return []
        vocabulary = [*SENIORITY_WORDS, *(t.lower() for t in (titles.all() if titles else ()))]
        vocabulary += [f.lower() for f in functions or []]
        contacts: dict[str, ScrapedContact] = {}
        for query in queries:
            report.queries += 1
            for item in await self._search.search_raw(query, num=10):
                report.results += 1
                contact, reason = _classify(item, company_name, domain, vocabulary)
                self._count(report, reason)
                if contact is None:
                    continue
                confidence = contact.confidence
                if confidence is not None and confidence < self._settings.contact_confidence_min:
                    continue
                key = contact.linkedin_url or contact.full_name
                if key not in contacts:
                    contacts[key] = contact
                    report.accepted += 1
            if len(contacts) >= ENOUGH_PEOPLE:
                break
        return list(contacts.values())

    @staticmethod
    def _count(report: SearchReport, reason: str) -> None:
        if reason != "not_a_profile":
            report.profiles += 1
        if reason not in ("not_a_profile", "not_a_person"):
            report.persons += 1
        if reason not in ("not_a_profile", "not_a_person", "no_role"):
            report.with_role += 1
        if reason == "ok":
            report.at_company += 1
