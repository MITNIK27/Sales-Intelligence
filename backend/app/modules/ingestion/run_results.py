"""The rep-facing result of a Market Discovery run: one worklist of companies that are worth
acting on (qualified, with at least one primary-target candidate contact) and, collapsed behind
it, everything that is not — each with a single-sentence reason.

A candidate contact is shown with the evidence a rep needs to pick the right person (role,
LinkedIn profile link, email when one was actually found). A draft is written only after the rep
confirms a contact, so a draft appears on a candidate only once that has happened.

Pure read side: assembles what the auto-pipeline already stored (company, latest qualification
result, latest role classification per contact, channels, latest draft per contact, enrichment
provenance). Nothing here judges anything; the verdicts were computed deterministically when they
were stored."""

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import ENRICHMENT_STATUS_FAILED, Company
from app.modules.contacts.models import (
    CHANNEL_TYPE_EMAIL,
    CHANNEL_TYPE_LINKEDIN,
    Contact,
    ContactChannel,
)
from app.modules.draft.models import DRAFT_STATUS_DISCARDED, Draft
from app.modules.enrichment.models import ENTITY_TYPE_COMPANY, EnrichmentRecord
from app.modules.ingestion.models import IngestionRun
from app.modules.qualification.evidence import overall_confidence, status_for_verdict
from app.modules.qualification.models import QualificationResult
from app.modules.role_relevance.models import RoleRelevanceResult

VERDICT_QUALIFIED = "qualified"
VERDICT_NOT_QUALIFIED = "not_qualified"
PRIORITY_PRIMARY = "primary"
# Not in contacts.models yet: the contact-search work that creates these channels is a later step
# of this round; the results view reads them already so the two land independently.

DATA_SOURCE_CONTEXTDEV = "context.dev"
DATA_SOURCE_SCRAPER = "scraper"
DATA_SOURCE_NONE = "none"


@dataclass
class WorklistDraft:
    draft_id: uuid.UUID
    subject: str | None
    body: str
    status: str


@dataclass
class WorklistContact:
    contact_id: uuid.UUID
    full_name: str | None
    role_title: str | None
    category: str | None
    # None means "not found" — shown as such, never guessed.
    linkedin_url: str | None
    email: str | None
    # Still flagged for review (found via search, not confirmed): needs the rep's one-click
    # confirmation before a draft can be written.
    needs_review: bool
    needs_review_reason: str | None
    draft: WorklistDraft | None
    confidence: float | None = None  # how sure we are they work at this company (0..1)
    source: str | None = None


@dataclass
class WorklistCriterion:
    name: str
    status: str  # PASS | FAIL | UNKNOWN
    hard: bool
    scope: str  # "run" (defined for this search) | "org" (saved criteria)
    reasoning: str | None
    evidence_quote: str | None
    source: str | None
    url: str | None
    confidence: float | None


def _criteria_detail(result: QualificationResult | None) -> list[WorklistCriterion]:
    items: list[WorklistCriterion] = []
    for entry in (result.criteria_results if result else None) or []:
        c: dict[str, Any] = dict(entry)
        items.append(
            WorklistCriterion(
                name=str(c.get("criterion_name") or ""),
                status=str(c.get("status") or status_for_verdict(str(c.get("verdict")))),
                hard=bool(c.get("is_disqualifying")),
                scope=str(c.get("scope") or "org"),
                reasoning=c.get("reasoning"),
                evidence_quote=c.get("evidence_quote"),
                source=c.get("source"),
                url=c.get("url"),
                confidence=c.get("confidence"),
            )
        )
    return sorted(items, key=lambda i: (not i.hard, i.name))


@dataclass
class WorklistRow:
    company_id: uuid.UUID
    name: str
    domain: str | None
    industry: str | None
    employee_count_range: str | None
    description: str | None
    data_source: str
    verdict: str | None
    why: str | None
    candidates: list[WorklistContact]
    skip_reason: str | None
    # Per-criterion PASS/FAIL/UNKNOWN with the evidence behind each, and the weakest hard-criterion
    # confidence — the "why qualified" detail. Empty for results stored before evidence existed.
    criteria: list[WorklistCriterion] = field(default_factory=list)
    confidence: float | None = None
    priority_score: float | None = None
    score_breakdown: dict[str, Any] | None = None
    # Where industry / size / description came from: {"industry": {"source", "confidence"}, ...}
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class Worklist:
    ready: list[WorklistRow]
    not_shown: list[WorklistRow]


