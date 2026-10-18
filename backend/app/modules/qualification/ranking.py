"""Priority Score — how strong a sales opportunity a company is. Pure functions, no I/O.

Same principle as the verdict (ADR 0005/0013): the LLM judges individual criteria, Python
computes everything derived from them, so a score is auditable and reproducible.

Seven components, each normalized to 0..1 and weighted (weights sum to 100). Missing data is not
treated as "bad": it scores a neutral-low `UNKNOWN_VALUE` (0.3), so a company is never ranked
down for what we failed to find as hard as for what we found to be wrong. The weighted sum is then
scaled by an evidence factor (0.7 .. 1.0) from the weakest hard-criterion confidence, so a
well-evidenced company beats one that merely has more data. A hard FAIL excludes the company
(score 0) no matter how strong the rest looks.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.modules.enrichment.signals import parse_published
from app.modules.qualification.evidence import FAIL, PASS, UNKNOWN, overall_confidence

WEIGHTS: dict[str, float] = {
    "market_fit": 35,
    "company_size": 15,
    "industry_relevance": 15,
    "business_signals": 10,
    "recent_news": 10,
    "technology_maturity": 5,
    "contact_availability": 10,
}
UNKNOWN_VALUE = 0.3
DEFAULT_PASS_CONFIDENCE = 0.7  # a PASS whose confidence the model didn't give
DEFAULT_EVIDENCE_CONFIDENCE = 0.5  # no hard criterion carried a confidence at all
_TECH_WORDS = ("digital", "technology", "tech ", "it maturity", "automation")


@dataclass
class RankInputs:
    criteria_results: list[dict[str, Any]]
    industry: str | None = None
    description: str | None = None
    employee_count_range: str | None = None
    requested_keywords: list[str] = field(default_factory=list)
    requested_size: str | None = None
    signal_dates: list[str | None] = field(default_factory=list)  # one entry per clean signal
    contact_count: int = 0
    contacts_with_linkedin: int = 0
    now: datetime | None = None


@dataclass
class RankResult:
    score: float
    excluded: bool
    breakdown: dict[str, Any]


def parse_size_range(text: str | None) -> tuple[float, float] | None:
    """"1,000-10,000" -> (1000, 10000); "10000+" -> (10000, inf); "50" -> (50, 50)."""
    if not text:
        return None
    cleaned = text.lower().replace(",", "").replace("–", "-").replace("—", "-")
    numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", cleaned)]
    if not numbers:
        return None
    if "+" in cleaned or "over" in cleaned or "more than" in cleaned:
        return numbers[0], float("inf")
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    return min(numbers[:2]), max(numbers[:2])


def _size_value(company: str | None, requested: str | None) -> tuple[float, str]:
    have = parse_size_range(company)
    want = parse_size_range(requested)
    if have is None:
        return UNKNOWN_VALUE, "employee count unknown"
    if want is None:
        return 0.5, "known size, no size requested"
    (lo, hi), (wlo, whi) = have, want
    if lo >= wlo and hi <= whi:
        return 1.0, "inside the requested range"
    if lo <= whi and hi >= wlo:
        return 0.7, "overlaps the requested range"
    # Disjoint: within 2x of the nearest boundary is still plausible, further is not.
    if hi < wlo:
        ratio = wlo / hi if hi > 0 else 99.0
    else:
        ratio = lo / whi if whi > 0 else 99.0
    if ratio <= 2:
        return 0.4, "just outside the requested range"
    return 0.1, "far from the requested range"


def _keyword_tokens(keywords: list[str]) -> list[str]:
    tokens: list[str] = []
    for keyword in keywords:
        tokens.extend(t for t in re.split(r"[^a-z0-9]+", keyword.lower()) if len(t) >= 4)
    return tokens


def _industry_value(
    industry: str | None, description: str | None, keywords: list[str]
) -> tuple[float, str]:
    tokens = _keyword_tokens(keywords)
    if not tokens:
        return (0.5, "no industry requested") if industry else (UNKNOWN_VALUE, "industry unknown")
    if industry and any(t in industry.lower() for t in tokens):
        return 1.0, "industry matches the search"
    if description and any(t in description.lower() for t in tokens):
        return 0.7, "description matches the search"
    if industry:
        return 0.3, "industry does not obviously match"
    return UNKNOWN_VALUE, "industry unknown"


def _news_value(dates: list[str | None], now: datetime) -> tuple[float, str]:
    parsed = [d for d in (parse_published(x) for x in dates) if d is not None]
    if not parsed:
        return 0.0, "no dated news"
    age_days = (now - max(parsed)).days
    if age_days <= 90:
        return 1.0, "news in the last 90 days"
    if age_days <= 365:
        return 0.5, "news in the last year"
    return 0.0, "only old news"


def _market_fit_value(criteria: list[dict[str, Any]]) -> tuple[float, bool, str]:
    """(value, excluded, note). Averages the hard criteria: PASS counts its confidence, UNKNOWN
    counts `UNKNOWN_VALUE`; any FAIL excludes."""
    hard = [c for c in criteria if c.get("is_disqualifying")]
    if not hard:
        return UNKNOWN_VALUE, False, "no hard requirements to verify"
    values: list[float] = []
    for c in hard:
        status = c.get("status") or UNKNOWN
        if status == FAIL:
            return 0.0, True, f"fails hard requirement: {c.get('criterion_name')}"
        if status == PASS:
            confidence = c.get("confidence")
            values.append(float(confidence) if confidence is not None else DEFAULT_PASS_CONFIDENCE)
        else:
            values.append(UNKNOWN_VALUE)
    return sum(values) / len(values), False, f"{len(hard)} hard requirement(s)"


def _tech_value(criteria: list[dict[str, Any]]) -> tuple[float, str]:
    for c in criteria:
        name = f"{c.get('criterion_name', '')} ".lower()
        if not c.get("is_disqualifying") and any(w in name for w in _TECH_WORDS):
            status = c.get("status") or UNKNOWN
            value = {PASS: 1.0, FAIL: 0.0}.get(status, UNKNOWN_VALUE)
            return value, f"{c.get('criterion_name')}: {status}"
    return UNKNOWN_VALUE, "no technology criterion"


def compute_priority(inputs: RankInputs) -> RankResult:
    now = inputs.now or datetime.now(UTC)
    fit, excluded, fit_note = _market_fit_value(inputs.criteria_results)
    if excluded:
        return RankResult(0.0, True, {"excluded": fit_note})

    size, size_note = _size_value(inputs.employee_count_range, inputs.requested_size)
    industry, industry_note = _industry_value(
        inputs.industry, inputs.description, inputs.requested_keywords
    )
    signals = min(len(inputs.signal_dates), 3) / 3
    news, news_note = _news_value(inputs.signal_dates, now)
    tech, tech_note = _tech_value(inputs.criteria_results)
    if inputs.contacts_with_linkedin > 0:
        contacts, contacts_note = 1.0, "a contact with a LinkedIn profile"
    elif inputs.contact_count > 0:
        contacts, contacts_note = 0.5, "contacts found, no LinkedIn profile"
    else:
        contacts, contacts_note = 0.0, "no contacts found"

    values = {
        "market_fit": (fit, fit_note),
        "company_size": (size, size_note),
        "industry_relevance": (industry, industry_note),
        "business_signals": (signals, f"{len(inputs.signal_dates)} signal(s)"),
        "recent_news": (news, news_note),
        "technology_maturity": (tech, tech_note),
        "contact_availability": (contacts, contacts_note),
    }
    raw = sum(WEIGHTS[name] * value for name, (value, _) in values.items())

    confidence = overall_confidence(inputs.criteria_results)
    used = DEFAULT_EVIDENCE_CONFIDENCE if confidence is None else confidence
    evidence_factor = 0.7 + 0.3 * used
    score = round(raw * evidence_factor, 1)

    return RankResult(
        score=score,
        excluded=False,
        breakdown={
            "components": {
                name: {
                    "weight": WEIGHTS[name],
                    "value": round(value, 2),
                    "points": round(WEIGHTS[name] * value, 1),
                    "note": note,
                }
                for name, (value, note) in values.items()
            },
            "evidence_factor": round(evidence_factor, 2),
            "raw": round(raw, 1),
        },
    )
