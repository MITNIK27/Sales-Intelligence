"""Turns the evidence about one company into the short answer. The model writes the words and
suggests which offerings fit; this code decides what is trusted: an offering must be one of ours,
and a fit counts only when its quote is really in the evidence it cites. The yes/maybe/no call is
computed here from what survived, so a confident model cannot talk its way to a "yes" without
proof on the company's own site."""

import hashlib
from dataclasses import dataclass
from typing import Any

from app.modules.llm.structured import StructuredLLM
from app.modules.qualification.evidence import quote_is_in_source
from app.modules.quicklook.prompts import (
    BANDS,
    PROMPT_VERSION,
    VERDICTS,
    QuickLookOut,
    build_quicklook_prompt,
)

THIN_EVIDENCE_CHARS = 300
MAX_OFFERINGS = 3
MAX_WORKING_ON = 4
KIND_SITE = "site"
KIND_SEARCH = "search"
KIND_NEWS = "news"
KIND_HIRING = "hiring"
# Where a proven fit may come from for a "yes": the company's own words, a dated news item, or an
# open job. A search snippet alone can only support a "maybe".
_STRONG_SOURCES = (KIND_SITE, KIND_NEWS, KIND_HIRING)

CALL_YES, CALL_MAYBE, CALL_NO, CALL_UNCLEAR = "yes", "maybe", "no", "unclear"
_CALL_REASON = {
    CALL_YES: "Their own site, recent news or an open job points to a need one of our offerings "
    "serves.",
    CALL_MAYBE: "There is a plausible link to our offerings, but not enough to be sure.",
    CALL_NO: "Nothing found points to a need yet. That is not proof they have none.",
    CALL_UNCLEAR: "Not enough could be found about this company to say.",
}
_BAND_RANK = {band: i for i, band in enumerate(BANDS)}


@dataclass(frozen=True)
class Evidence:
    label: str  # E1, E2, ... as the model sees it
    url: str
    kind: str  # site | search | news | hiring
    text: str
    date: str | None = None  # as the source gave it; None when it states none


@dataclass(frozen=True)
class OfferingRef:
    label: str  # O1, O2, ... as the model sees it
    product_id: str
    name: str
    description: str


def offerings_fingerprint(
    offerings: list[OfferingRef], focus: str | None = None, criteria: list[str] | None = None
) -> str:
    """What a snapshot was judged against: our offerings, the person's extras, and the prompt. A
    look-up with different extras is a different answer, so it is not served from this cache."""
    raw = "|".join(f"{o.product_id}:{o.name}:{o.description}" for o in offerings)
    extras = f"{focus or ''}#{'|'.join(criteria or [])}"
    return hashlib.sha256(f"{PROMPT_VERSION}#{raw}#{extras}".encode()).hexdigest()


def _format_evidence(evidence: list[Evidence]) -> str:
    return "\n\n".join(
        f"[{e.label}] {e.kind}{f' dated {e.date}' if e.date else ''} ({e.url})\n{e.text}"
        for e in evidence
    )


def _format_offerings(offerings: list[OfferingRef]) -> str:
    return "\n".join(f"[{o.label}] {o.name}: {o.description[:200]}" for o in offerings)


def _verified_offerings(
    answer: QuickLookOut, evidence: list[Evidence], offerings: list[OfferingRef]
) -> list[dict[str, Any]]:
    by_evidence = {e.label: e for e in evidence}
    by_offering = {o.label: o for o in offerings}
    picked: dict[str, dict[str, Any]] = {}
    for item in answer.offerings:
        offering = by_offering.get((item.offering or "").strip().upper())
        band = (item.band or "").strip().lower()
        if offering is None or band not in _BAND_RANK or offering.label in picked:
            continue
        source = by_evidence.get((item.evidence or "").strip().upper())
        quote = item.quote or ""
        verified = source is not None and bool(quote) and quote_is_in_source(quote, source.text)
        if band != "weak" and not verified:
            band = "weak"  # a fit with no proof behind it is only a stretch
        picked[offering.label] = {
            "product_id": offering.product_id,
            "name": offering.name,
            "band": band,
            "reason": item.reason.strip()[:300],
            "quote": item.quote.strip() if verified and item.quote else None,
            "source_url": source.url if verified and source else None,
            "source_kind": source.kind if verified and source else None,
            "source_date": source.date if verified and source else None,
            # What we would offer is shown only when its evidence is real.
            "idea": (item.idea or "").strip()[:300] or None if verified else None,
            "why_now": (item.why_now or "").strip()[:300] or None if verified else None,
        }
    ordered = sorted(picked.values(), key=lambda o: _BAND_RANK[o["band"]])
    return ordered[:MAX_OFFERINGS]


