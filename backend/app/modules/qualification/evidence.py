"""Evidence handling for qualification — pure functions, no I/O.

The judging model must cite WHAT it relied on: a source reference (a company field such as
`company.description`, or a numbered signal such as `S2`) plus a verbatim quote. The prompt only
asks for that; this module enforces it. A "met"/"not_met" whose quote cannot be found in the cited
source is not trusted and becomes "could_not_determine" — an unverifiable claim must never turn
into a PASS or FAIL ("no negative evidence" is not evidence).

Source numbering (`S1`..) is shared with the prompt builder through `numbered_signals`, so the
reference the model sees is the reference checked here."""

import re
from typing import Any

from app.modules.companies.models import Company
from app.modules.enrichment.models import EnrichmentRecord

MAX_SIGNALS_IN_PROMPT = 10

COMPANY_FIELD_REFS = (
    "company.name",
    "company.domain",
    "company.industry",
    "company.employee_count_range",
    "company.description",
)

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
_STATUS_BY_VERDICT = {"met": PASS, "not_met": FAIL, "could_not_determine": UNKNOWN}


def status_for_verdict(verdict: str) -> str:
    return _STATUS_BY_VERDICT.get(verdict, UNKNOWN)


def numbered_signals(signals: list[EnrichmentRecord]) -> list[tuple[str, EnrichmentRecord]]:
    """The signals the model is shown, with the reference ids it must cite them by."""
    return [(f"S{i}", record) for i, record in enumerate(signals[:MAX_SIGNALS_IN_PROMPT], start=1)]


def company_field_texts(company: Company) -> dict[str, str]:
    return {
        "company.name": company.name or "",
        "company.domain": company.domain or "",
        "company.industry": company.industry or "",
        "company.employee_count_range": company.employee_count_range or "",
        "company.description": company.description or "",
    }


def evidence_sources(company: Company, signals: list[EnrichmentRecord]) -> dict[str, str]:
    sources = dict(company_field_texts(company))
    for ref, record in numbered_signals(signals):
        sources[ref] = str((record.raw_payload or {}).get("text", ""))
    return sources


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def quote_is_in_source(quote: str, source_text: str) -> bool:
    """True when the quote appears verbatim (ignoring case/whitespace) in the source. A quote
    with ellipses ("a ... b") is accepted when every fragment appears; fragments under 3
    characters are ignored so "..." alone cannot pass."""
    haystack = _normalize(source_text)
    fragments = [_normalize(part) for part in re.split(r"\.\.\.|…", quote)]
    fragments = [f for f in fragments if len(f) >= 3]
    return bool(fragments) and all(f in haystack for f in fragments)


def verify_evidence(
    verdict: str, evidence_ref: str | None, evidence_quote: str | None, sources: dict[str, str]
) -> tuple[bool, str | None]:
    """Returns (trusted, problem). UNKNOWN needs no evidence; PASS/FAIL need a real citation."""
    if verdict == "could_not_determine":
        return True, None
    if not evidence_ref or not evidence_quote:
        return False, "no evidence was cited"
    ref = evidence_ref.strip()
    if ref not in sources:
        return False, f"cited source {ref!r} does not exist"
    if not quote_is_in_source(evidence_quote, sources[ref]):
        return False, "the quoted evidence does not appear in the cited source"
    return True, None


def describe_source(ref: str | None, signals: list[EnrichmentRecord]) -> dict[str, Any]:
    """Human-facing origin of a cited reference, for the "why qualified" view."""
    if not ref:
        return {"source": None, "url": None}
    if ref.startswith("company."):
        return {"source": "company profile", "url": None}
    for signal_ref, record in numbered_signals(signals):
        if signal_ref == ref:
            if record.source.startswith("contextdev"):
                origin = "context.dev news"
            elif record.source.startswith("serper"):
                origin = "web search"
            else:
                origin = "website"
            return {"source": origin, "url": (record.raw_payload or {}).get("url")}
    return {"source": None, "url": None}


def overall_confidence(criteria_results: list[dict[str, Any]]) -> float | None:
    """Conservative: the weakest confidence among the hard criteria that have one. A company is
    only as certain as its least certain hard requirement."""
    values = [
        float(c["confidence"])
        for c in criteria_results
        if c.get("is_disqualifying") and c.get("confidence") is not None
    ]
    return min(values) if values else None
