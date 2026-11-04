"""How well each offering fits a company in an area. The model explains each fit and cites evidence;
code verifies every citation and computes the band and score from explicit factors, so a fit is
never "strong" just because the model said so. An offering is judged again only when something it
depends on has changed."""

import logging
import re
from collections.abc import Iterable

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.enrichment.models import EnrichmentRecord
from app.modules.llm.structured import StructuredLLM
from app.modules.llm.untrusted import untrusted_aware, wrap_untrusted
from app.modules.opportunity.assessment import model_names
from app.modules.opportunity.evidence import (
    EvidenceItem,
    build_evidence_pack,
    evidence_set_hash,
    format_evidence,
    stored_citation,
    verify_citation,
)
from app.modules.opportunity.models import (
    BAND_INSUFFICIENT,
    BAND_POTENTIAL,
    BAND_STRONG,
    BAND_WEAK,
    VERDICT_EMERGING,
    VERDICT_SUPPORTED,
    VERDICT_WEAK,
    CompanyOpportunity,
    OpportunityAssessment,
    OpportunityOfferingMatch,
)
from app.modules.opportunity.service import latest_assessment
from app.modules.opportunity.shortlist import area_alignment, keyword_hits
from app.modules.products.models import Product

logger = logging.getLogger(__name__)

FIT_PROMPT_VERSION = "v2"
NO_EVIDENCE_REASON = "There is no evidence on file to judge this fit."
# For an offering the model gave no answer about: nothing in the evidence points to a need for it.
NOT_ANSWERED_REASON = "The research shows no need for this offering."
_MAX_REASONING = 600
_MAX_CITATIONS = 3

# Points toward the 0-100 score; the band is decided by rules (below), the score is for ordering.
_EVIDENCE_POINTS = {0: 0, 1: 20, 2: 35, 3: 50}
_ALIGNMENT_POINTS = 20
_KEYWORD_POINTS_EACH, _KEYWORD_POINTS_MAX = 5, 3
_VERDICT_POINTS = {VERDICT_SUPPORTED: 15, VERDICT_EMERGING: 10, VERDICT_WEAK: 5}


class FitCitation(BaseModel):
    evidence: str  # evidence label, for example E3
    quote: str  # a short verbatim quote from it


class OfferingFitOut(BaseModel):
    offering: str  # offering label, for example O2
    reasoning: str  # why it fits, or does not, in one or two sentences
    evidence: list[FitCitation] = []


class FitOut(BaseModel):
    offerings: list[OfferingFitOut] = []


_RETRY_NOTE = (
    "\n\nReturn one entry for EVERY offering label listed above, even when the answer is that it "
    "does not fit (then say so and cite nothing). Do not return an empty list."
)


def _answers_by_label(
    out: FitOut, labelled: list[tuple[str, Product]]
) -> dict[str, OfferingFitOut]:
    """Each answer filed under the label of the offering it is about. The model is asked to use
    the label (O2) but often writes the offering's name instead, so a name that matches an offering
    counts too. If neither works and it gave exactly one entry per offering, they are taken in the
    order asked."""
    names = {product.name.strip().lower(): label for label, product in labelled}
    answers: dict[str, OfferingFitOut] = {}
    for a in out.offerings:
        key = _answer_label(a.offering)
        if key is None or key not in {label for label, _ in labelled}:
            raw = (a.offering or "").strip().lower()
            key = names.get(raw) or next(
                (label for name, label in names.items() if name and name in raw), None
            )
        if key:
            answers.setdefault(key, a)
    if not answers and len(out.offerings) == len(labelled):
        answers = {label: a for (label, _), a in zip(labelled, out.offerings, strict=True)}
    return answers


def _answer_label(raw: str) -> str | None:
    """The label the model used for an offering, whatever its dressing: "O2", "o2.", "[O2]" or
    "O2 - Cloud" all mean O2."""
    found = re.search(r"\bO\s*(\d+)\b", raw or "", flags=re.IGNORECASE)
    return f"O{found.group(1)}" if found else None


