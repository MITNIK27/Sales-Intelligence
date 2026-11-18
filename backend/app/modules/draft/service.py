import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_recommendation.models import Recommendation
from app.modules.companies.models import Company
from app.modules.companies.service import get_company_detail
from app.modules.contacts.models import Contact
from app.modules.draft.claims import find_unsupported_claims
from app.modules.draft.draft_generator import DraftGenerator
from app.modules.draft.evidence import DraftEvidence, build_draft_evidence
from app.modules.draft.models import (
    DRAFT_CHANNEL_EMAIL,
    DRAFT_STATUS_DISCARDED,
    DRAFT_STATUS_DRAFT,
    DRAFT_STATUS_SENT,
    DRAFT_TYPE_FIRST_TOUCH,
    Draft,
)
from app.modules.draft.prompts import PROMPT_VERSION
from app.modules.draft.refine import REFINE_PROMPT_VERSION
from app.modules.draft.schemas import DraftListItem, DraftListOut
from app.modules.products.models import Product
from app.modules.products.service import get_product
from app.modules.role_relevance.models import FRAMING_STYLE_BUSINESS, FRAMING_STYLE_TECHNICAL
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


class DraftNotEditableError(Exception):
    """Raised when a draft that was already sent or discarded is asked to change."""


class NothingToUndoError(Exception):
    """Raised when a draft has no earlier version to go back to."""


class NeedsReviewError(Exception):
    """Raised when the company or the specific contact is still flagged `needs_review` — an
    unreviewed contact must not receive a drafted (and potentially sent) outreach message.
    Cleared only via `companies.service.confirm_company` / `contacts.service.confirm_contact`."""


