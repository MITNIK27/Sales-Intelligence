"""Default in-house CompanyDataProvider/ContactDataProvider: scrapes a company's own website
(homepage + a couple of about/team pages). Heuristic extraction only, deliberately no LLM here —
see the Phase 2a plan for why (2c is where the shared Gemini client first gets built)."""

import asyncio
import logging
import re
import time
import urllib.robotparser as robotparser
from typing import Literal

import httpx
from bs4 import BeautifulSoup

from app.core.config import Settings
from app.modules.enrichment.providers.base import (
    CompanyDataProvider,
    ContactDataProvider,
    FetchedPage,
    ScrapedCompanyData,
    ScrapedContact,
    ScrapedSignal,
    SignalDataProvider,
)

logger = logging.getLogger(__name__)

# Fixed candidate paths, tried in order until MAX_ABOUT_PAGES are found — bounds every scrape to
# at most 1 (homepage) + MAX_ABOUT_PAGES requests, keeping jobs fast and the site lightly loaded.
_ABOUT_TEAM_PATHS = (
    "/about", "/about-us", "/team", "/our-team", "/leadership", "/company", "/people",
)
_MAX_ABOUT_PAGES = 2

_EMPLOYEE_COUNT_RE = re.compile(
    r"(\d{1,4}(?:,\d{3})?)\s*(?:-|to)\s*(\d{1,4}(?:,\d{3})?)\s*employees"
    r"|(?:team of|over|more than)\s*(\d{1,4}(?:,\d{3})?)\+?\s*employees"
    r"|(\d{1,4}(?:,\d{3})?)\+\s*employees",
    re.IGNORECASE,
)

# Only headings followed by one of these role keywords are treated as a decision-maker contact —
# a team page listing every employee shouldn't import every employee, only plausible sales
# targets.
_DECISION_MAKER_KEYWORDS = (
    "ceo", "cto", "coo", "cfo", "founder", "co-founder", "president", "vp",
    "vice president", "director", "head of", "owner", "manager",
)
_MAILTO_RE = re.compile(r"^mailto:", re.IGNORECASE)

# News/press and careers pages are fetched independently of the about/team candidates above —
# they serve a different purpose (buying signals, not firmographics/contacts) and all three are
# attempted rather than "first N found", since a site typically has at most one of news/press.
_SIGNAL_PATHS: dict[str, Literal["news", "job_posting"]] = {
    "/news": "news",
    "/press": "news",
    "/careers": "job_posting",
}
_MAX_SIGNALS_PER_PAGE = 10
_DATE_RE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}/\d{1,2}/\d{2,4}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)


class WebsiteScraperProvider(CompanyDataProvider, ContactDataProvider, SignalDataProvider):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            headers={"User-Agent": settings.scraper_user_agent},
            timeout=10.0,
            follow_redirects=True,
        )
        self._robots_cache: dict[str, robotparser.RobotFileParser] = {}
        self._last_request_at: dict[str, float] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _robots_allows(self, domain: str, path: str) -> bool:
        rp = self._robots_cache.get(domain)
        if rp is None:
            rp = robotparser.RobotFileParser()
            try:
                resp = await self._client.get(f"https://{domain}/robots.txt")
                rp.parse(resp.text.splitlines() if resp.status_code == 200 else [])
            except httpx.HTTPError:
                rp.parse([])  # unreachable robots.txt -> default allow, same as "no robots.txt"
            self._robots_cache[domain] = rp
        return rp.can_fetch(self._settings.scraper_user_agent, path)

    async def _throttle(self, domain: str) -> None:
        delay = self._settings.scraper_request_delay_seconds
        last = self._last_request_at.get(domain)
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < delay:
                await asyncio.sleep(delay - elapsed)
        self._last_request_at[domain] = time.monotonic()

    async def _fetch(self, domain: str, path: str) -> FetchedPage | None:
        if not await self._robots_allows(domain, path):
            logger.info("robots.txt disallows %s%s, skipping", domain, path)
            return None
        await self._throttle(domain)
        url = f"https://{domain}{path}"
        try:
            resp = await self._client.get(url)
        except httpx.HTTPError as exc:
            logger.info("fetch failed for %s: %s", url, exc)
            return None
        if resp.status_code != 200:
            return None
        return FetchedPage(url=url, status_code=resp.status_code, text=resp.text)

    async def fetch_company_data(self, domain: str) -> ScrapedCompanyData:
        homepage = await self._fetch(domain, "/")
        if homepage is None:
            raise ValueError(f"could not fetch homepage for {domain}")
        pages = [homepage]

        for path in _ABOUT_TEAM_PATHS:
            if len(pages) - 1 >= _MAX_ABOUT_PAGES:
                break
            page = await self._fetch(domain, path)
            if page is not None:
                pages.append(page)

        description = extract_description(homepage.text)
        employee_count_range = None
        for page in pages:
            employee_count_range = extract_employee_count(page.text)
            if employee_count_range:
                break

        return ScrapedCompanyData(
            description=description,
            employee_count_range=employee_count_range,
            industry=None,  # not reliably extractable heuristically — left for a future phase
            pages_fetched=pages,
        )

    async def fetch_contacts(
        self, domain: str, pages: list[FetchedPage]
    ) -> list[ScrapedContact]:
        contacts: list[ScrapedContact] = []
        for page in pages:
            contacts.extend(extract_contacts(page.text))
        return contacts

    async def fetch_signals(self, domain: str) -> list[ScrapedSignal]:
        signals: list[ScrapedSignal] = []
        for path, signal_type in _SIGNAL_PATHS.items():
            page = await self._fetch(domain, path)
            if page is None:
                continue
            extractor = (
                extract_job_signals if signal_type == "job_posting" else extract_news_signals
            )
            signals.extend(extractor(page.text, page.url))
        return signals


