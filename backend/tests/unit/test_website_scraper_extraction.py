from app.modules.enrichment.providers.website_scraper import (
    extract_contacts,
    extract_description,
    extract_employee_count,
    extract_job_signals,
    extract_news_signals,
)

HOMEPAGE_HTML = """
<html><head>
<meta name="description" content="Acme builds rockets for small businesses.">
</head><body><p>Welcome to Acme.</p></body></html>
"""

NO_META_HTML = """
<html><body>
<p>Short.</p>
<p>Acme Inc has been building high quality widgets for over a decade, serving thousands of
customers.</p>
</body></html>
"""

EMPLOYEE_COUNT_HTML = """
<html><body><p>We are a team of 50 employees spread across three offices.</p></body></html>
"""

EMPLOYEE_RANGE_HTML = """
<html><body><p>Acme currently has 500-1000 employees worldwide.</p></body></html>
"""

NEWS_PAGE_HTML = """
<html><body>
<h2>Acme raises $10M Series A <time datetime="2026-01-15">Jan 15, 2026</time></h2>
<h2>Acme opens new Bangalore office</h2>
<h2>Hi</h2>
</body></html>
"""

CAREERS_PAGE_HTML = """
<html><body>
<nav><a href="/">Home</a><a href="/about">About</a></nav>
<ul>
  <li>Senior Sales Ops Manager</li>
  <li>Backend Engineer</li>
</ul>
<h3>We welcome differences.</h3>
<h3>Let's reclaim the internet together.</h3>
<p>Cookie settings</p>
</body></html>
"""

TEAM_PAGE_HTML = """
<html><body>
<div>
  <h3>Jane Doe</h3>
  <p>CEO &amp; Co-Founder</p>
  <a href="mailto:jane@acme.com">Email Jane</a>
</div>
<div>
  <h3>Bob Smith</h3>
  <p>Warehouse Associate</p>
</div>
<div>
  <h3>Not A Person Heading With Way Too Many Words In It</h3>
  <p>Director</p>
</div>
</body></html>
"""


def test_extract_description_prefers_meta_tag() -> None:
    assert extract_description(HOMEPAGE_HTML) == "Acme builds rockets for small businesses."


def test_extract_description_falls_back_to_first_substantial_paragraph() -> None:
    result = extract_description(NO_META_HTML)
    assert result is not None
    assert "Acme Inc has been building" in result


def test_extract_employee_count_single_plus_pattern() -> None:
    assert extract_employee_count(EMPLOYEE_COUNT_HTML) == "50+"


def test_extract_employee_count_range_pattern() -> None:
    assert extract_employee_count(EMPLOYEE_RANGE_HTML) == "500-1000"


def test_extract_employee_count_returns_none_when_no_match() -> None:
    assert extract_employee_count("<p>No numbers here.</p>") is None


def test_extract_contacts_filters_to_decision_maker_roles_and_captures_email() -> None:
    contacts = extract_contacts(TEAM_PAGE_HTML)

    names = {c.full_name for c in contacts}
    assert "Jane Doe" in names
    assert "Bob Smith" not in names  # not a decision-maker role keyword

    jane = next(c for c in contacts if c.full_name == "Jane Doe")
    assert jane.role_title == "CEO & Co-Founder"
    assert jane.email == "jane@acme.com"

    # heading text too long to plausibly be a person's name is skipped
    assert "Not A Person Heading With Way Too Many Words In It" not in names


def test_extract_news_signals_captures_headline_and_date() -> None:
    signals = extract_news_signals(NEWS_PAGE_HTML, "https://acme.com/press")

    texts = {s.text: s for s in signals}
    assert "Acme raises $10M Series A" in texts
    assert texts["Acme raises $10M Series A"].date == "2026-01-15"
    assert texts["Acme raises $10M Series A"].signal_type == "news"
    assert "Acme opens new Bangalore office" in texts
    # too short to plausibly be a headline
    assert "Hi" not in texts


def test_extract_job_signals_captures_listings_and_skips_nav_links() -> None:
    signals = extract_job_signals(CAREERS_PAGE_HTML, "https://acme.com/careers")

    texts = {s.text for s in signals}
    assert "Senior Sales Ops Manager" in texts
    assert "Backend Engineer" in texts
    assert "Home" not in texts
    assert "About" not in texts
    # marketing copy that reads structurally like a title gets filtered out
    assert "We welcome differences." not in texts
    assert "Let's reclaim the internet together." not in texts
    assert "Cookie settings" not in texts
    assert all(s.signal_type == "job_posting" for s in signals)
