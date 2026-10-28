"""The cross-company draft list behind the Drafts review page."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.api.v1.drafts import list_all_drafts_endpoint
from app.db.base import Base
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.draft.models import Draft
from app.modules.draft.service import discard_draft, list_all_drafts
from app.modules.products.models import Product


async def _seed(session, org):
    product = Product(organization_id=org, name="Widget", description="w")
    session.add(product)
    await session.flush()
    made = []
    for i, status in enumerate(["draft", "draft", "sent", "discarded", "draft"]):
        company = Company(organization_id=org, name=f"Co{i}", domain=f"co{i}.com")
        session.add(company)
        await session.flush()
        contact = Contact(
            organization_id=org, company_id=company.id, full_name=f"Person{i}", role_title="CTO"
        )
        session.add(contact)
        await session.flush()
        draft = Draft(
            organization_id=org,
            company_id=company.id,
            contact_id=contact.id,
            product_id=product.id,
            draft_type="first_touch",
            channel="email",
            subject=f"Subject {i}",
            body=f"Body {i}",
            status=status,
            model_used="m",
        )
        session.add(draft)
        await session.flush()
        draft.created_at = datetime.now(UTC) - timedelta(minutes=10 - i)  # later i = newer
        made.append(draft)
    await session.commit()
    return made


async def test_lists_every_draft_newest_first_with_who_and_where(
    db_session, organization_id
) -> None:
    await _seed(db_session, organization_id)

    result = await list_all_drafts(db_session, organization_id)

    assert result.total == 5
    assert [i.company_name for i in result.items] == ["Co4", "Co3", "Co2", "Co1", "Co0"]
    first = result.items[0]
    assert (first.contact_name, first.contact_role) == ("Person4", "CTO")
    assert first.subject == "Subject 4"
    assert result.counts == {"draft": 3, "sent": 1, "discarded": 1}


async def test_status_filter_and_pagination_keep_counts_for_the_tabs(
    db_session, organization_id
) -> None:
    await _seed(db_session, organization_id)

    to_review = await list_all_drafts(db_session, organization_id, "draft", limit=2, offset=0)
    assert to_review.total == 3 and len(to_review.items) == 2
    assert all(i.status == "draft" for i in to_review.items)
    assert to_review.counts == {"draft": 3, "sent": 1, "discarded": 1}  # not narrowed by the filter

    rest = await list_all_drafts(db_session, organization_id, "draft", limit=2, offset=2)
    assert len(rest.items) == 1


async def test_a_discarded_draft_moves_tabs_and_the_endpoint_serves_the_same_data(
    db_session, organization_id
) -> None:
    drafts = await _seed(db_session, organization_id)
    await discard_draft(db_session, organization_id, drafts[0].id)
    await db_session.commit()

    via_endpoint = await list_all_drafts_endpoint("discarded", 25, 0, db_session)
    assert via_endpoint.total == 2
    assert via_endpoint.counts["draft"] == 2


async def test_listing_drafts_never_writes(db_session, organization_id) -> None:
    await _seed(db_session, organization_id)

    async def counts() -> dict[str, int]:
        return {
            t.name: (await db_session.execute(select(func.count()).select_from(t))).scalar_one()
            for t in Base.metadata.sorted_tables
        }

    before = await counts()
    await list_all_drafts(db_session, organization_id, "draft")
    await list_all_drafts(db_session, organization_id)
    assert not db_session.dirty and not db_session.new and not db_session.deleted
    assert await counts() == before
