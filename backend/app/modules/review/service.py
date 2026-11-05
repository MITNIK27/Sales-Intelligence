import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.review.models import ReviewDecision

SUBJECT_COMPANY = "company"
SUBJECT_CONTACT = "contact"
DECISION_CONFIRMED = "confirmed"
DECISION_DELETED = "deleted"


def company_snapshot(company: Company) -> dict[str, Any]:
    return {
        "name": company.name,
        "domain": company.domain,
        "found_by_run": (
            str(company.source_ingestion_run_id) if company.source_ingestion_run_id else None
        ),
    }


def contact_snapshot(contact: Contact) -> dict[str, Any]:
    """Role and where it came from, never the person's name or email (personal data)."""
    return {
        "role_title": contact.role_title,
        "seniority": contact.seniority,
        "source": contact.source,
        "confidence": contact.confidence,
    }


def record_review_decision(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    subject_type: str,
    subject_id: uuid.UUID,
    company_id: uuid.UUID | None,
    decision: str,
    was_flagged: bool,
    flag_reason: str | None,
    snapshot: dict[str, Any] | None,
) -> ReviewDecision:
    """Adds the row to the caller's session, so it is saved or rolled back with the decision it
    describes. Never commits on its own."""
    row = ReviewDecision(
        organization_id=organization_id,
        subject_type=subject_type,
        subject_id=subject_id,
        company_id=company_id,
        decision=decision,
        was_flagged=was_flagged,
        flag_reason=flag_reason,
        snapshot=snapshot,
    )
    session.add(row)
    return row