def _qualification_why(result: QualificationResult | None) -> tuple[str | None, str | None]:
    """(why it qualified, why it did not) — each one line, taken from the stored per-criterion
    reasoning (hard requirements first), never re-derived."""
    if result is None:
        return None, "not qualified yet (no active criteria, or the run stopped early)"
    criteria: list[dict[str, Any]] = [dict(c) for c in result.criteria_results or []]

    def line(entry: dict[str, Any]) -> str:
        return f"{entry.get('criterion_name')}: {entry.get('reasoning')}".strip()

    if result.overall_verdict == VERDICT_QUALIFIED:
        met = sorted(
            (c for c in criteria if c.get("verdict") == "met"),
            key=lambda c: not c.get("is_disqualifying"),
        )
        # "Qualified" can mean nothing was ever checked against evidence (no hard criteria exist).
        # Say that instead of implying requirements were verified.
        return (
            "; ".join(line(c) for c in met[:2]) or "no requirement could be verified from the data"
        ), None

    if result.overall_verdict == VERDICT_NOT_QUALIFIED:
        failing = [
            c for c in criteria if c.get("is_disqualifying") and c.get("verdict") == "not_met"
        ]
        reason = line(failing[0]) if failing else result.overall_verdict
        return None, f"does not qualify - {reason}"

    # Could not be verified: not rejected, kept in the list (ranked below verified companies)
    # and labelled, so the rep decides with the gap in plain sight.
    unknown = [c for c in criteria if c.get("is_disqualifying") and c.get("verdict") != "met"]
    missing = ", ".join(str(c.get("criterion_name")) for c in unknown) or "a hard requirement"
    return f"Needs evidence - could not verify: {missing}", None


