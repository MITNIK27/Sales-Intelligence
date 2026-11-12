"""Assessing a company in one area: show the model the evidence, then keep only what survives
checking. The model proposes findings; code verifies each citation, decides which findings stand
and what verdict the set earns, and stores the result as a new version."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.enrichment.models import EnrichmentRecord
from app.modules.llm.structured import FallbackStructuredLLM, StructuredLLM
from app.modules.opportunity.evidence import (
    EvidenceItem,
    build_evidence_pack,
    evidence_set_hash,
    format_evidence,
    stored_citation,
    verify_citation,
)
from app.modules.opportunity.llm_models import AssessmentOut
from app.modules.opportunity.models import (
    VERDICT_INSUFFICIENT,
    CompanyOpportunity,
    OpportunityAssessment,
)
from app.modules.opportunity.prompts import PROMPT_VERSION, build_assessment_prompt
from app.modules.opportunity.research.report import gap_statements
from app.modules.opportunity.service import latest_assessment, next_version
from app.modules.opportunity.sufficiency import VerifiedFinding, decide_verdict, kind_fits_evidence

NOTHING_FOUND = "No public evidence about this area was found in the sources searched."
NO_EVIDENCE_AT_ALL = "There is no evidence on file for this company yet."
_MAX_NOT_FOUND = 6


@dataclass(frozen=True)
class AssessmentResult:
    assessment: OpportunityAssessment
    cache_hit: bool


def model_names(llm: StructuredLLM) -> str:
    """Which vendor(s) actually answered, for the record (a fallback chain remembers them)."""
    if isinstance(llm, FallbackStructuredLLM) and llm.used:
        return ",".join(sorted(llm.used))[:50]
    return getattr(llm, "name", "unknown")[:50]


def verified_findings(
    items: list[EvidenceItem], answer: AssessmentOut
) -> tuple[list[VerifiedFinding], int]:
    """The model's findings that survive checking, and how many did not. A finding stands only when
    its citation names real evidence, its quote is in that evidence, it has a statement, and its
    kind fits what the evidence is. Used by the assessment and by its evals, so both check alike."""
    by_label = {item.label: item for item in items}
    findings: list[VerifiedFinding] = []
    dropped = 0
    for proposed in answer.findings:
        item = verify_citation(by_label, proposed.evidence, proposed.quote)
        statement = proposed.statement.strip()
        if item is None or not statement or not kind_fits_evidence(proposed.kind, item):
            dropped += 1
            continue
        findings.append(VerifiedFinding(proposed.kind, statement, item, proposed.quote))
    return findings, dropped


async def assess_opportunity(
    session: AsyncSession,
    llm: StructuredLLM,
    company: Company,
    opportunity: CompanyOpportunity,
    records: list[EnrichmentRecord],
    force: bool = False,
) -> AssessmentResult:
    items = build_evidence_pack(company, records)
    set_hash = evidence_set_hash(items)
    gaps = gap_statements(opportunity.research_log)

    # Same evidence, same prompt version, and nothing new to say about what was not found: the
    # earlier judgment still stands, so no model call.
    previous = await latest_assessment(session, opportunity.id)
    if (
        not force
        and previous is not None
        and previous.evidence_set_hash == set_hash
        and previous.prompt_version == PROMPT_VERSION
        and set(gaps) <= set(previous.not_found)
    ):
        return AssessmentResult(previous, cache_hit=True)

    findings: list[VerifiedFinding] = []
    dropped = 0
    not_found: list[str] = []
    summary = NO_EVIDENCE_AT_ALL

    if items:
        prompt = build_assessment_prompt(
            company, opportunity.area_label, opportunity.industry_context, format_evidence(items)
        )
        answer = await llm.generate(prompt, AssessmentOut)
        findings, dropped = verified_findings(items, answer)
        summary = answer.summary.strip() or NOTHING_FOUND
        not_found = [n.strip() for n in answer.not_found if n.strip()][:_MAX_NOT_FOUND]

    verdict = decide_verdict(findings)
    # What the collectors searched and did not find is stated by code, not left to the model.
    not_found = [*gaps, *(n for n in not_found if n not in gaps)][:_MAX_NOT_FOUND]
    if verdict == VERDICT_INSUFFICIENT and not not_found:
        not_found = [NOTHING_FOUND if items else NO_EVIDENCE_AT_ALL]

    assessment = OpportunityAssessment(
        organization_id=opportunity.organization_id,
        company_opportunity_id=opportunity.id,
        version=await next_version(session, opportunity.id),
        verdict=verdict,
        summary=summary,
        findings=[
            {
                "kind": f.kind,
                "statement": f.statement,
                "evidence": stored_citation(f.item, f.quote),
            }
            for f in findings
        ],
        not_found=not_found,
        dropped_count=dropped,
        evidence_count=len(items),
        evidence_set_hash=set_hash,
        prompt_version=PROMPT_VERSION,
        model_used=model_names(llm) if items else "none",
    )
    session.add(assessment)
    await session.flush()
    return AssessmentResult(assessment, cache_hit=False)
