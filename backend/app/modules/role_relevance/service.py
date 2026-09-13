import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_recommendation.gemini_client import GeminiClientError
from app.modules.companies.models import Company
from app.modules.companies.service import get_company_detail
from app.modules.contacts.models import Contact
from app.modules.role_relevance.models import (
    FRAMING_STYLE_BUSINESS,
    RoleCategory,
    RoleRelevanceResult,
)
from app.modules.role_relevance.role_relevance_generator import RoleRelevanceGenerator


async def create_category(
    session: AsyncSession,
    organization_id: uuid.UUID,
    name: str,
    description: str | None,
    is_primary_target: bool,
    is_active: bool,
    framing_style: str = FRAMING_STYLE_BUSINESS,
) -> RoleCategory:
    category = RoleCategory(
        organization_id=organization_id,
        name=name,
        description=description,
        is_primary_target=is_primary_target,
        is_active=is_active,
        framing_style=framing_style,
    )
    session.add(category)
    await session.flush()
    return category


async def list_categories(
    session: AsyncSession, organization_id: uuid.UUID, limit: int = 50, offset: int = 0
) -> tuple[list[RoleCategory], int]:
    count_stmt = select(func.count()).select_from(RoleCategory).where(
        RoleCategory.organization_id == organization_id
    )
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = (
        select(RoleCategory)
        .where(RoleCategory.organization_id == organization_id)
        .order_by(RoleCategory.name)
        .limit(limit)
        .offset(offset)
    )
    categories = (await session.execute(stmt)).scalars().all()
    return list(categories), total


async def get_category(
    session: AsyncSession, organization_id: uuid.UUID, category_id: uuid.UUID
) -> RoleCategory | None:
    category = await session.get(RoleCategory, category_id)
    if category is None or category.organization_id != organization_id:
        return None
    return category


async def update_category(
    session: AsyncSession,
    organization_id: uuid.UUID,
    category_id: uuid.UUID,
    updates: dict[str, object],
) -> RoleCategory | None:
    """`updates` should already be limited to explicitly-provided fields (e.g. via
    `RoleCategoryUpdate.model_dump(exclude_unset=True)`) so an omitted field is left untouched
    while an explicit `null` still clears it."""
    category = await get_category(session, organization_id, category_id)
    if category is None:
        return None
    for field, value in updates.items():
        setattr(category, field, value)
    await session.flush()
    return category


async def delete_category(
    session: AsyncSession, organization_id: uuid.UUID, category_id: uuid.UUID
) -> bool:
    category = await get_category(session, organization_id, category_id)
    if category is None:
        return False
    await session.delete(category)
    await session.flush()
    return True


async def list_active_categories(
    session: AsyncSession, organization_id: uuid.UUID
) -> list[RoleCategory]:
    stmt = (
        select(RoleCategory)
        .where(
            RoleCategory.organization_id == organization_id,
            RoleCategory.is_active.is_(True),
        )
        .order_by(RoleCategory.name)
    )
    return list((await session.execute(stmt)).scalars().all())


class CompanyNotFoundError(Exception):
    """Raised by `run_role_relevance_check` when the company doesn't exist or belongs to a
    different organization — the router surfaces this as a 404."""


class NoContactsError(Exception):
    """Raised by `run_role_relevance_check` when the company has zero contacts — there is nothing
    to classify. The router surfaces this as a 422."""


class NoCategoriesConfiguredError(Exception):
    """Raised by `run_role_relevance_check` when the org has zero active role categories —
    classifying against nothing isn't a classification. The router surfaces this as a 422."""


def _compute_priority(matched: RoleCategory | None) -> str:
    """Deterministic — never decided by the LLM. A contact matched to a primary-target category
    is "primary"; matched to any other active category is "secondary"; no genuine match at all is
    "not_relevant" (a valid, expected outcome, not a failure of the judgment)."""
    if matched is None:
        return "not_relevant"
    return "primary" if matched.is_primary_target else "secondary"