def band_and_score(
    verified_evidence: int, aligned: bool, hits: int, verdict: str | None
) -> tuple[str, int]:
    """The band comes from rules a person can read; the score only orders offerings within a band.

    - strong: at least two pieces of verified evidence, the offering belongs to the area, and the
      opportunity itself is supported or emerging.
    - potential: some verified evidence, or the offering belongs to the area and the opportunity
      is not without evidence.
    - weak: everything else that has some evidence behind the opportunity.
    - insufficient evidence: nothing verified and the opportunity has no evidence either."""
    score = (
        _EVIDENCE_POINTS[min(verified_evidence, 3)]
        + (_ALIGNMENT_POINTS if aligned else 0)
        + min(hits, _KEYWORD_POINTS_MAX) * _KEYWORD_POINTS_EACH
        + _VERDICT_POINTS.get(verdict or "", 0)
    )
    has_activity = verdict in (VERDICT_SUPPORTED, VERDICT_EMERGING, VERDICT_WEAK)
    if verified_evidence == 0 and not has_activity:
        return BAND_INSUFFICIENT, score
    if verified_evidence >= 2 and aligned and verdict in (VERDICT_SUPPORTED, VERDICT_EMERGING):
        return BAND_STRONG, score
    if verified_evidence >= 1 or (aligned and has_activity):
        return BAND_POTENTIAL, score
    return BAND_WEAK, score


def _profile_block(label: str, product: Product) -> str:
    profile = product.buyer_profile or {}
    lines = [f"[{label}] {product.name} ({product.kind})"]
    lines.append(f"- Description: {product.description or 'none given'}")
    for key, title in (
        ("buyer_functions", "Bought by"),
        ("problems", "Addresses"),
        ("area_tags", "Areas"),
    ):
        if profile.get(key):
            lines.append(f"- {title}: {', '.join(profile[key])}")
    return "\n".join(lines)


@untrusted_aware
def build_fit_prompt(
    company: Company,
    opportunity: CompanyOpportunity,
    evidence_text: str,
    assessment: OpportunityAssessment | None,
    offerings: Iterable[tuple[str, Product]],
) -> str:
    established = (
        "\n".join(f"- {f['statement']}" for f in assessment.findings)
        if assessment and assessment.findings
        else "- nothing has been established yet"
    )
    return f"""You are judging how well each of our offerings fits one company in one business \
area, so a salesperson knows what to lead with.

Company: {company.name}
Business area: {opportunity.area_label}
Industry: {opportunity.industry_context or company.industry or "unknown"}

Ground rules:
- Use ONLY the numbered evidence below. Cite it by label (for example E3) with a short VERBATIM \
quote; a quote that is not in the cited evidence is discarded.
- An offering fits only when the evidence shows a need or activity it addresses. Matching the \
offering's name to the area is not evidence.
- If the evidence does not show a need for an offering, say so plainly and cite nothing.

Already established about this area (checked earlier):
{established}

Evidence:
{wrap_untrusted(evidence_text, "evidence")}

Offerings to judge:
{chr(10).join(_profile_block(label, product) for label, product in offerings)}

For each offering return its label, one or two sentences of reasoning, and up to \
{_MAX_CITATIONS} citations (evidence label and verbatim quote)."""


def _cache_valid(
    match: OpportunityOfferingMatch,
    assessment: OpportunityAssessment | None,
    product: Product,
    set_hash: str,
) -> bool:
    return (
        match.assessment_id == (assessment.id if assessment else None)
        and match.profile_hash == product.profile_hash
        and match.evidence_set_hash == set_hash
        and match.prompt_version == FIT_PROMPT_VERSION
    )


