"""Signal normalization: turns the raw items the scraper and context.dev produce into a short list
of genuine business signals. Pure functions, no I/O.

    scraper + context.dev items -> drop page chrome and gossip -> require a link -> drop stale news
    -> de-duplicate across providers -> newest first -> keep the best few

The scraper reads headings off news/careers pages and cannot tell a headline from a menu entry
("Track shipment", "Go to homepage"); context.dev returns real articles but some are personal
gossip. Both are filtered by the same deterministic rules here, so nothing downstream (the
qualification prompt, the Priority Score, drafts) ever sees navigation text as a "signal"."""

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from app.modules.enrichment.providers.base import ScrapedSignal

MIN_NEWS_WORDS = 4
MAX_NEWS_AGE_DAYS = 365
MAX_NEWS_KEPT = 5
MAX_JOBS_KEPT = 5

# Page chrome the heading extractor mistakes for headlines. A signal that starts with one of these
# is a menu/button/banner, not company news.
NAV_PHRASES = (
    "track", "go to homepage", "homepage", "log in", "login", "sign in", "sign up", "subscribe",
    "contact us", "cookie", "privacy", "accept all", "what would you like to do", "skip to",
    "menu", "search", "my account", "get a quote", "find a", "read more", "learn more",
    "back to", "share", "follow us", "newsletter", "press contact", "media contact",
)

# Personal or off-topic stories that mention a company only because of a person. Kept
# deliberately small: legal and financial news about the business itself stays.
LOW_VALUE_PHRASES = (
    "divorce", "obituary", "passed away", "scandal", "affair", "horoscope", "celebrity",
)

_ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATE_FORMATS = ("%d %B %Y", "%B %d, %Y", "%b %d, %Y", "%d %b %Y", "%d.%m.%Y", "%d/%m/%Y")
_SOURCE_SUFFIX_RE = re.compile(r"\s+[-|–—]\s+[^-|–—]{2,40}$")


def parse_published(value: str | None) -> datetime | None:
    """Best-effort publication date from the formats the sources actually emit."""
    if not value:
        return None
    iso = _ISO_RE.search(value)
    if iso:
        try:
            return datetime.fromisoformat(iso.group(0)).replace(tzinfo=UTC)
        except ValueError:
            return None
    cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", value.strip(), flags=re.I)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def normalize_title(text: str) -> str:
    """Key for "same story": lowercase, source suffix ("... - Reuters") dropped, punctuation and
    spacing collapsed — so two providers reporting one headline collapse to one item."""
    stripped = _SOURCE_SUFFIX_RE.sub("", text.strip())
    return re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()


def _is_chrome(text: str) -> bool:
    lowered = text.strip().lower()
    return any(lowered.startswith(phrase) for phrase in NAV_PHRASES)


def is_clean_text(signal_type: str, text: str) -> bool:
    """Text-level check shared by fresh signals and already-stored records."""
    text = text.strip()
    if not text or _is_chrome(text):
        return False
    lowered = text.lower()
    if any(phrase in lowered for phrase in LOW_VALUE_PHRASES):
        return False
    if signal_type == "news":
        return len(text.split()) >= MIN_NEWS_WORDS
    return len(text.split()) >= 2  # a job title is at least "Software Engineer"


def is_clean_signal(signal: ScrapedSignal) -> bool:
    return is_clean_text(signal.signal_type, signal.text)


def is_fresh(published: datetime | None, now: datetime) -> bool:
    """Undated news is allowed (many pages carry no date); dated news must be recent."""
    return published is None or (now - published) <= timedelta(days=MAX_NEWS_AGE_DAYS)


def normalize_signals(
    signals: list[ScrapedSignal], now: datetime | None = None
) -> list[ScrapedSignal]:
    """The cleaned, de-duplicated, newest-first list that gets stored and shown."""
    now = now or datetime.now(UTC)
    news: dict[str, tuple[datetime | None, ScrapedSignal]] = {}
    jobs: dict[str, ScrapedSignal] = {}

    for signal in signals:
        if not is_clean_signal(signal):
            continue
        key = normalize_title(signal.text)
        if not key:
            continue
        if signal.signal_type == "job_posting":
            jobs.setdefault(key, signal)
            continue
        if not signal.url:
            continue  # news we cannot point to is not usable as evidence
        published = parse_published(signal.date)
        if not is_fresh(published, now):
            continue
        existing = news.get(key)
        # Same story from two providers: keep the dated one (it can be ranked by recency).
        if existing is None or (existing[0] is None and published is not None):
            news[key] = (published, signal)

    floor = datetime.min.replace(tzinfo=UTC)
    ordered = sorted(news.values(), key=lambda item: item[0] or floor, reverse=True)
    return [s for _, s in ordered[:MAX_NEWS_KEPT]] + list(jobs.values())[:MAX_JOBS_KEPT]


def is_clean_payload(payload: dict[str, Any]) -> bool:
    """Filter for signal records stored before normalization existed (or by other code paths)."""
    return is_clean_text(str(payload.get("signal_type") or "news"), str(payload.get("text") or ""))
