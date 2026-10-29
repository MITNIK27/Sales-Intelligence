import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_recommendation.models import Recommendation
from app.modules.companies.models import Company
from app.modules.companies.service import get_company_detail
from app.modules.contacts.models import Contact
from app.modules.draft.draft_generator import DraftGenerator
from app.modules.draft.evidence import build_draft_evidence
from app.modules.draft.models import (
    DRAFT_CHANNEL_EMAIL,
    DRAFT_STATUS_DISCARDED,
    DRAFT_STATUS_DRAFT,
    DRAFT_STATUS_SENT,
    DRAFT_TYPE_FIRST_TOUCH,
    Draft,
)
from app.modules.draft.schemas import DraftListItem, DraftListOut
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


class NeedsReviewError(Exception):
    """Raised when the company or the specific contact is still flagged `needs_review` — an
    unreviewed contact must not receive a drafted (and potentially sent) outreach message.
    Cleared only via `companies.service.confirm_company` / `contacts.service.confirm_contact`."""


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


_PREVIOUS_EMAILS_SHOWN = 3


async def _previous_emails(
    session: AsyncSession, organization_id: uuid.UUID, contact_id: uuid.UUID
) -> list[tuple[str | None, str]]:
    """The contact's most recent non-discarded drafts, oldest first (subject, body)."""
    stmt = (
        select(Draft)
        .where(
            Draft.organization_id == organization_id,
            Draft.contact_id == contact_id,
            Draft.status != DRAFT_STATUS_DISCARDED,
        )
        .order_by(Draft.created_at.desc())
        .limit(_PREVIOUS_EMAILS_SHOWN)
    )
    drafts = (await session.execute(stmt)).scalars().all()
    return [(d.subject, d.body) for d in reversed(drafts)]


async def generate_draft(
    session: AsyncSession,
    organization_id: uuid.UUID,
    company_id: uuid.UUID,
    contact_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    draft_type: str,
    generator: DraftGenerator,
) -> Draft:
    """Fetches company/contact/every candidate product, the most recent matching Recommendation
    for each (grounding), and the contact's latest RoleRelevanceResult if one exists (framing_style
    — falls back to "business" when the contact hasn't been classified yet; this is not a hard
    failure, since not every org will always classify a contact before drafting to them). When more
    than one product is given, the generator itself picks exactly one (via `DraftResult.
    chosen_option`, a 1-based index into `product_ids` in the given order) — this function maps
    that back to a real `product_id`/`Recommendation`, never trusting the LLM to echo back a UUID.
    Persists a new Draft row for whichever product was chosen."""
    company = await get_company_detail(session, organization_id, company_id)
    if company is None:
        raise CompanyNotFoundError(f"company {company_id} not found")

    contact = next((c for c in company.contacts if c.id == contact_id), None)
    if contact is None:
        raise ContactNotFoundError(f"contact {contact_id} not found on this company")

    if company.needs_review:
        raise NeedsReviewError(f"company {company_id} needs review before drafting")
    if contact.needs_review:
        raise NeedsReviewError(f"contact {contact_id} needs review before drafting")

    products = []
    for product_id in product_ids:
        product = await get_product(session, organization_id, product_id)
        if product is None:
            raise ProductNotFoundError(f"product {product_id} not found")
        products.append(product)

    recommendations = [
        await _get_latest_recommendation(session, organization_id, company_id, product_id)
        for product_id in product_ids
    ]

    role_relevance = await get_latest_role_relevance_for_contact(
        session, organization_id, contact_id
    )
    framing_style = (
        role_relevance.matched_category_framing_style
        if role_relevance and role_relevance.matched_category_framing_style
        else FRAMING_STYLE_BUSINESS
    )

    evidence = await build_draft_evidence(session, organization_id, company, contact)
    # A follow-up sees what this person was already written, so "add something new" is checkable.
    # Passed only when there is something, so a generator written without it keeps working.
    previous = (
        await _previous_emails(session, organization_id, contact_id)
        if draft_type != DRAFT_TYPE_FIRST_TOUCH
        else []
    )
    result = await generator.generate(
        company,
        contact,
        products,
        recommendations,
        framing_style,
        draft_type,
        evidence,
        **({"previous_emails": previous} if previous else {}),
    )

    chosen_index = result.chosen_option - 1
    chosen_product = products[chosen_index]
    chosen_recommendation = recommendations[chosen_index]

    draft = Draft(
        organization_id=organization_id,
        company_id=company_id,
        contact_id=contact_id,
        product_id=chosen_product.id,
        recommendation_id=chosen_recommendation.id if chosen_recommendation else None,
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


async def list_all_drafts(
    session: AsyncSession,
    organization_id: uuid.UUID,
    status: str | None = None,
    limit: int = 25,
    offset: int = 0,
) -> DraftListOut:
    """Every draft in the organization, newest first, for the review page. Read-only. `status`
    None means all statuses; `counts` always reports all three so the page can label its tabs."""
    conditions = [Draft.organization_id == organization_id]
    if status is not None:
        conditions.append(Draft.status == status)

    total = (
        await session.execute(select(func.count()).select_from(Draft).where(*conditions))
    ).scalar_one()
    rows = await session.execute(
        select(Draft, Company.name, Contact.full_name, Contact.role_title)
        .join(Company, Company.id == Draft.company_id)
        .join(Contact, Contact.id == Draft.contact_id)
        .where(*conditions)
        .order_by(Draft.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [
        DraftListItem(
            id=d.id,
            company_id=d.company_id,
            company_name=company_name,
            contact_id=d.contact_id,
            contact_name=contact_name,
            contact_role=contact_role,
            draft_type=d.draft_type,
            channel=d.channel,
            subject=d.subject,
            body=d.body,
            status=d.status,
            model_used=d.model_used,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d, company_name, contact_name, contact_role in rows.all()
    ]
    counts = {s: 0 for s in (DRAFT_STATUS_DRAFT, DRAFT_STATUS_SENT, DRAFT_STATUS_DISCARDED)}
    grouped = await session.execute(
        select(Draft.status, func.count())
        .where(Draft.organization_id == organization_id)
        .group_by(Draft.status)
    )
    for draft_status, n in grouped.all():
        counts[draft_status] = n
    return DraftListOut(items=items, total=total, limit=limit, offset=offset, counts=counts)
