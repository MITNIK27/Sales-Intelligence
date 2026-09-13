import uuid

import pytest

from app.modules.ai_recommendation.models import Recommendation
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.draft.mock import MockDraftGenerator
from app.modules.draft.models import (
    DRAFT_STATUS_DISCARDED,
    DRAFT_STATUS_DRAFT,
    DRAFT_STATUS_SENT,
    DRAFT_TYPE_FIRST_TOUCH,
)
from app.modules.draft.service import (
    CompanyNotFoundError,
    ContactNotFoundError,
    ProductNotFoundError,
    discard_draft,
    generate_draft,
    list_drafts,
    mark_draft_sent,
    update_draft,
)
from app.modules.products.models import Product
from app.modules.role_relevance.models import RoleCategory, RoleRelevanceResult


async def _make_company_contact_product(session, organization_id):
    company = Company(
        organization_id=organization_id, name="Acme", domain=f"acme-{uuid.uuid4()}.com"
    )
    session.add(company)
    await session.flush()
    contact = Contact(organization_id=organization_id, company_id=company.id, full_name="Jane")
    session.add(contact)
    product = Product(organization_id=organization_id, name="Widget Pro", description="Widgets.")
    session.add(product)
    await session.commit()
    return company, contact, product


async def test_generate_draft_raises_for_missing_company(db_session, organization_id) -> None:
    with pytest.raises(CompanyNotFoundError):
        await generate_draft(
            db_session,
            organization_id,
            uuid.uuid4(),
            uuid.uuid4(),
            uuid.uuid4(),
            DRAFT_TYPE_FIRST_TOUCH,
            MockDraftGenerator(),
        )


async def test_generate_draft_raises_for_contact_not_on_company(
    db_session, organization_id
) -> None:
    company, _contact, product = await _make_company_contact_product(db_session, organization_id)
    with pytest.raises(ContactNotFoundError):
        await generate_draft(
            db_session,
            organization_id,
            company.id,
            uuid.uuid4(),
            product.id,
            DRAFT_TYPE_FIRST_TOUCH,
            MockDraftGenerator(),
        )


async def test_generate_draft_raises_for_missing_product(db_session, organization_id) -> None:
    company, contact, _product = await _make_company_contact_product(db_session, organization_id)
    with pytest.raises(ProductNotFoundError):
        await generate_draft(
            db_session,
            organization_id,
            company.id,
            contact.id,
            uuid.uuid4(),
            DRAFT_TYPE_FIRST_TOUCH,
            MockDraftGenerator(),
        )


async def test_generate_draft_persists_result_without_grounding(
    db_session, organization_id
) -> None:
    company, contact, product = await _make_company_contact_product(db_session, organization_id)

    draft = await generate_draft(
        db_session,
        organization_id,
        company.id,
        contact.id,
        product.id,
        DRAFT_TYPE_FIRST_TOUCH,
        MockDraftGenerator(),
    )
    await db_session.commit()

    assert draft.status == DRAFT_STATUS_DRAFT
    assert draft.recommendation_id is None
    assert draft.model_used == "mock"
    assert draft.subject == "Canned subject for testing"


async def test_generate_draft_grounds_in_latest_matching_recommendation(
    db_session, organization_id
) -> None:
    company, contact, product = await _make_company_contact_product(db_session, organization_id)
    recommendation = Recommendation(
        organization_id=organization_id,
        company_id=company.id,
        product_id=product.id,
        pitch_summary="s",
        why_this_company="w",
        talking_points=["a"],
        model_used="mock",
    )
    db_session.add(recommendation)
    await db_session.commit()

    draft = await generate_draft(
        db_session,
        organization_id,
        company.id,
        contact.id,
        product.id,
        DRAFT_TYPE_FIRST_TOUCH,
        MockDraftGenerator(),
    )
    await db_session.commit()

    assert draft.recommendation_id == recommendation.id