def _verified_working_on(answer: QuickLookOut, evidence: list[Evidence]) -> list[dict[str, Any]]:
    """What the company is doing, kept only when the quote is really in the evidence it cites."""
    by_evidence = {e.label: e for e in evidence}
    points: list[dict[str, Any]] = []
    for item in answer.working_on:
        source = by_evidence.get((item.evidence or "").strip().upper())
        quote = (item.quote or "").strip()
        if source is None or not quote or not quote_is_in_source(quote, source.text):
            continue
        if not item.point.strip():
            continue
        points.append(
            {
                "point": item.point.strip()[:300],
                "quote": quote,
                "source_url": source.url,
                "source_kind": source.kind,
                "source_date": source.date,
            }
        )
    return points[:MAX_WORKING_ON]


def decide_call(picks: list[dict[str, Any]], evidence_chars: int) -> str:
    # A fit proven by a real quote from their own site, a dated news item or an open job is proof
    # however little else was found; anything weaker needs enough evidence behind it.
    if any(p["band"] == "strong" and p["source_kind"] in _STRONG_SOURCES for p in picks):
        return CALL_YES
    if evidence_chars < THIN_EVIDENCE_CHARS:
        return CALL_UNCLEAR
    if any(p["band"] in ("strong", "potential") for p in picks):
        return CALL_MAYBE
    return CALL_NO


def _checked_criteria(
    answer: QuickLookOut, evidence: list[Evidence], criteria: list[str]
) -> list[dict[str, Any]]:
    """One entry per criterion the person gave, in their order. These are for information only:
    a met or not-met verdict counts only when its quote is really in the evidence it cites,
    otherwise it is "unknown". Nothing here feeds the call."""
    by_evidence = {e.label: e for e in evidence}
    by_label = {(c.criterion or "").strip().upper(): c for c in answer.criteria}
    checked: list[dict[str, Any]] = []
    for index, name in enumerate(criteria, start=1):
        item = by_label.get(f"C{index}")
        entry: dict[str, Any] = {
            "name": name,
            "verdict": "unknown",
            "reason": "The evidence found does not say.",
            "quote": None,
            "source_url": None,
        }
        if item is not None:
            source = by_evidence.get((item.evidence or "").strip().upper())
            quote = (item.quote or "").strip()
            verdict = (item.verdict or "").strip().lower()
            proven = source is not None and bool(quote) and quote_is_in_source(quote, source.text)
            if verdict in VERDICTS and verdict != "unknown" and proven and source is not None:
                entry.update(verdict=verdict, quote=quote, source_url=source.url)
            entry["reason"] = item.reason.strip()[:300] or entry["reason"]
        checked.append(entry)
    return checked


def empty_summary(
    name: str, note: str, criteria: list[str] | None = None, focus: str | None = None
) -> dict[str, Any]:
    return {
        "name": name,
        "what_they_do": None,
        "industry": None,
        "size_hint": None,
        "relevance": None,
        "call": CALL_UNCLEAR,
        "call_reason": _CALL_REASON[CALL_UNCLEAR],
        "offerings": [],
        "working_on": [],
        "focus": focus,
        "criteria": [
            {
                "name": c,
                "verdict": "unknown",
                "reason": "Nothing could be read about this company.",
                "quote": None,
                "source_url": None,
            }
            for c in criteria or []
        ],
        "notes": [note],
    }


async def build_summary(
    llm: StructuredLLM,
    name: str,
    domain: str,
    evidence: list[Evidence],
    offerings: list[OfferingRef],
    criteria: list[str] | None = None,
    focus: str | None = None,
) -> dict[str, Any]:
    criteria = criteria or []
    chars = sum(len(e.text) for e in evidence)
    if not evidence:
        return empty_summary(name, "Nothing could be read about this company.", criteria, focus)
    criteria_text = "\n".join(f"[C{i}] {c}" for i, c in enumerate(criteria, start=1))
    answer = await llm.generate(
        build_quicklook_prompt(
            name,
            domain,
            _format_evidence(evidence),
            _format_offerings(offerings),
            criteria_text,
            focus,
        ),
        QuickLookOut,
    )
    picks = _verified_offerings(answer, evidence, offerings)
    call = decide_call(picks, chars)
    notes: list[str] = []
    if chars < THIN_EVIDENCE_CHARS:
        notes.append("Very little was found about this company, so the call is unclear.")
    reason = answer.call_reason.strip()[:300]
    agreed = call == answer.call.strip().lower() and bool(reason)
    return {
        "name": answer.company_name.strip() or name,
        "what_they_do": answer.what_they_do.strip(),
        "industry": (answer.industry or "").strip() or None,
        "size_hint": (answer.size_hint or "").strip() or None,
        "relevance": answer.relevance.strip(),
        "call": call,
        "call_reason": reason if agreed else _CALL_REASON[call],
        "offerings": picks,
        "working_on": _verified_working_on(answer, evidence),
        "focus": focus,
        "criteria": _checked_criteria(answer, evidence, criteria),
        "notes": notes,
    }