def extract_description(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    meta = soup.find("meta", attrs={"name": "description"})
    content = meta.get("content") if meta else None
    if isinstance(content, str) and content.strip():
        return content.strip()[:500]
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if len(text) >= 40:
            return text[:500]
    return None


def extract_employee_count(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    page_text = soup.get_text(" ", strip=True)
    match = _EMPLOYEE_COUNT_RE.search(page_text)
    if not match:
        return None
    low_high, high, single_plus, exact_plus = match.groups()
    if low_high and high:
        return f"{low_high.replace(',', '')}-{high.replace(',', '')}"
    if single_plus:
        return f"{single_plus.replace(',', '')}+"
    if exact_plus:
        return f"{exact_plus.replace(',', '')}+"
    return None


def extract_contacts(html: str) -> list[ScrapedContact]:
    soup = BeautifulSoup(html, "lxml")
    contacts: list[ScrapedContact] = []
    for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
        name = heading.get_text(strip=True)
        if not name or len(name.split()) > 5:
            continue

        role_el = heading.find_next_sibling()
        role = role_el.get_text(strip=True) if role_el else None
        if not role:
            continue
        # A real role title is a short phrase. A long blob here means the "next sibling" was
        # actually a nav/menu container, not a title — reject it rather than trying to save
        # unbounded text into a VARCHAR(255) column.
        if len(role) > 200:
            continue
        if not any(kw in role.lower() for kw in _DECISION_MAKER_KEYWORDS):
            continue

        # Only look for a mailto: link within this heading's immediate container, so we don't
        # grab an unrelated email from elsewhere on the page.
        container = heading.parent or heading
        mailto = container.find("a", href=_MAILTO_RE)
        href = mailto.get("href") if mailto else None
        email = href.split(":", 1)[1].strip() if isinstance(href, str) else None

        contacts.append(ScrapedContact(full_name=name, role_title=role, email=email or None))
    return contacts


def extract_news_signals(html: str, url: str) -> list[ScrapedSignal]:
    soup = BeautifulSoup(html, "lxml")
    signals: list[ScrapedSignal] = []
    seen: set[str] = set()

    for heading in soup.find_all(["h1", "h2", "h3", "article"]):
        # Pull a nested <time> out before reading the heading's text, so the date string
        # doesn't get appended onto the headline text itself.
        date: str | None = None
        time_el = heading.find("time")
        if time_el is not None:
            datetime_attr = time_el.get("datetime")
            date = (
                datetime_attr if isinstance(datetime_attr, str) else time_el.get_text(strip=True)
            )
            time_el.extract()
        else:
            sibling = heading.find_next_sibling("time")
            if sibling is not None:
                datetime_attr = sibling.get("datetime")
                date = (
                    datetime_attr
                    if isinstance(datetime_attr, str)
                    else sibling.get_text(strip=True)
                )

        text = heading.get_text(" ", strip=True)
        if not text or len(text) < 10 or len(text) > 200 or text in seen:
            continue
        seen.add(text)

        if not date:
            date_match = _DATE_RE.search(text)
            if date_match:
                date = date_match.group(0)

        signals.append(ScrapedSignal(signal_type="news", text=text, url=url, date=date))
        if len(signals) >= _MAX_SIGNALS_PER_PAGE:
            break
    return signals


# Many careers pages are culture/landing pages, not raw job lists, and are full of marketing
# copy ("We welcome differences.", "Help us build the future.") that reads structurally just
# like a job title (a short heading or list item). These are the cheap, real-world tells that
# separate a sentence from a title: sentences end in terminal punctuation, and marketing copy
# overwhelmingly opens with one of these words. Neither is foolproof — this stays best-effort.
_SENTENCE_END_RE = re.compile(r"[.!?…]$")
_SENTENCE_OPENER_STOPWORDS = frozenset(
    {"we", "our", "you", "your", "let's", "lets", "help", "more", "learn", "join", "cookie"}
)


def _looks_like_job_title(text: str) -> bool:
    if _SENTENCE_END_RE.search(text):
        return False
    first_word = text.split(" ", 1)[0].strip(",").lower()
    return first_word not in _SENTENCE_OPENER_STOPWORDS


def extract_job_signals(html: str, url: str) -> list[ScrapedSignal]:
    soup = BeautifulSoup(html, "lxml")
    signals: list[ScrapedSignal] = []
    seen: set[str] = set()

    # Careers pages vary a lot in structure — headings and list items both commonly hold job
    # titles. Everything found here already counts as a hiring signal (no role-keyword filter,
    # unlike decision-maker contact extraction), since it's already scoped to a careers page.
    for el in soup.find_all(["h1", "h2", "h3", "h4", "li", "a"]):
        if el.find_parent(["nav", "header", "footer"]):
            continue
        text = el.get_text(" ", strip=True)
        if not text or len(text) < 4 or len(text) > 120 or text in seen:
            continue
        if len(text.split()) > 10:  # too long to plausibly be a job title
            continue
        if not _looks_like_job_title(text):
            continue
        seen.add(text)
        signals.append(ScrapedSignal(signal_type="job_posting", text=text, url=url, date=None))
        if len(signals) >= _MAX_SIGNALS_PER_PAGE:
            break
    return signals