async def judge_role_relevance(
    company: Company,
    contacts: list[Contact],
    categories: list[RoleCategory],
    generator: RoleRelevanceGenerator,
) -> list[dict[str, object]]:
    """Pure core: no session, no persistence. Calls the generator, snapshots each matched
    category AS JUDGED (not a live reference — a later edit to the category must never rewrite
    this history), and computes the deterministic priority."""
    judgment = await generator.generate(company, contacts, categories)

    categories_by_id = {str(category.id): category for category in categories}
    verdicts_by_id = {v.contact_id: v for v in judgment.contact_results}
    contact_ids = {str(contact.id) for contact in contacts}
    if set(verdicts_by_id) != contact_ids:
        raise GeminiClientError("Gemini did not return exactly one verdict per given contact")

    results: list[dict[str, object]] = []
    for contact in contacts:
        verdict = verdicts_by_id[str(contact.id)]
        matched = (
            categories_by_id.get(verdict.matched_category_id)
            if verdict.matched_category_id
            else None
        )
        results.append(
            {
                "contact_id": contact.id,
                "matched_category_id": matched.id if matched else None,
                "matched_category_name": matched.name if matched else None,
                "is_primary_target": matched.is_primary_target if matched else False,
                "matched_category_framing_style": matched.framing_style if matched else None,
                "priority": _compute_priority(matched),
                "reasoning": verdict.reasoning,
            }
        )
    return results


async def run_role_relevance_check(
    session: AsyncSession,
    organization_id: uuid.UUID,
    company_id: uuid.UUID,
    generator: RoleRelevanceGenerator,
) -> list[RoleRelevanceResult]:
    company = await get_company_detail(session, organization_id, company_id)
    if company is None:
        raise CompanyNotFoundError(f"company {company_id} not found")

    if not company.contacts:
        raise NoContactsError("this company has no contacts to classify")

    categories = await list_active_categories(session, organization_id)
    if not categories:
        raise NoCategoriesConfiguredError("no active role categories configured")

    judged = await judge_role_relevance(company, company.contacts, categories, generator)

    results = [
        RoleRelevanceResult(
            organization_id=organization_id,
            company_id=company_id,
            contact_id=entry["contact_id"],
            matched_category_id=entry["matched_category_id"],
            matched_category_name=entry["matched_category_name"],
            is_primary_target=entry["is_primary_target"],
            matched_category_framing_style=entry["matched_category_framing_style"],
            priority=entry["priority"],
            reasoning=entry["reasoning"],
            model_used=generator.model_name,
        )
        for entry in judged
    ]
    session.add_all(results)
    await session.flush()
    return results


async def list_latest_role_relevance(
    session: AsyncSession, organization_id: uuid.UUID, company_id: uuid.UUID
) -> dict[uuid.UUID, RoleRelevanceResult]:
    """The most recent result per contact_id, for display without re-running. Contact lists are
    small enough that fetching all rows and keeping the first occurrence per contact in Python is
    simpler than a window-function query."""
    stmt = (
        select(RoleRelevanceResult)
        .where(
            RoleRelevanceResult.organization_id == organization_id,
            RoleRelevanceResult.company_id == company_id,
        )
        .order_by(RoleRelevanceResult.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    latest: dict[uuid.UUID, RoleRelevanceResult] = {}
    for row in rows:
        latest.setdefault(row.contact_id, row)
    return latest


async def get_latest_role_relevance_for_contact(
    session: AsyncSession, organization_id: uuid.UUID, contact_id: uuid.UUID
) -> RoleRelevanceResult | None:
    """Single-contact lookup — used by Phase B's draft generator to resolve persona framing for
    one specific recipient, where `list_latest_role_relevance`'s whole-company dict would be
    overkill."""
    stmt = (
        select(RoleRelevanceResult)
        .where(
            RoleRelevanceResult.organization_id == organization_id,
            RoleRelevanceResult.contact_id == contact_id,
        )
        .order_by(RoleRelevanceResult.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()
