"""Which people at a company matter for an opportunity. A model judges each contact from the title
and seniority alone (never the name), the company's context, the area and the offering's buyer
profile, and says what part the person plays in a purchase: decides, influences, uses, or is not
involved. A person can override any judgment; the override is its own row, shown as such, and the
model's judgment stays visible beneath it. Names never leave the system: the model sees labels."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.llm.structured import StructuredLLM
from app.modules.opportunity.assessment import model_names
from app.modules.opportunity.models import (
    ROLE_DECISION_MAKER,
    ROLE_INFLUENCER,
    ROLE_NOT_RELEVANT,
    ROLE_REVERT,
    ROLE_USER,
    ROLES,
    SOURCE_HUMAN,
    SOURCE_MODEL,
    CompanyOpportunity,
    ContactOpportunityRelevance,
)
from app.modules.opportunity.service import latest_assessment
from app.modules.products.models import Product

RELEVANCE_PROMPT_VERSION = "v1"
MAX_CONTACTS_JUDGED = 25
NO_TITLE_REASON = "No job title is known, so this person's part in the decision cannot be judged."
_CONFIDENCES = ("low", "medium", "high")


class ContactRoleOut(BaseModel):
    contact: str  # label such as C3; never a name or an id
    role: str  # decision_maker | influencer | user | not_relevant
    function: str | None = None  # the business function the title implies
    reasoning: str
    confidence: str = "medium"


class RelevanceOut(BaseModel):
    contacts: list[ContactRoleOut] = []


@dataclass(frozen=True)
class Resolved:
    """What to show for a contact: the person's override if there is one, else the model's
    judgment, with the model's own view kept when it was overridden."""

    contact_id: object
    role: str
    function: str | None
    reasoning: str
    confidence: str | None
    needs_review: bool
    source: str  # model | human
    note: str | None = None
    model_role: str | None = None
    model_reasoning: str | None = None


def contact_hash(contact: Contact) -> str:
    """A fingerprint of what was judged, so a changed title or seniority is judged again."""
    text = (
        f"{(contact.role_title or '').strip().lower()}|{(contact.seniority or '').strip().lower()}"
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_relevance_prompt(
    company: Company,
    opportunity: CompanyOpportunity,
    product: Product | None,
    contacts: list[tuple[str, Contact]],
) -> str:
    profile = (product.buyer_profile if product else None) or {}
    offering = (
        f"Offering: {product.name} ({product.kind})\n"
        f"Usually bought by: {', '.join(profile.get('buyer_functions', [])) or 'not specified'}\n"
        f"Others who weigh in: "
        f"{', '.join(profile.get('influencer_functions', [])) or 'not specified'}"
        if product
        else "Offering: not chosen yet; judge by the business area alone."
    )
    people = "\n".join(
        f"[{label}] title: {c.role_title or '(unknown)'}, seniority: {c.seniority or '(unknown)'}"
        for label, c in contacts
    )
    return f"""You are judging what part each person at a company would play in a purchase, so a \
salesperson knows who to approach first.

Company: {company.name}
Industry: {opportunity.industry_context or company.industry or "unknown"}
Business area: {opportunity.area_label}
{offering}

Roles:
- decision_maker: decides, or controls the budget, for something like this.
- influencer: shapes or evaluates the decision.
- user: would use it or feel its effect day to day, without deciding.
- not_relevant: no real part in a decision like this.

Rules:
- Judge by the business FUNCTION the title describes, not how senior it sounds. A senior title in \
an unrelated function is not_relevant; a junior title in the right function can be an influencer.
- The same function has different titles in different companies, so reason from what the title \
implies, not from exact wording.
- Give a confidence (low, medium or high). Use low when the title is vague.

People:
{people}

For each person return the label, a role, the function the title implies, one sentence of \
reasoning and a confidence."""


def _after(newest: datetime | None) -> datetime:
    """Now, but never earlier than (or equal to) the newest existing row. These tables are read as
    "the latest row wins", so a row written within the same clock tick as the one it replaces must
    still sort after it."""
    now = datetime.now(UTC)
    if newest is None:
        return now
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=UTC)
    return now if now > newest else newest + timedelta(microseconds=1)