async def test_generate_draft_falls_back_to_business_framing_when_unclassified(
    db_session, organization_id
) -> None:
    """Not a hard failure -- the contact simply hasn't been through Phase A3 role classification
    yet, which is a valid, expected state, not an error."""
    company, contact, product = await _make_company_contact_product(db_session, organization_id)

    captured: dict[str, object] = {}

    class _CapturingGenerator(MockDraftGenerator):
        async def generate(  # type: ignore[no-untyped-def]
            self, company, contact, product, recommendation, framing_style, draft_type
        ):
            captured["framing_style"] = framing_style
            return await super().generate(
                company, contact, product, recommendation, framing_style, draft_type
            )

    await generate_draft(
        db_session,
        organization_id,
        company.id,
        contact.id,
        product.id,
        DRAFT_TYPE_FIRST_TOUCH,
        _CapturingGenerator(),
    )

    assert captured["framing_style"] == "business"


async def test_generate_draft_uses_contacts_latest_role_relevance_framing(
    db_session, organization_id
) -> None:
    company, contact, product = await _make_company_contact_product(db_session, organization_id)
    category = RoleCategory(
        organization_id=organization_id,
        name="Engineering Lead",
        is_primary_target=True,
        is_active=True,
        framing_style="technical",
    )
    db_session.add(category)
    await db_session.flush()
    result = RoleRelevanceResult(
        organization_id=organization_id,
        company_id=company.id,
        contact_id=contact.id,
        matched_category_id=category.id,
        matched_category_name=category.name,
        is_primary_target=True,
        matched_category_framing_style="technical",
        priority="primary",
        reasoning="r",
        model_used="mock",
    )
    db_session.add(result)
    await db_session.commit()

    captured: dict[str, object] = {}

    class _CapturingGenerator(MockDraftGenerator):
        async def generate(  # type: ignore[no-untyped-def]
            self, company, contact, product, recommendation, framing_style, draft_type
        ):
            captured["framing_style"] = framing_style
            return await super().generate(
                company, contact, product, recommendation, framing_style, draft_type
            )

    await generate_draft(
        db_session,
        organization_id,
        company.id,
        contact.id,
        product.id,
        DRAFT_TYPE_FIRST_TOUCH,
        _CapturingGenerator(),
    )

    assert captured["framing_style"] == "technical"


async def test_update_draft_mutates_in_place(db_session, organization_id) -> None:
    company, contact, product = await _make_company_contact_product(db_session, organization_id)
    draft = await generate_draft(
        db_session,
        organization_id,
        company.id,
        contact.id,
        product.id,
        DRAFT_TYPE_FIRST_TOUCH,
        MockDraftGenerator(),
    )
    await db_session.commit()
    original_id = draft.id

    updated = await update_draft(
        db_session, organization_id, draft.id, subject="Edited subject", body="Edited body"
    )
    await db_session.commit()

    assert updated is not None
    assert updated.id == original_id  # same row, not a new append-only entry
    assert updated.subject == "Edited subject"
    assert updated.body == "Edited body"


async def test_discard_and_mark_sent_transitions(db_session, organization_id) -> None:
    company, contact, product = await _make_company_contact_product(db_session, organization_id)
    draft = await generate_draft(
        db_session,
        organization_id,
        company.id,
        contact.id,
        product.id,
        DRAFT_TYPE_FIRST_TOUCH,
        MockDraftGenerator(),
    )
    await db_session.commit()

    discarded = await discard_draft(db_session, organization_id, draft.id)
    await db_session.commit()
    assert discarded is not None
    assert discarded.status == DRAFT_STATUS_DISCARDED

    sent = await mark_draft_sent(db_session, organization_id, draft.id)
    await db_session.commit()
    assert sent is not None
    assert sent.status == DRAFT_STATUS_SENT


async def test_list_drafts_filters_by_contact(db_session, organization_id) -> None:
    company, contact, product = await _make_company_contact_product(db_session, organization_id)
    other_contact = Contact(
        organization_id=organization_id, company_id=company.id, full_name="Other"
    )
    db_session.add(other_contact)
    await db_session.commit()

    await generate_draft(
        db_session, organization_id, company.id, contact.id, product.id,
        DRAFT_TYPE_FIRST_TOUCH, MockDraftGenerator(),
    )
    await generate_draft(
        db_session, organization_id, company.id, other_contact.id, product.id,
        DRAFT_TYPE_FIRST_TOUCH, MockDraftGenerator(),
    )
    await db_session.commit()

    all_drafts = await list_drafts(db_session, organization_id, company.id)
    assert len(all_drafts) == 2

    only_contact = await list_drafts(db_session, organization_id, company.id, contact.id)
    assert len(only_contact) == 1
    assert only_contact[0].contact_id == contact.id