async def build_run_worklist(
    session: AsyncSession, organization_id: uuid.UUID, run_id: uuid.UUID
) -> Worklist:
    # A run covers the companies it created AND the ones it reused from the existing index
    # (recorded in the run summary; those carry another run's id as their source).
    run = await session.get(IngestionRun, run_id)
    summary_ids = [
        uuid.UUID(cid) for cid in ((run.summary if run else None) or {}).get("company_ids", [])
    ]
    companies = list(
        (
            await session.execute(
                select(Company)
                .where(
                    Company.organization_id == organization_id,
                    or_(Company.source_ingestion_run_id == run_id, Company.id.in_(summary_ids)),
                )
                .order_by(Company.name)
            )
        )
        .scalars()
        .all()
    )
    if not companies:
        return Worklist(ready=[], not_shown=[])
    company_ids = [c.id for c in companies]

    # Latest qualification result per company (append-only table -> newest wins).
    qualification: dict[uuid.UUID, QualificationResult] = {}
    for stored_result in (
        await session.execute(
            select(QualificationResult)
            .where(QualificationResult.company_id.in_(company_ids))
            .order_by(QualificationResult.created_at.asc())
        )
    ).scalars():
        qualification[stored_result.company_id] = stored_result

    # Latest role classification per contact; a company's contact is its first primary-target one.
    contacts = {
        c.id: c
        for c in (
            await session.execute(select(Contact).where(Contact.company_id.in_(company_ids)))
        ).scalars()
    }
    role_by_contact: dict[uuid.UUID, RoleRelevanceResult] = {}
    for role in (
        await session.execute(
            select(RoleRelevanceResult)
            .where(RoleRelevanceResult.company_id.in_(company_ids))
            .order_by(RoleRelevanceResult.created_at.asc())
        )
    ).scalars():
        role_by_contact[role.contact_id] = role

    # Channels per contact: the LinkedIn profile URL and an email, each only if actually found.
    linkedin_by_contact: dict[uuid.UUID, str] = {}
    email_by_contact: dict[uuid.UUID, str] = {}
    if contacts:
        for channel in (
            await session.execute(
                select(ContactChannel).where(ContactChannel.contact_id.in_(list(contacts)))
            )
        ).scalars():
            if channel.channel_type == CHANNEL_TYPE_LINKEDIN:
                linkedin_by_contact.setdefault(channel.contact_id, channel.value)
            elif channel.channel_type == CHANNEL_TYPE_EMAIL:
                email_by_contact.setdefault(channel.contact_id, channel.value)

    drafts_by_contact: dict[uuid.UUID, Draft] = {}
    for stored_draft in (
        await session.execute(
            select(Draft)
            .where(Draft.company_id.in_(company_ids), Draft.status != DRAFT_STATUS_DISCARDED)
            .order_by(Draft.created_at.asc())
        )
    ).scalars():
        drafts_by_contact[stored_draft.contact_id] = stored_draft

    sources_by_company: dict[uuid.UUID, set[str]] = {}
    for company_id, source in (
        await session.execute(
            select(EnrichmentRecord.entity_id, EnrichmentRecord.source).where(
                EnrichmentRecord.entity_type == ENTITY_TYPE_COMPANY,
                EnrichmentRecord.entity_id.in_(company_ids),
            )
        )
    ).all():
        sources_by_company.setdefault(company_id, set()).add(source)

    ready: list[WorklistRow] = []
    not_shown: list[WorklistRow] = []
    for company in companies:
        sources = sources_by_company.get(company.id, set())
        if any(s.startswith("contextdev:") for s in sources):
            data_source = DATA_SOURCE_CONTEXTDEV
        elif sources:
            data_source = DATA_SOURCE_SCRAPER
        else:
            data_source = DATA_SOURCE_NONE

        result = qualification.get(company.id)
        why, not_why = _qualification_why(result)

        company_contacts = [c for c in contacts.values() if c.company_id == company.id]
        candidates: list[WorklistContact] = []
        # Most certain match first (a missing confidence sorts last), then by name.
        for c in sorted(
            company_contacts,
            key=lambda x: (
                -(x.confidence if x.confidence is not None else -1.0),
                x.full_name or "",
            ),
        ):
            contact_role = role_by_contact.get(c.id)
            if contact_role is None or contact_role.priority != PRIORITY_PRIMARY:
                continue
            draft_row = drafts_by_contact.get(c.id)
            candidates.append(
                WorklistContact(
                    contact_id=c.id,
                    full_name=c.full_name,
                    role_title=c.role_title,
                    category=contact_role.matched_category_name,
                    linkedin_url=linkedin_by_contact.get(c.id),
                    email=email_by_contact.get(c.id),
                    needs_review=bool(c.needs_review),
                    needs_review_reason=c.needs_review_reason,
                    confidence=c.confidence,
                    source=c.source,
                    draft=(
                        WorklistDraft(
                            draft_id=draft_row.id,
                            subject=draft_row.subject,
                            body=draft_row.body,
                            status=draft_row.status,
                        )
                        if draft_row is not None
                        else None
                    ),
                )
            )

        skip_reason: str | None = None
        if company.enrichment_status == ENRICHMENT_STATUS_FAILED:
            skip_reason = f"enrichment failed - {company.enrichment_error or 'unknown error'}"
        elif company.needs_review:
            skip_reason = f"needs review - {company.needs_review_reason or 'flagged'}"
        elif not_why is not None:
            skip_reason = not_why
        elif not candidates:
            classified = sum(1 for c in company_contacts if c.id in role_by_contact)
            if not company_contacts:
                skip_reason = "qualified, but no contacts were found"
            elif classified == 0:
                skip_reason = (
                    f"qualified, but its {len(company_contacts)} contacts were not "
                    "classified yet (run limit)"
                )
            else:
                skip_reason = (
                    f"qualified, but none of its {len(company_contacts)} contacts is a "
                    "primary-target role"
                )

        row = WorklistRow(
            company_id=company.id,
            name=company.name,
            domain=company.domain,
            industry=company.industry,
            employee_count_range=company.employee_count_range,
            description=company.description,
            data_source=data_source,
            verdict=result.overall_verdict if result else None,
            why=why,
            candidates=candidates,
            skip_reason=skip_reason,
            criteria=_criteria_detail(result),
            provenance=dict(company.field_provenance or {}),
            priority_score=result.priority_score if result else None,
            score_breakdown=dict(result.score_breakdown or {}) if result else None,
            confidence=overall_confidence([dict(c) for c in (result.criteria_results or [])])
            if result
            else None,
        )
        (not_shown if skip_reason else ready).append(row)

    # Best opportunity first: fully verified before needs-evidence, then by Priority Score.
    ready.sort(
        key=lambda r: (r.verdict != VERDICT_QUALIFIED, -(r.priority_score or 0.0), r.name)
    )
    return Worklist(ready=ready, not_shown=not_shown)
