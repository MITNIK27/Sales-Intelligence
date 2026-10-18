"""What a draft may cite. The first-touch prompt asks for "a specific, researched trigger", and
until now the only grounding was an optional Recommendation that the auto pipeline never creates.
This gathers facts the system actually verified - recent cleaned news, the qualification points
that passed with evidence, size and the recipient's seniority - and formats them for the prompt
with an explicit rule: use these, invent nothing else.

Pure formatting here (`format_evidence`); `build_draft_evidence` is the only part that reads the
database."""

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.enrichment.service import list_company_signals
from app.modules.qualification.models import QualificationResult

MAX_SIGNALS = 3
MAX_POINTS = 3


@dataclass
class DraftEvidence:
    signals: list[dict[str, Any]] = field(default_factory=list)  # text, date, source, url
    qualification_points: list[str] = field(default_factory=list)
    employee_count_range: str | None = None
    contact_seniority: str | None = None

    @property
    def is_empty(self) -> bool:
        return not (self.signals or self.qualification_points or self.employee_count_range)


async def build_draft_evidence(
    session: AsyncSession,
    organization_id: uuid.UUID,
    company: Company,
    contact: Contact,
) -> DraftEvidence:
    records = await list_company_signals(session, organization_id, company.id)
    news = [r for r in records if (r.raw_payload or {}).get("signal_type") == "news"]
    signals = [
        {
            "text": r.raw_payload.get("text"),
            "date": r.raw_payload.get("date"),
            "source": "context.dev" if r.source.startswith("contextdev") else "company website",
            "url": r.raw_payload.get("url"),
        }
        for r in news[:MAX_SIGNALS]
    ]

    latest = (
        await session.execute(
            select(QualificationResult)
            .where(QualificationResult.company_id == company.id)
            .order_by(QualificationResult.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    points: list[str] = []
    for entry in (latest.criteria_results if latest else None) or []:
        # Only points that passed WITH a verified quote: an unverified "met" is not a fact.
        if entry.get("status") == "PASS" and entry.get("evidence_quote"):
            points.append(f"{entry.get('criterion_name')}: \"{entry.get('evidence_quote')}\"")
    return DraftEvidence(
        signals=signals,
        qualification_points=points[:MAX_POINTS],
        employee_count_range=company.employee_count_range,
        contact_seniority=contact.seniority,
    )


def format_evidence(evidence: DraftEvidence | None) -> str:
    """The prompt block. Empty evidence says so plainly, so the model keeps the line general
    instead of inventing a trigger."""
    if evidence is None or evidence.is_empty:
        return (
            "Verified facts about this company: none available beyond the description above. "
            "Do not invent news, numbers or events; keep the opening line to what the "
            "description and the recipient's role support."
        )
    lines = ["Verified facts about this company (the ONLY facts you may cite):"]
    if evidence.employee_count_range:
        lines.append(f"- Size: about {evidence.employee_count_range} employees")
    for point in evidence.qualification_points:
        lines.append(f"- Confirmed fit: {point}")
    for signal in evidence.signals:
        when = f" ({signal['date']})" if signal.get("date") else ""
        lines.append(f"- Recent news{when}: {signal['text']} [{signal['source']}]")
    lines.append(
        "Use AT MOST ONE of these as the opening trigger, and only if it is genuinely relevant "
        "to the recipient's role. Do not state any fact, figure or event that is not listed "
        "above. Do not quote dates you were not given."
    )
    return "\n".join(lines)
