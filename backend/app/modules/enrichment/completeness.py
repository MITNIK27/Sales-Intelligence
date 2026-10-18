"""Decides whether what the free scraper found is enough, or context.dev (which costs credits)
should fill gaps. Pure functions, no I/O — so the policy is one readable place and unit-testable.

Sufficient company data = a real description AND at least one of industry / employee range.
Sufficient signals = enough genuine news-like items (not menu text). Anything short of that is a
*gap*, and only the gap is paid for: a brand lookup when firmographics are thin, a news lookup
when there are too few usable signals — never both for a company that already has them."""

from app.modules.enrichment.providers.base import ScrapedCompanyData, ScrapedSignal
from app.modules.enrichment.signals import is_clean_signal

MIN_DESCRIPTION_CHARS = 80
MIN_CLEAN_SIGNALS = 2


def has_real_description(data: ScrapedCompanyData) -> bool:
    return bool(data.description and len(data.description.strip()) >= MIN_DESCRIPTION_CHARS)


def missing_company_fields(data: ScrapedCompanyData) -> set[str]:
    """The firmographic fields that are absent or too thin to rely on."""
    missing: set[str] = set()
    if not has_real_description(data):
        missing.add("description")
    if not data.industry:
        missing.add("industry")
    if not data.employee_count_range:
        missing.add("employee_count_range")
    return missing


def company_data_is_sufficient(data: ScrapedCompanyData) -> bool:
    """A real description plus industry OR employee range. Industry alone is not demanded:
    the scraper almost never finds it, and insisting on it would mean paying for every company."""
    return has_real_description(data) and bool(data.industry or data.employee_count_range)


def signals_are_sufficient(signals: list[ScrapedSignal]) -> bool:
    return sum(1 for s in signals if is_clean_signal(s)) >= MIN_CLEAN_SIGNALS
