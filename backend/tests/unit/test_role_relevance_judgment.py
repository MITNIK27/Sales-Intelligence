import uuid

import pytest

from app.modules.ai_recommendation.gemini_client import GeminiClientError
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.role_relevance.models import RoleCategory
from app.modules.role_relevance.role_relevance_generator import (
    ContactRoleVerdict,
    RoleRelevanceJudgment,
)
from app.modules.role_relevance.service import (
    CompanyNotFoundError,
    NoCategoriesConfiguredError,
    NoContactsError,
    _compute_priority,
    create_category,
    judge_role_relevance,
    run_role_relevance_check,
)


def _company(**overrides: object) -> Company:
    defaults: dict[str, object] = {
        "name": "Acme Inc",
        "domain": "acme.com",
        "industry": "Logistics",
        "description": "Acme moves parcels across Europe.",
    }
    defaults.update(overrides)
    return Company(**defaults)  # type: ignore[arg-type]


def _contact(**overrides: object) -> Contact:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "full_name": "Jane Doe",
        "role_title": "Category Procurement Manager",
        "seniority": "Manager",
    }
    defaults.update(overrides)
    return Contact(**defaults)  # type: ignore[arg-type]


def _category(**overrides: object) -> RoleCategory:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "name": "Vendor / IT Procurement",
        "description": "Evaluates and selects technology vendors.",
        "is_primary_target": True,
        "is_active": True,
        "framing_style": "business",
    }
    defaults.update(overrides)
    return RoleCategory(**defaults)  # type: ignore[arg-type]


class _FakeGenerator:
    def __init__(self, matches: dict[str, str | None]) -> None:
        self._matches = matches

    @property
    def model_name(self) -> str:
        return "fake-model"

    async def generate(self, company, contacts, categories) -> RoleRelevanceJudgment:  # type: ignore[no-untyped-def]
        return RoleRelevanceJudgment(
            contact_results=[
                ContactRoleVerdict(
                    contact_id=str(c.id),
                    matched_category_id=self._matches[str(c.id)],
                    reasoning="r",
                )
                for c in contacts
            ]
        )


# --- _compute_priority (pure, deterministic) ---


def test_priority_primary_when_matched_category_is_primary_target() -> None:
    assert _compute_priority(_category(is_primary_target=True)) == "primary"


def test_priority_secondary_when_matched_category_is_not_primary_target() -> None:
    assert _compute_priority(_category(is_primary_target=False)) == "secondary"


def test_priority_not_relevant_when_no_category_matched() -> None:
    assert _compute_priority(None) == "not_relevant"


# --- judge_role_relevance (pure core, fake generator) ---


async def test_judge_role_relevance_snapshots_category_and_computes_priority() -> None:
    category = _category(is_primary_target=True)
    contact = _contact()
    generator = _FakeGenerator({str(contact.id): str(category.id)})

    results = await judge_role_relevance(_company(), [contact], [category], generator)  # type: ignore[arg-type]

    assert results == [
        {
            "contact_id": contact.id,
            "matched_category_id": category.id,
            "matched_category_name": "Vendor / IT Procurement",
            "is_primary_target": True,
            "matched_category_framing_style": "business",
            "priority": "primary",
            "reasoning": "r",
        }
    ]


async def test_judge_role_relevance_handles_null_match() -> None:
    contact = _contact(role_title="Head of Marketing")
    generator = _FakeGenerator({str(contact.id): None})

    results = await judge_role_relevance(_company(), [contact], [_category()], generator)  # type: ignore[arg-type]

    assert results[0]["matched_category_id"] is None
    assert results[0]["priority"] == "not_relevant"
    assert results[0]["matched_category_framing_style"] is None


async def test_judge_role_relevance_snapshots_technical_framing_style() -> None:
    category = _category(framing_style="technical")
    contact = _contact()
    generator = _FakeGenerator({str(contact.id): str(category.id)})

    results = await judge_role_relevance(_company(), [contact], [category], generator)  # type: ignore[arg-type]

    assert results[0]["matched_category_framing_style"] == "technical"


async def test_judge_role_relevance_raises_on_contact_id_mismatch() -> None:
    contact = _contact()

    class _BadGenerator:
        model_name = "fake-model"

        async def generate(self, company, contacts, categories) -> RoleRelevanceJudgment:  # type: ignore[no-untyped-def]
            return RoleRelevanceJudgment(
                contact_results=[
                    ContactRoleVerdict(
                        contact_id="not-a-real-id", matched_category_id=None, reasoning="r"
                    )
                ]
            )

    with pytest.raises(GeminiClientError, match="exactly one verdict per given contact"):
        await judge_role_relevance(_company(), [contact], [_category()], _BadGenerator())  # type: ignore[arg-type]


# --- run_role_relevance_check (DB-backed) ---


async def test_run_role_relevance_check_raises_for_missing_company(
    db_session, organization_id
) -> None:
    generator = _FakeGenerator({})
    with pytest.raises(CompanyNotFoundError):
        await run_role_relevance_check(
            db_session, organization_id, uuid.uuid4(), generator  # type: ignore[arg-type]
        )


async def test_run_role_relevance_check_raises_without_contacts(
    db_session, organization_id
) -> None:
    company = Company(organization_id=organization_id, name="Acme", domain="acme.com")
    db_session.add(company)
    await db_session.commit()

    generator = _FakeGenerator({})
    with pytest.raises(NoContactsError):
        await run_role_relevance_check(
            db_session, organization_id, company.id, generator  # type: ignore[arg-type]
        )


async def test_run_role_relevance_check_raises_without_active_categories(
    db_session, organization_id
) -> None:
    company = Company(organization_id=organization_id, name="Acme", domain="acme.com")
    db_session.add(company)
    await db_session.flush()
    contact = Contact(organization_id=organization_id, company_id=company.id, full_name="Jane")
    db_session.add(contact)
    await db_session.commit()

    generator = _FakeGenerator({})
    with pytest.raises(NoCategoriesConfiguredError):
        await run_role_relevance_check(
            db_session, organization_id, company.id, generator  # type: ignore[arg-type]
        )


async def test_run_role_relevance_check_excludes_inactive_categories_and_persists_history(
    db_session, organization_id
) -> None:
    company = Company(organization_id=organization_id, name="Acme", domain="acme.com")
    db_session.add(company)
    await db_session.flush()
    contact = Contact(
        organization_id=organization_id,
        company_id=company.id,
        full_name="Jane",
        role_title="Category Procurement Manager",
    )
    db_session.add(contact)
    active = await create_category(
        db_session, organization_id, name="Active one", description=None,
        is_primary_target=True, is_active=True,
    )
    await create_category(
        db_session, organization_id, name="Inactive one", description=None,
        is_primary_target=True, is_active=False,
    )
    await db_session.commit()

    generator = _FakeGenerator({str(contact.id): str(active.id)})

    first = await run_role_relevance_check(
        db_session, organization_id, company.id, generator  # type: ignore[arg-type]
    )
    await db_session.commit()
    assert len(first) == 1
    assert first[0].matched_category_name == "Active one"
    assert first[0].priority == "primary"

    second = await run_role_relevance_check(
        db_session, organization_id, company.id, generator  # type: ignore[arg-type]
    )
    await db_session.commit()

    assert first[0].id != second[0].id  # append-only: a re-check creates new rows, not overwrites