async def _newest_time(
    session: AsyncSession, opportunity_id: object, contact_id: object, product_id: object | None
) -> datetime | None:
    stmt = select(ContactOpportunityRelevance.created_at).where(
        ContactOpportunityRelevance.company_opportunity_id == opportunity_id,
        ContactOpportunityRelevance.contact_id == contact_id,
        (
            ContactOpportunityRelevance.product_id == product_id
            if product_id is not None
            else ContactOpportunityRelevance.product_id.is_(None)
        ),
    )
    times = list((await session.execute(stmt)).scalars().all())
    return max(times) if times else None


def _clean_role(role: str) -> str:
    role = role.strip().lower().replace(" ", "_").replace("-", "_")
    return role if role in ROLES else ROLE_NOT_RELEVANT


def _clean_confidence(confidence: str) -> str:
    confidence = confidence.strip().lower()
    return confidence if confidence in _CONFIDENCES else "low"


async def _model_rows(
    session: AsyncSession, opportunity_id: object, product_id: object | None, source: str
) -> list[ContactOpportunityRelevance]:
    stmt = select(ContactOpportunityRelevance).where(
        ContactOpportunityRelevance.company_opportunity_id == opportunity_id,
        ContactOpportunityRelevance.source == source,
        (
            ContactOpportunityRelevance.product_id == product_id
            if product_id is not None
            else ContactOpportunityRelevance.product_id.is_(None)
        ),
    )
    return list(
        (await session.execute(stmt.order_by(ContactOpportunityRelevance.created_at.desc())))
        .scalars()
        .all()
    )


def _newest_per_contact(
    rows: list[ContactOpportunityRelevance],
) -> dict[object, ContactOpportunityRelevance]:
    newest: dict[object, ContactOpportunityRelevance] = {}
    for row in rows:  # newest first
        newest.setdefault(row.contact_id, row)
    return newest


async def judge_contact_relevance(
    session: AsyncSession,
    llm: StructuredLLM,
    company: Company,
    opportunity: CompanyOpportunity,
    product: Product | None,
    contacts: list[Contact],
    force: bool = False,
) -> list[ContactOpportunityRelevance]:
    """Judge the contacts whose last judgment no longer stands (new, changed title, or a changed
    assessment or offering profile) in one model call; the rest are left as they are."""
    assessment = await latest_assessment(session, opportunity.id)
    assessment_id = assessment.id if assessment else None
    product_id = product.id if product else None
    profile_hash = product.profile_hash if product else None
    existing = _newest_per_contact(
        await _model_rows(session, opportunity.id, product_id, SOURCE_MODEL)
    )

    saved: list[ContactOpportunityRelevance] = []
    to_judge: list[Contact] = []
    for contact in contacts[:MAX_CONTACTS_JUDGED]:
        row = existing.get(contact.id)
        valid = (
            row is not None
            and not force
            and row.contact_hash == contact_hash(contact)
            and row.assessment_id == assessment_id
            and row.profile_hash == profile_hash
            and row.prompt_version == RELEVANCE_PROMPT_VERSION
        )
        if valid:
            continue
        if not (contact.role_title or "").strip():
            saved.append(
                _row(
                    opportunity,
                    contact,
                    product,
                    assessment_id,
                    profile_hash,
                    role=ROLE_NOT_RELEVANT,
                    reasoning=NO_TITLE_REASON,
                    confidence="low",
                    needs_review=True,
                    model_used="none",
                )
            )
        else:
            to_judge.append(contact)

    if to_judge:
        labelled = [(f"C{i}", c) for i, c in enumerate(to_judge, start=1)]
        out = await llm.generate(
            build_relevance_prompt(company, opportunity, product, labelled), RelevanceOut
        )
        answers = {a.contact.strip(): a for a in out.contacts}
        for label, contact in labelled:
            answer = answers.get(label)
            confidence = _clean_confidence(answer.confidence) if answer else "low"
            saved.append(
                _row(
                    opportunity,
                    contact,
                    product,
                    assessment_id,
                    profile_hash,
                    role=_clean_role(answer.role) if answer else ROLE_NOT_RELEVANT,
                    function=(answer.function or "").strip()[:120] or None if answer else None,
                    reasoning=(answer.reasoning.strip()[:600] if answer else "")
                    or "This person was not assessed.",
                    confidence=confidence,
                    needs_review=answer is None or confidence == "low",
                    model_used=model_names(llm),
                )
            )
    session.add_all(saved)
    await session.flush()
    return saved


