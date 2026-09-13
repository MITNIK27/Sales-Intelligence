import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_recommendation.models import Recommendation
from app.modules.companies.service import get_company_detail
from app.modules.draft.draft_generator import DraftGenerator
from app.modules.draft.models import (
    DRAFT_CHANNEL_EMAIL,
    DRAFT_STATUS_DISCARDED,
    DRAFT_STATUS_SENT,
    Draft,
)
from app.modules.products.service import get_product
from app.modules.role_relevance.models import FRAMING_STYLE_BUSINESS
from app.modules.role_relevance.service import get_latest_role_relevance_for_contact


class CompanyNotFoundError(Exception):
    """Raised when the company doesn't exist or belongs to a different organization."""


class ContactNotFoundError(Exception):
    """Raised when the contact doesn't exist, belongs to a different organization, or doesn't
    belong to the given company."""


class ProductNotFoundError(Exception):
    """Raised when the product doesn't exist or belongs to a different organization."""


class DraftNotFoundError(Exception):
    """Raised when the draft doesn't exist or belongs to a different organization."""


async def _get_latest_recommendation(
    session: AsyncSession, organization_id: uuid.UUID, company_id: uuid.UUID, product_id: uuid.UUID
) -> Recommendation | None:
    """Best-effort grounding reuse: the most recent Recommendation for this exact
    (company, product) pair, if one has ever been generated (Phase A's ai_recommendation module).
    A draft can still be generated without one — see draft_generator.py's anti-hallucination
    fallback instruction for that case."""
    stmt = (
        select(Recommendation)
        .where(
            Recommendation.organization_id == organization_id,
            Recommendation.company_id == company_id,
            Recommendation.product_id == product_id,
        )
        .order_by(Recommendation.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def generate_draft(
    session: AsyncSession,
    organization_id: uuid.UUID,
    company_id: uuid.UUID,
    contact_id: uuid.UUID,
    product_id: uuid.UUID,
    draft_type: str,
    generator: DraftGenerator,
) -> Draft:
    """Fetches company/contact/product, the most recent matching Recommendation if one exists
    (grounding), and the contact's latest RoleRelevanceResult if one exists (framing_style —
    falls back to "business" when the contact hasn't been classified yet; this is not a hard
    failure, since not every org will always classify a contact before drafting to them). Calls
    the generator and persists a new Draft row."""
    company = await get_company_detail(session, organization_id, company_id)
    if company is None:
        raise CompanyNotFoundError(f"company {company_id} not found")

    contact = next((c for c in company.contacts if c.id == contact_id), None)
    if contact is None:
        raise ContactNotFoundError(f"contact {contact_id} not found on this company")

    product = await get_product(session, organization_id, product_id)
    if product is None:
        raise ProductNotFoundError(f"product {product_id} not found")

    recommendation = await _get_latest_recommendation(
        session, organization_id, company_id, product_id
    )

    role_relevance = await get_latest_role_relevance_for_contact(
        session, organization_id, contact_id
    )
    framing_style = (
        role_relevance.matched_category_framing_style
        if role_relevance and role_relevance.matched_category_framing_style
        else FRAMING_STYLE_BUSINESS
    )

    result = await generator.generate(
        company, contact, product, recommendation, framing_style, draft_type
    )

    draft = Draft(
        organization_id=organization_id,
        company_id=company_id,
        contact_id=contact_id,
        product_id=product_id,
        recommendation_id=recommendation.id if recommendation else None,
        draft_type=draft_type,
        channel=DRAFT_CHANNEL_EMAIL,
        subject=result.subject,
        body=result.body,
        model_used=generator.model_name,
    )
    session.add(draft)
    await session.flush()
    return draft


async def _get_draft(
    session: AsyncSession, organization_id: uuid.UUID, draft_id: uuid.UUID
) -> Draft | None:
    draft = await session.get(Draft, draft_id)
    if draft is None or draft.organization_id != organization_id:
        return None
    return draft


async def update_draft(
    session: AsyncSession,
    organization_id: uuid.UUID,
    draft_id: uuid.UUID,
    subject: str | None,
    body: str | None,
) -> Draft | None:
    """The human-in-the-loop edit path — mutates the same row, unlike every append-only Phase
    A/C entity. Only touches fields explicitly provided."""
    draft = await _get_draft(session, organization_id, draft_id)
    if draft is None:
        return None
    if subject is not None:
        draft.subject = subject
    if body is not None:
        draft.body = body
    await session.flush()
    return draft


async def discard_draft(
    session: AsyncSession, organization_id: uuid.UUID, draft_id: uuid.UUID
) -> Draft | None:
    draft = await _get_draft(session, organization_id, draft_id)
    if draft is None:
        return None
    draft.status = DRAFT_STATUS_DISCARDED
    await session.flush()
    return draft


async def mark_draft_sent(
    session: AsyncSession, organization_id: uuid.UUID, draft_id: uuid.UUID
) -> Draft | None:
    """Called from outreach/service.py when a rep logs an OutreachActivity against this draft."""
    draft = await _get_draft(session, organization_id, draft_id)
    if draft is None:
        return None
    draft.status = DRAFT_STATUS_SENT
    await session.flush()
    return draft


async def list_drafts(
    session: AsyncSession,
    organization_id: uuid.UUID,
    company_id: uuid.UUID,
    contact_id: uuid.UUID | None = None,
) -> list[Draft]:
    conditions = [Draft.organization_id == organization_id, Draft.company_id == company_id]
    if contact_id is not None:
        conditions.append(Draft.contact_id == contact_id)
    stmt = select(Draft).where(*conditions).order_by(Draft.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())
