import uuid
from datetime import UTC, datetime

import pytest

from app.modules.ai_recommendation.mock import MockRecommendationGenerator
from app.modules.ai_recommendation.recommendation_generator import RecommendationResult
from app.modules.ai_recommendation.service import (
    CompanyNotFoundError,
    ProductNotFoundError,
    generate_recommendation,
    list_recommendations,
)
from app.modules.companies.service import get_or_create_company
from app.modules.contacts.service import get_or_create_contact
from app.modules.products.service import create_product


async def test_full_recommendation_flow(db_session, organization_id) -> None:
    company, _ = await get_or_create_company(
        db_session, organization_id, name="Acme Inc", domain="acme.com"
    )
    contact, _ = await get_or_create_contact(
        db_session,
        organization_id,
        company_id=company.id,
        full_name="Jane Doe",
        role_title="VP Engineering",
        email="jane@acme.com",
    )
    product = await create_product(
        db_session, organization_id, name="Widget Pro", description="The best widget."
    )
    await db_session.commit()

    generator = MockRecommendationGenerator(
        RecommendationResult(
            pitch_summary="Pitch Widget Pro to Acme.",
            why_this_company="Acme is a growing company that needs widgets.",
            talking_points=["Point one", "Point two", "Point three"],
        )
    )

    recommendation = await generate_recommendation(
        db_session, organization_id, company.id, product.id, contact.id, generator
    )
    await db_session.commit()

    assert recommendation.company_id == company.id
    assert recommendation.contact_id == contact.id
    assert recommendation.product_id == product.id
    assert recommendation.pitch_summary == "Pitch Widget Pro to Acme."
    assert recommendation.why_this_company == "Acme is a growing company that needs widgets."
    assert recommendation.talking_points == ["Point one", "Point two", "Point three"]
    assert recommendation.model_used == "mock"
    assert recommendation.created_at is not None

    recommendations = await list_recommendations(db_session, organization_id, company.id)
    assert len(recommendations) == 1
    assert recommendations[0].id == recommendation.id


async def test_generate_recommendation_supports_no_specific_contact(
    db_session, organization_id
) -> None:
    company, _ = await get_or_create_company(
        db_session, organization_id, name="Acme Inc", domain="acme.com"
    )
    product = await create_product(db_session, organization_id, name="Widget", description=None)
    await db_session.commit()

    recommendation = await generate_recommendation(
        db_session, organization_id, company.id, product.id, None, MockRecommendationGenerator()
    )
    await db_session.commit()

    assert recommendation.contact_id is None


async def test_list_recommendations_newest_first(db_session, organization_id) -> None:
    company, _ = await get_or_create_company(
        db_session, organization_id, name="Acme Inc", domain="acme.com"
    )
    product = await create_product(db_session, organization_id, name="Widget", description=None)
    await db_session.commit()

    # created_at is pinned explicitly below (rather than relying on two back-to-back
    # datetime.now(UTC) calls landing in different microseconds) so "newest first" ordering is
    # deterministic, not a coin flip on timestamp resolution.
    generator = MockRecommendationGenerator()
    first = await generate_recommendation(
        db_session, organization_id, company.id, product.id, None, generator
    )
    first.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    await db_session.commit()
    second = await generate_recommendation(
        db_session, organization_id, company.id, product.id, None, generator
    )
    second.created_at = datetime(2024, 1, 2, tzinfo=UTC)
    await db_session.commit()

    recommendations = await list_recommendations(db_session, organization_id, company.id)
    assert [r.id for r in recommendations] == [second.id, first.id]


async def test_generate_recommendation_raises_for_missing_or_wrong_org_company(
    db_session, organization_id
) -> None:
    product = await create_product(db_session, organization_id, name="Widget", description=None)
    await db_session.commit()

    with pytest.raises(CompanyNotFoundError):
        await generate_recommendation(
            db_session,
            organization_id,
            uuid.uuid4(),
            product.id,
            None,
            MockRecommendationGenerator(),
        )

    other_org = uuid.uuid4()
    from app.modules.auth.models import Organization

    db_session.add(Organization(id=other_org, name="Other Org"))
    company, _ = await get_or_create_company(
        db_session, other_org, name="Wrong Org Co", domain="wrongorg.com"
    )
    await db_session.commit()

    with pytest.raises(CompanyNotFoundError):
        await generate_recommendation(
            db_session,
            organization_id,
            company.id,
            product.id,
            None,
            MockRecommendationGenerator(),
        )


async def test_generate_recommendation_raises_for_missing_or_wrong_org_product(
    db_session, organization_id
) -> None:
    company, _ = await get_or_create_company(
        db_session, organization_id, name="Acme Inc", domain="acme.com"
    )
    await db_session.commit()

    with pytest.raises(ProductNotFoundError):
        await generate_recommendation(
            db_session,
            organization_id,
            company.id,
            uuid.uuid4(),
            None,
            MockRecommendationGenerator(),
        )

    other_org = uuid.uuid4()
    from app.modules.auth.models import Organization

    db_session.add(Organization(id=other_org, name="Other Org 2"))
    await db_session.commit()
    other_product = await create_product(
        db_session, other_org, name="Other Product", description=None
    )
    await db_session.commit()

    with pytest.raises(ProductNotFoundError):
        await generate_recommendation(
            db_session,
            organization_id,
            company.id,
            other_product.id,
            None,
            MockRecommendationGenerator(),
        )
