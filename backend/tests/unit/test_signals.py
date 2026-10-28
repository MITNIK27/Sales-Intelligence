"""Signal normalization and the scraper's news extraction: real news in, page chrome out."""

from datetime import UTC, datetime

from app.modules.enrichment.providers.base import ScrapedSignal
from app.modules.enrichment.providers.website_scraper import extract_news_signals
from app.modules.enrichment.signals import (
    is_clean_payload,
    normalize_signals,
    normalize_title,
    parse_published,
)

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def _news(text: str, url: str = "https://n.example/a", date: str | None = None, label="x"):
    return ScrapedSignal(signal_type="news", text=text, url=url, date=date, source_label=label)


def test_navigation_text_is_not_a_signal() -> None:
    chrome = [
        _news("Track shipment"),
        _news("Go to homepage"),
        _news("What would you like to do?"),
        _news("Subscribe to our newsletter today"),
        _news("Track your parcel with our new tool"),  # starts with a nav word
    ]
    assert normalize_signals(chrome, NOW) == []


def test_gossip_is_dropped_but_business_news_stays() -> None:
    kept = _news("DPD opens a new automated hub in Lyon", date="2026-09-20")
    gossip = _news("Hermes heir files for divorce after merger talks", date="2026-09-21")
    assert normalize_signals([gossip, kept], NOW) == [kept]


def test_news_without_a_link_or_that_is_stale_is_dropped() -> None:
    no_link = _news("DPD opens a new automated hub in Lyon", url="")
    stale = _news("DPD opens an old warehouse in Spain", date="2023-01-05")
    fresh = _news("DPD signs a deal with a retailer", date="2026-08-01")
    assert normalize_signals([no_link, stale, fresh], NOW) == [fresh]


def test_same_story_from_two_providers_is_kept_once_preferring_the_dated_copy() -> None:
    from_scraper = _news("DPD opens a new automated hub in Lyon - Reuters", label="scraper")
    from_news = _news(
        "DPD opens a new automated hub in Lyon", date="2026-09-20", label="contextdev"
    )
    result = normalize_signals([from_scraper, from_news], NOW)
    assert len(result) == 1 and result[0].source_label == "contextdev"


def test_news_is_newest_first_and_capped() -> None:
    items = [
        _news(f"Company announces expansion number {i}", date=f"2026-0{i}-10")
        for i in range(1, 9)
    ]
    result = normalize_signals(items, NOW)
    assert len(result) == 5
    assert result[0].date == "2026-08-10" and result[-1].date == "2026-04-10"


def test_job_postings_are_kept_but_must_look_like_titles() -> None:
    jobs = [
        ScrapedSignal(signal_type="job_posting", text="Senior Logistics Engineer", url="u"),
        ScrapedSignal(signal_type="job_posting", text="Home", url="u"),
    ]
    assert [s.text for s in normalize_signals(jobs, NOW)] == ["Senior Logistics Engineer"]


def test_title_normalization_ignores_source_suffix_and_punctuation() -> None:
    assert normalize_title("DPD opens hub, in Lyon! - Reuters") == normalize_title(
        "dpd opens hub in lyon"
    )


def test_date_formats_from_real_sources() -> None:
    assert parse_published("2026-09-20T10:00:00Z") == datetime(2026, 9, 20, tzinfo=UTC)
    assert parse_published("March 12, 2026") == datetime(2026, 3, 12, tzinfo=UTC)
    assert parse_published("12th March 2026") == datetime(2026, 3, 12, tzinfo=UTC)
    assert parse_published("soon") is None and parse_published(None) is None


def test_stored_records_are_checked_with_the_same_rules() -> None:
    assert not is_clean_payload({"signal_type": "news", "text": "Track now"})
    assert is_clean_payload({"signal_type": "news", "text": "DPD opens a new hub in Lyon"})


# -- the scraper's own extraction -------------------------------------------------------------

_PAGE = """
<html><body>
<header><h2>Track shipment</h2></header>
<nav><h3>Go to homepage</h3></nav>
<main>
  <article>
    <h2><a href="/news/lyon-hub">DPD opens a new automated hub in Lyon</a></h2>
    <time datetime="2026-09-20">20 Sep 2026</time>
  </article>
  <h3>Track now</h3>
  <h3>What would you like to do?</h3>
</main>
<footer><h3>Subscribe to our newsletter</h3></footer>
</body></html>
"""


def test_scraper_ignores_menu_headings_and_links_to_the_article() -> None:
    signals = extract_news_signals(_PAGE, "https://dpd.com/press")
    texts = [s.text for s in signals]
    assert "DPD opens a new automated hub in Lyon" in texts
    assert not any(t in texts for t in ("Track shipment", "Go to homepage", "Track now"))
    assert not any("Subscribe" in t or "What would you like" in t for t in texts)
    hub = next(s for s in signals if s.text.startswith("DPD opens"))
    assert hub.url == "https://dpd.com/news/lyon-hub"
    assert hub.date == "2026-09-20"