def _row(
    opportunity: CompanyOpportunity,
    contact: Contact,
    product: Product | None,
    assessment_id: object,
    profile_hash: str | None,
    *,
    role: str,
    reasoning: str,
    confidence: str,
    needs_review: bool,
    model_used: str,
    function: str | None = None,
) -> ContactOpportunityRelevance:
    return ContactOpportunityRelevance(
        organization_id=opportunity.organization_id,
        company_opportunity_id=opportunity.id,
        contact_id=contact.id,
        product_id=product.id if product else None,
        source=SOURCE_MODEL,
        role=role,
        function=function,
        reasoning=reasoning,
        confidence=confidence,
        needs_review=needs_review,
        assessment_id=assessment_id,
        profile_hash=profile_hash,
        contact_hash=contact_hash(contact),
        prompt_version=RELEVANCE_PROMPT_VERSION,
        model_used=model_used[:50],
    )


async def resolve_relevance(
    session: AsyncSession, opportunity_id: object, product_id: object | None
) -> dict[object, Resolved]:
    """The relevance to show for each contact: a person's latest override if it is still in force
    (a `revert` row ends it), otherwise the model's latest judgment."""
    model = _newest_per_contact(
        await _model_rows(session, opportunity_id, product_id, SOURCE_MODEL)
    )
    human = _newest_per_contact(
        await _model_rows(session, opportunity_id, product_id, SOURCE_HUMAN)
    )
    resolved: dict[object, Resolved] = {}
    for contact_id in {*model, *human}:
        m, h = model.get(contact_id), human.get(contact_id)
        if h is not None and h.role != ROLE_REVERT:
            resolved[contact_id] = Resolved(
                contact_id=contact_id,
                role=h.role,
                function=m.function if m else None,
                reasoning=h.note or "Set by a person.",
                confidence=None,
                needs_review=False,
                source=SOURCE_HUMAN,
                note=h.note,
                model_role=m.role if m else None,
                model_reasoning=m.reasoning if m else None,
            )
        elif m is not None:
            resolved[contact_id] = Resolved(
                contact_id=contact_id,
                role=m.role,
                function=m.function,
                reasoning=m.reasoning,
                confidence=m.confidence,
                needs_review=m.needs_review,
                source=SOURCE_MODEL,
            )
    return resolved


async def set_override(
    session: AsyncSession,
    opportunity: CompanyOpportunity,
    contact: Contact,
    product_id: object | None,
    role: str,
    note: str | None,
) -> ContactOpportunityRelevance:
    """Record a person's own view. Never edits the model's row; a later `clear_override` or a new
    override simply adds another row."""
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    row = ContactOpportunityRelevance(
        created_at=_after(await _newest_time(session, opportunity.id, contact.id, product_id)),
        organization_id=opportunity.organization_id,
        company_opportunity_id=opportunity.id,
        contact_id=contact.id,
        product_id=product_id,
        source=SOURCE_HUMAN,
        role=role,
        reasoning=note or "Set by a person.",
        needs_review=False,
        note=(note or "").strip()[:500] or None,
    )
    session.add(row)
    await session.flush()
    return row


async def clear_override(
    session: AsyncSession,
    opportunity: CompanyOpportunity,
    contact: Contact,
    product_id: object | None,
) -> ContactOpportunityRelevance:
    row = await set_override(session, opportunity, contact, product_id, ROLE_NOT_RELEVANT, None)
    row.role = ROLE_REVERT
    await session.flush()
    return row


def relevant_count(resolved: dict[object, Resolved]) -> int:
    """People who decide or influence, the ones worth approaching."""
    return sum(1 for r in resolved.values() if r.role in (ROLE_DECISION_MAKER, ROLE_INFLUENCER))


__all__ = [
    "ROLE_USER",
    "Resolved",
    "build_relevance_prompt",
    "clear_override",
    "contact_hash",
    "judge_contact_relevance",
    "relevant_count",
    "resolve_relevance",
    "set_override",
]