async def _get_latest_recommendation(
    session: AsyncSession,
    organization_id: uuid.UUID,
    company_id: uuid.UUID,
    product_id: uuid.UUID,
    opportunity_id: uuid.UUID | None = None,
) -> Recommendation | None:
    """Best-effort grounding reuse: the most recent Recommendation for this exact
    (company, product) pair, if one has ever been generated (Phase A's ai_recommendation module).
    A draft can still be generated without one — see draft_generator.py's anti-hallucination
    fallback instruction for that case."""
    base = select(Recommendation).where(
        Recommendation.organization_id == organization_id,
        Recommendation.company_id == company_id,
        Recommendation.product_id == product_id,
    )
    if opportunity_id is not None:
        # A recommendation written for this opportunity is the right grounding; fall back to the
        # newest company-and-offering one only when there is none.
        scoped = (
            (
                await session.execute(
                    base.where(Recommendation.company_opportunity_id == opportunity_id)
                    .order_by(Recommendation.created_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if scoped is not None:
            return scoped
    stmt = base.order_by(Recommendation.created_at.desc()).limit(1)
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


async def _style_from_buying_role(
    session: AsyncSession,
    opportunity_id: uuid.UUID | None,
    contact_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> str:
    """Someone who would use the offering is written to technically; anyone else (and anyone not
    judged) in business terms, which was always the fallback."""
    if opportunity_id is None:
        return FRAMING_STYLE_BUSINESS
    from app.modules.opportunity.relevance import resolve_relevance

    for product_id in product_ids:
        resolved = (await resolve_relevance(session, opportunity_id, product_id)).get(contact_id)
        if resolved is not None:
            return FRAMING_STYLE_TECHNICAL if resolved.role == "user" else FRAMING_STYLE_BUSINESS
    return FRAMING_STYLE_BUSINESS


def _allowed_sources(
    company: Any,
    product: Product,
    recommendation: Recommendation | None,
    evidence: DraftEvidence,
) -> list[str | None]:
    """What a draft was allowed to draw on; a figure or past-work claim outside it is flagged."""
    return [
        company.description,
        company.industry,
        company.employee_count_range,
        product.name,
        product.description,
        *(
            [
                recommendation.pitch_summary,
                recommendation.why_this_company,
                *recommendation.talking_points,
            ]
            if recommendation
            else []
        ),
        *(str(signal.get("text") or "") for signal in evidence.signals),
        *evidence.qualification_points,
        evidence.employee_count_range,
    ]


async def generate_draft(
    session: AsyncSession,
    organization_id: uuid.UUID,
    company_id: uuid.UUID,
    contact_id: uuid.UUID,
    product_ids: list[uuid.UUID],
    draft_type: str,
    generator: DraftGenerator,
    opportunity_id: uuid.UUID | None = None,
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
    if company.dismissed_at is not None:
        raise NeedsReviewError(f"company {company_id} was marked not a fit; restore it to draft")
    if contact.needs_review:
        raise NeedsReviewError(f"contact {contact_id} needs review before drafting")

    products = []
    for product_id in product_ids:
        product = await get_product(session, organization_id, product_id)
        if product is None:
            raise ProductNotFoundError(f"product {product_id} not found")
        products.append(product)

    recommendations = [
        await _get_latest_recommendation(
            session, organization_id, company_id, product_id, opportunity_id
        )
        for product_id in product_ids
    ]

    role_relevance = await get_latest_role_relevance_for_contact(
        session, organization_id, contact_id
    )
    framing_style = (
        role_relevance.matched_category_framing_style
        if role_relevance and role_relevance.matched_category_framing_style
        else None
    )
    if framing_style is None:
        # Not classified the old way: let the person's part in this opportunity (as set or judged
        # in the Company Brief) decide the tone, so the draft agrees with what the Brief shows.
        framing_style = await _style_from_buying_role(
            session, opportunity_id, contact_id, product_ids
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

    # What the draft was allowed to draw on; a figure or past-work claim outside it is flagged.
    allowed = [
        *_allowed_sources(company, chosen_product, chosen_recommendation, evidence),
        *(earlier_body for _, earlier_body in previous),
    ]
    flags = find_unsupported_claims(f"{result.subject or ''}\n{result.body}", allowed)

    draft = Draft(
        organization_id=organization_id,
        company_id=company_id,
        contact_id=contact_id,
        product_id=chosen_product.id,
        recommendation_id=chosen_recommendation.id if chosen_recommendation else None,
        company_opportunity_id=opportunity_id,
        draft_type=draft_type,
        channel=DRAFT_CHANNEL_EMAIL,
        subject=result.subject,
        body=result.body,
        model_used=generator.model_name,
        prompt_version=PROMPT_VERSION,
        grounding_flags=flags or None,
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


MAX_REVISIONS = 10


async def refine_draft(
    session: AsyncSession,
    organization_id: uuid.UUID,
    draft_id: uuid.UUID,
    instruction: str,
    subject: str | None,
    body: str,
    generator: DraftGenerator,
) -> Draft | None:
    """Rewrite a draft the way the rep describes. The text rewritten is the text the rep sent (what
    is on screen, hand edits included). The version it replaces is kept so the change can be undone,
    the new text is checked for invented claims again (the rep's own request counts as a source:
    a fact they typed is theirs), and the draft stays a draft: nothing is sent."""
    draft = await _get_draft(session, organization_id, draft_id)
    if draft is None:
        return None
    if draft.status != DRAFT_STATUS_DRAFT:
        raise DraftNotEditableError(f"draft {draft_id} was already {draft.status}")

    company = await get_company_detail(session, organization_id, draft.company_id)
    if company is None:
        raise CompanyNotFoundError(f"company {draft.company_id} not found")
    contact = next((c for c in company.contacts if c.id == draft.contact_id), None)
    if contact is None:
        raise ContactNotFoundError(f"contact {draft.contact_id} not found on this company")
    if company.needs_review:
        raise NeedsReviewError(f"company {company.id} needs review before drafting")
    if company.dismissed_at is not None:
        raise NeedsReviewError(f"company {company.id} was marked not a fit; restore it to draft")
    if contact.needs_review:
        raise NeedsReviewError(f"contact {contact.id} needs review before drafting")
    product = await get_product(session, organization_id, draft.product_id)
    if product is None:
        raise ProductNotFoundError(f"product {draft.product_id} not found")

    recommendation = (
        await session.get(Recommendation, draft.recommendation_id)
        if draft.recommendation_id
        else None
    )
    role_relevance = await get_latest_role_relevance_for_contact(
        session, organization_id, contact.id
    )
    framing_style = (
        role_relevance.matched_category_framing_style
        if role_relevance and role_relevance.matched_category_framing_style
        else None
    ) or await _style_from_buying_role(
        session, draft.company_opportunity_id, contact.id, [product.id]
    )
    evidence = await build_draft_evidence(session, organization_id, company, contact)

    result = await generator.refine(
        company, contact, product, recommendation, framing_style, subject, body, instruction
    )
    new_subject = result.subject or subject or None
    if new_subject is not None:
        new_subject = new_subject[:255]
    flags = find_unsupported_claims(
        f"{new_subject or ''}\n{result.body}",
        [*_allowed_sources(company, product, recommendation, evidence), instruction],
    )

    revisions = list(draft.revisions or [])
    revisions.append(
        {
            "instruction": draft.instruction,
            "subject": subject,
            "body": body,
            "grounding_flags": draft.grounding_flags,
            "model_used": draft.model_used,
            "prompt_version": draft.prompt_version,
            "saved_at": datetime.now(UTC).isoformat(),
        }
    )
    draft.revisions = revisions[-MAX_REVISIONS:]
    draft.subject = new_subject
    draft.body = result.body
    draft.instruction = instruction
    draft.model_used = generator.model_name
    draft.prompt_version = REFINE_PROMPT_VERSION
    draft.grounding_flags = flags or None
    await session.flush()
    return draft


async def undo_draft(
    session: AsyncSession, organization_id: uuid.UUID, draft_id: uuid.UUID
) -> Draft | None:
    """Go back to the version the last rewrite replaced."""
    draft = await _get_draft(session, organization_id, draft_id)
    if draft is None:
        return None
    if draft.status != DRAFT_STATUS_DRAFT:
        raise DraftNotEditableError(f"draft {draft_id} was already {draft.status}")
    revisions = list(draft.revisions or [])
    if not revisions:
        raise NothingToUndoError("there is no earlier version of this draft")
    previous = revisions.pop()
    draft.revisions = revisions or None
    draft.subject = previous.get("subject")
    draft.body = previous.get("body") or draft.body
    draft.instruction = previous.get("instruction")
    draft.grounding_flags = previous.get("grounding_flags")
    draft.model_used = previous.get("model_used") or draft.model_used
    draft.prompt_version = previous.get("prompt_version")
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
            grounding_flags=d.grounding_flags,
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