async def latest_matches(
    session: AsyncSession, opportunity_id: object
) -> dict[object, OpportunityOfferingMatch]:
    """The newest match for each offering on this opportunity."""
    rows = (
        (
            await session.execute(
                select(OpportunityOfferingMatch)
                .where(OpportunityOfferingMatch.company_opportunity_id == opportunity_id)
                .order_by(OpportunityOfferingMatch.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    latest: dict[object, OpportunityOfferingMatch] = {}
    for row in rows:
        latest.setdefault(row.product_id, row)
    return latest


async def judge_offering_fit(
    session: AsyncSession,
    llm: StructuredLLM,
    company: Company,
    opportunity: CompanyOpportunity,
    records: list[EnrichmentRecord],
    products: list[Product],
    force: bool = False,
) -> list[OpportunityOfferingMatch]:
    """A current match for each given offering, newest first by fit. Offerings whose match is
    still valid are returned as they are; the rest are judged together in one model call."""
    items = build_evidence_pack(company, records)
    set_hash = evidence_set_hash(items)
    assessment = await latest_assessment(session, opportunity.id)
    verdict = assessment.verdict if assessment else None
    existing = await latest_matches(session, opportunity.id)

    current: dict[object, OpportunityOfferingMatch] = {}
    stale: list[Product] = []
    for product in products:
        match = existing.get(product.id)
        if match is not None and not force and _cache_valid(match, assessment, product, set_hash):
            current[product.id] = match
        else:
            stale.append(product)

    answers: dict[str, OfferingFitOut] = {}
    if stale and items:
        labelled = [(f"O{i}", product) for i, product in enumerate(stale, start=1)]
        prompt = build_fit_prompt(
            company, opportunity, format_evidence(items), assessment, labelled
        )
        out = await llm.generate(prompt, FitOut)
        answers = _answers_by_label(out, labelled)
        if not answers:
            # A model that sees no fit sometimes returns an empty list. Ask once more, plainly.
            out = await llm.generate(prompt + _RETRY_NOTE, FitOut)
            answers = _answers_by_label(out, labelled)
        labels = {product.id: label for label, product in labelled}
        if not answers:
            logger.warning(
                "offering fit: the model answered but none of its %d entries could be matched "
                "to an offering label (first: %r)",
                len(out.offerings),
                out.offerings[0].offering if out.offerings else None,
            )
    else:
        labels = {}

    by_label = {item.label: item for item in items}
    all_text = " ".join(item.text for item in items)
    for product in stale:
        answer = answers.get(labels.get(product.id, ""))
        # An offering the model said nothing about is still recorded, as "no need shown": dropping
        # it would leave the page saying "not worked out yet" with no explanation, every time.
        verified: dict[str, tuple[EvidenceItem, str]] = {}
        dropped = 0
        for citation in (answer.evidence if answer else [])[:_MAX_CITATIONS]:
            item = verify_citation(by_label, citation.evidence, citation.quote)
            if item is None:
                dropped += 1
            else:
                verified.setdefault(item.identity, (item, citation.quote))
        aligned = area_alignment(product, opportunity.area_key, opportunity.area_label)
        hits = keyword_hits(product, all_text)
        band, score = band_and_score(len(verified), aligned, hits, verdict)
        if answer is None and items and band in (BAND_STRONG, BAND_POTENTIAL):
            # The model gave no reason for this offering, so nothing backs a good band: it must
            # not read "Possible fit" under a sentence saying no need was shown.
            band = BAND_WEAK
        match = OpportunityOfferingMatch(
            organization_id=opportunity.organization_id,
            company_opportunity_id=opportunity.id,
            product_id=product.id,
            assessment_id=assessment.id if assessment else None,
            band=band,
            score=score,
            factors={
                "verified_evidence": len(verified),
                "area_alignment": aligned,
                "keyword_hits": hits,
                "assessment_verdict": verdict,
                "dropped_citations": dropped,
            },
            reasoning=(answer.reasoning.strip()[:_MAX_REASONING] if answer else "")
            or (NO_EVIDENCE_REASON if not items else NOT_ANSWERED_REASON),
            evidence=[stored_citation(item, quote) for item, quote in verified.values()],
            needs_review=dropped > 0 or (band == BAND_POTENTIAL and not verified),
            profile_hash=product.profile_hash,
            evidence_set_hash=set_hash,
            prompt_version=FIT_PROMPT_VERSION,
            model_used=model_names(llm) if items else "none",
        )
        session.add(match)
        current[product.id] = match
    await session.flush()
    return sorted(current.values(), key=lambda m: (-m.score, str(m.product_id)))
