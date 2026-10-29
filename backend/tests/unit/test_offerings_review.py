from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select

from app.db.session import get_db
from app.main import app
from app.modules.jobs.models import STATUS_DONE, Job
from app.modules.offerings.models import (
    CHANGE_CHANGED,
    CHANGE_NEW,
    CHANGE_REMOVED,
    PROPOSAL_APPROVED,
    PROPOSAL_REJECTED,
    OfferingProposal,
)
from app.modules.offerings.review import (
    approve_proposal,
    enqueue_sync_if_due,
    reject_proposal,
    start_sync,
    sync_due,
    sync_status,
)
from app.modules.offerings.service import JOB_TYPE_SYNC_OFFERINGS
from app.modules.products.models import Product
from app.modules.products.service import create_product

URL = "https://infobeans.ai/spacewarp"


def proposal(organization_id, change=CHANGE_NEW, product_id=None, name="Spacewarp"):
    return OfferingProposal(
        organization_id=organization_id,
        product_id=product_id,
        change=change,
        kind="product",
        name=name,
        description="Moves ServiceNow data.",
        source_url=URL,
        content_hash="abc",
    )


async def website_product(session, organization_id) -> Product:
    product = await create_product(session, organization_id, name="Old name", description="Old.")
    product.source = "website"
    product.source_url = URL
    product.source_hash = "old"
    await session.commit()
    return product


async def test_approving_a_new_proposal_creates_the_offering_once(
    db_session, organization_id
) -> None:
    pending = proposal(organization_id)
    db_session.add(pending)
    await db_session.commit()

    await approve_proposal(db_session, organization_id, pending.id)
    again = await approve_proposal(db_session, organization_id, pending.id)  # double click
    await db_session.commit()

    products = (await db_session.execute(select(Product))).scalars().all()
    assert [(p.name, p.kind, p.source, p.source_url, p.status) for p in products] == [
        ("Spacewarp", "product", "website", URL, "active")
    ]
    assert products[0].source_hash == "abc"
    assert again is not None and again.status == PROPOSAL_APPROVED


async def test_approving_a_change_updates_the_existing_offering(
    db_session, organization_id
) -> None:
    live = await website_product(db_session, organization_id)
    pending = proposal(organization_id, CHANGE_CHANGED, live.id)
    db_session.add(pending)
    await db_session.commit()

    await approve_proposal(db_session, organization_id, pending.id)

    await db_session.refresh(live)
    assert (live.name, live.description, live.source_hash) == (
        "Spacewarp",
        "Moves ServiceNow data.",
        "abc",
    )


async def test_approving_a_removal_archives_instead_of_deleting(
    db_session, organization_id
) -> None:
    live = await website_product(db_session, organization_id)
    pending = proposal(organization_id, CHANGE_REMOVED, live.id)
    db_session.add(pending)
    await db_session.commit()

    await approve_proposal(db_session, organization_id, pending.id)

    await db_session.refresh(live)
    assert live.status == "archived"


async def test_rejecting_changes_nothing_live_and_cannot_be_undone_by_approve(
    db_session, organization_id
) -> None:
    live = await website_product(db_session, organization_id)
    pending = proposal(organization_id, CHANGE_CHANGED, live.id)
    db_session.add(pending)
    await db_session.commit()

    rejected = await reject_proposal(db_session, organization_id, pending.id)
    again = await approve_proposal(db_session, organization_id, pending.id)

    assert rejected is not None and rejected.status == PROPOSAL_REJECTED
    assert again is not None and again.status == PROPOSAL_REJECTED
    await db_session.refresh(live)
    assert live.name == "Old name"


async def test_other_organizations_proposals_are_not_found(db_session, organization_id) -> None:
    import uuid

    pending = proposal(organization_id)
    db_session.add(pending)
    await db_session.commit()

    assert await approve_proposal(db_session, uuid.uuid4(), pending.id) is None
    assert await reject_proposal(db_session, organization_id, uuid.uuid4()) is None


async def test_pressing_check_for_updates_twice_queues_one_sync(
    db_session, organization_id
) -> None:
    first = await start_sync(db_session, organization_id)
    second = await start_sync(db_session, organization_id)
    await db_session.commit()

    assert first.id == second.id
    status = await sync_status(db_session, organization_id)
    assert status["running"] is True and status["job_id"] == first.id


async def test_weekly_check_is_due_only_when_the_last_sync_is_old_enough(
    db_session, organization_id
) -> None:
    assert await sync_due(db_session, organization_id, 7) is True  # never synced

    job = Job(organization_id=organization_id, job_type=JOB_TYPE_SYNC_OFFERINGS, payload={})
    job.status = STATUS_DONE
    job.finished_at = datetime.now(UTC) - timedelta(days=2)
    db_session.add(job)
    await db_session.commit()
    assert await sync_due(db_session, organization_id, 7) is False

    job.finished_at = datetime.now(UTC) - timedelta(days=8)
    await db_session.commit()
    assert await sync_due(db_session, organization_id, 7) is True

    assert await enqueue_sync_if_due(db_session, organization_id, 7) is True
    assert await enqueue_sync_if_due(db_session, organization_id, 7) is False  # one is waiting
    assert await enqueue_sync_if_due(db_session, organization_id, 0) is False  # switched off


async def test_routes_resolve_before_the_product_id_route(db_session, organization_id) -> None:
    pending = proposal(organization_id)
    db_session.add(pending)
    await db_session.commit()

    async def override():
        yield db_session

    app.dependency_overrides[get_db] = override
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            status = await client.get("/api/v1/products/sync/status")
            listed = await client.get("/api/v1/products/proposals")
            decided = await client.post(
                "/api/v1/products/proposals/decide",
                json={"proposal_ids": [str(pending.id)], "decision": "approve"},
            )
            started = await client.post("/api/v1/products/sync")
            archived_listing = await client.get("/api/v1/products?include_archived=true")
    finally:
        app.dependency_overrides.clear()

    assert status.status_code == 200 and status.json()["pending_count"] == 1
    assert [p["name"] for p in listed.json()["items"]] == ["Spacewarp"]
    assert decided.json() == {"decided": 1, "not_found": 0}
    assert started.status_code == 202
    assert [p["name"] for p in archived_listing.json()["items"]] == ["Spacewarp"]


async def test_a_new_proposal_that_looks_like_an_existing_offering_is_flagged(
    db_session, organization_id
) -> None:
    from app.modules.offerings.review import duplicate_hints

    live = await create_product(db_session, organization_id, name="Expona", description=None)
    live.status = "active"
    twin_a = proposal(organization_id, name="Expona AI")
    twin_b = proposal(organization_id, name="Insane SDD")
    twin_c = proposal(organization_id, name="InsaneSDD")
    twin_c.source_url = "https://infobeans.ai/insanesdd"
    other = proposal(organization_id, name="Spacewarp")
    db_session.add_all([twin_a, twin_b, twin_c, other])
    await db_session.commit()

    hints = await duplicate_hints(db_session, organization_id, [twin_a, twin_b, twin_c, other])

    assert hints == {twin_a.id: "Expona"}  # "Insane SDD" vs "InsaneSDD" is left for a person
