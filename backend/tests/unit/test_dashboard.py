"""The dashboard is read-only, scoped (one search vs all, de-duplicated) and honest."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.api.v1.dashboard import get_overview, get_runs
from app.db.base import Base
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.dashboard.schemas import Kpis
from app.modules.dashboard.service import build_headline, build_overview, list_run_stats
from app.modules.draft.models import Draft
from app.modules.ingestion.models import SOURCE_TYPE_MARKET_DISCOVERY, IngestionRun
from app.modules.outreach.models import OutreachActivity
from app.modules.products.models import Product
from app.modules.qualification.models import QualificationResult
from app.modules.role_relevance.models import RoleRelevanceResult


def _entry(name: str, status: str, hard: bool = True, scope: str = "run") -> dict:
    return {
        "criterion_name": name,
        "is_disqualifying": hard,
        "scope": scope,
        "status": status,
        "verdict": {"PASS": "met", "FAIL": "not_met", "UNKNOWN": "could_not_determine"}[status],
        "reasoning": f"{name} {status}",
    }


async def _run(
    session, org, *, raw="Logistics in Germany", summary=None, status="done", age_days=0
):
    run = IngestionRun(
        organization_id=org,
        source_type=SOURCE_TYPE_MARKET_DISCOVERY,
        status=status,
        raw_input=raw,
        parsed_fields={
            "industry_keywords": {"value": ["logistics"]},
            "location": {"value": "Germany"},
            "employee_size_range": {"value": "1,000-10,000"},
        },
        summary=summary or {},
    )
    session.add(run)
    await session.flush()
    if age_days:
        run.created_at = datetime.now(UTC) - timedelta(days=age_days)
    return run


async def _company(session, org, run, name, verdict, score=None, entries=None):
    company = Company(
        organization_id=org,
        name=name,
        domain=f"{name.lower()}.com",
        source_ingestion_run_id=run.id if run else None,
    )
    session.add(company)
    await session.flush()
    if verdict:
        session.add(
            QualificationResult(
                organization_id=org,
                company_id=company.id,
                overall_verdict=verdict,
                model_used="m",
                criteria_results=entries or [],
                priority_score=score,
            )
        )
    await session.flush()
    return company


async def _contact(session, org, company, name, *, primary=False, confidence=None):
    contact = Contact(
        organization_id=org, company_id=company.id, full_name=name, confidence=confidence
    )
    session.add(contact)
    await session.flush()
    if primary:
        session.add(
            RoleRelevanceResult(
                organization_id=org,
                company_id=company.id,
                contact_id=contact.id,
                priority="primary",
                is_primary_target=True,
                reasoning="r",
                model_used="m",
            )
        )
    await session.flush()
    return contact


async def _draft(session, org, company, contact, status="draft"):
    product = (await session.execute(select(Product))).scalars().first()
    if product is None:
        product = Product(organization_id=org, name="Widget", description="w")
        session.add(product)
        await session.flush()
    draft = Draft(
        organization_id=org,
        company_id=company.id,
        contact_id=contact.id,
        product_id=product.id,
        draft_type="first_touch",
        channel="email",
        subject="s",
        body="b",
        status=status,
        model_used="m",
    )
    session.add(draft)
    await session.flush()
    return draft


async def _seed_one_search(session, org):
    run = await _run(
        session,
        org,
        summary={
            "company_ids": [],
            "context_dev": {
                "credits_used": 22,
                "credit_ceiling": 150,
                "budget_exhausted": False,
                "skipped_sufficient": 3,
            },
            "enrichment": {"branch_errors": {"signals": 2}},
        },
    )
    dpd = await _company(
        session, org, run, "DPD", "qualified", 80.0,
        [_entry("Industry", "PASS"), _entry("Location", "PASS")],
    )
    gls = await _company(
        session, org, run, "GLS", "could_not_determine", 67.0,
        [_entry("Industry", "PASS"), _entry("Location", "UNKNOWN")],
    )
    hermes = await _company(
        session, org, run, "Hermes", "not_qualified", 0.0,
        [_entry("Industry", "FAIL"), _entry("Location", "PASS")],
    )
    await _company(session, org, run, "Unchecked", None)
    marc = await _contact(session, org, dpd, "Marc", primary=True, confidence=0.95)
    await _contact(session, org, dpd, "Elaine", confidence=0.5)
    await _contact(session, org, gls, "Kevin", primary=True, confidence=0.9)
    await _contact(session, org, hermes, "Jackie")
    await _draft(session, org, dpd, marc, "draft")
    await session.commit()
    return run


async def test_empty_system_gives_a_friendly_headline_and_zero_numbers(
    db_session, organization_id
) -> None:
    overview = await build_overview(db_session, organization_id)
    assert overview is not None
    assert overview.scope == "all"
    assert overview.headline.startswith("No searches yet")
    assert overview.kpis.searches == 0 and overview.kpis.companies == 0
    assert [s.count for s in overview.funnel] == [0, 0, 0, 0, 0]
    assert overview.requirements == [] and overview.top_companies == []
    assert overview.setup.products == 0


async def test_one_search_numbers_funnel_requirements_and_headline(
    db_session, organization_id
) -> None:
    run = await _seed_one_search(db_session, organization_id)

    overview = await build_overview(db_session, organization_id, run.id)
    assert overview is not None and overview.scope == "search"

    k = overview.kpis
    assert (k.companies, k.fit, k.needs_closer_look, k.rejected) == (4, 1, 1, 1)
    assert k.contacts == 4
    assert k.likely_decision_makers == 2  # Marc 0.95, Kevin 0.9 (>= 0.8); Elaine 0.5 is not
    assert (k.drafts_to_review, k.drafts_sent, k.credits_used) == (1, 0, 22)

    counts = {s.key: s.count for s in overview.funnel}
    assert counts == {
        "found": 4,
        "checked": 3,
        "worth_pursuing": 2,
        "have_contact": 2,
        "draft_written": 1,
    }
    assert overview.funnel[1].percent_of_previous == 75

    by_name = {r.name: r for r in overview.requirements}
    assert (by_name["Industry"].meets, by_name["Industry"].doesnt_meet) == (2, 1)
    assert by_name["Location"].couldnt_verify == 1
    # only DPD has a draft, and DPD meets both requirements
    assert by_name["Industry"].drafts_for_meeting == 1
    assert by_name["Industry"].scope == "run" and by_name["Industry"].hard

    assert [t.name for t in overview.top_companies] == ["DPD", "GLS"]  # rejected excluded
    assert overview.top_companies[1].reason.startswith("Needs a closer look")

    attention = {a.key: a.count for a in overview.attention}
    assert attention["ready_to_contact"] == 1  # GLS: primary contact, nothing drafted yet
    assert attention["drafts_to_review"] == 1
    assert attention["needs_closer_look"] == 1

    assert overview.health.credits_used == 22 and overview.health.credit_ceiling == 150
    assert overview.health.companies_needing_no_paid_lookup == 3
    assert overview.health.provider_errors == {"signals": 2}
    assert overview.run is not None and overview.run.title == "Logistics in Germany"
    assert overview.run.summary == "logistics · Germany · 1,000-10,000 employees"

    assert "found 4 companies" in overview.headline
    assert "1 is ready for you to contact" in overview.headline
    assert "1 was rejected as a poor fit" in overview.headline
    assert "1 draft written" in overview.headline


async def test_all_searches_counts_a_reused_company_once(db_session, organization_id) -> None:
    first = await _run(db_session, organization_id, raw="First search")
    shared = await _company(db_session, organization_id, first, "Shared", "qualified", 70.0)
    second = await _run(
        db_session,
        organization_id,
        raw="Second search",
        summary={"company_ids": [str(shared.id)]},  # reused from the index, not created by it
    )
    await _company(db_session, organization_id, second, "OnlyInSecond", "qualified", 60.0)
    await db_session.commit()

    everything = await build_overview(db_session, organization_id)
    assert everything is not None
    assert everything.kpis.searches == 2
    assert everything.kpis.companies == 2  # Shared is in both searches but counts once

    second_only = await build_overview(db_session, organization_id, second.id)
    assert second_only is not None and second_only.kpis.companies == 2  # includes the reused one
    first_only = await build_overview(db_session, organization_id, first.id)
    assert first_only is not None and first_only.kpis.companies == 1


async def test_period_filter_excludes_old_searches(db_session, organization_id) -> None:
    old = await _run(db_session, organization_id, raw="Old", age_days=45)
    await _company(db_session, organization_id, old, "OldCo", "qualified")
    recent = await _run(db_session, organization_id, raw="Recent")
    await _company(db_session, organization_id, recent, "NewCo", "qualified")
    await db_session.commit()

    month = await build_overview(db_session, organization_id, None, "30d")
    allt = await build_overview(db_session, organization_id, None, "all")
    assert month is not None and month.kpis.searches == 1 and month.kpis.companies == 1
    assert allt is not None and allt.kpis.searches == 2 and allt.kpis.companies == 2
    # the scope selector still lists every search, whatever the period
    assert len(month.searches) == 2


async def test_unknown_search_is_none_and_the_endpoint_404s(db_session, organization_id) -> None:
    assert await build_overview(db_session, organization_id, uuid.uuid4()) is None
    try:
        await get_overview(uuid.uuid4(), "all", db_session)
    except Exception as exc:  # HTTPException
        assert getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError("expected a 404")


async def test_run_list_is_paginated_with_per_search_stats(db_session, organization_id) -> None:
    await _seed_one_search(db_session, organization_id)
    for i in range(3):
        await _run(db_session, organization_id, raw=f"Extra {i}")
    await db_session.commit()

    page = await list_run_stats(db_session, organization_id, limit=2, offset=0)
    assert page.total == 4 and len(page.items) == 2
    rest = await list_run_stats(db_session, organization_id, limit=2, offset=2)
    assert len(rest.items) == 2
    seeded = next(
        r for p in (page, rest) for r in p.items if r.title == "Logistics in Germany"
    )
    assert (seeded.companies, seeded.fit, seeded.drafts, seeded.credits_used) == (4, 1, 1, 22)
    assert seeded.top_score == 80.0

    via_endpoint = await get_runs(1, 0, "all", db_session)
    assert via_endpoint.total == 4


async def test_awaiting_confirmation_runs_are_not_searches(db_session, organization_id) -> None:
    await _run(db_session, organization_id, raw="Only parsed", status="awaiting_confirmation")
    await db_session.commit()
    overview = await build_overview(db_session, organization_id)
    assert overview is not None and overview.kpis.searches == 0


async def test_activity_lists_searches_drafts_and_outreach_newest_first(
    db_session, organization_id
) -> None:
    run = await _seed_one_search(db_session, organization_id)
    marc = (
        (await db_session.execute(select(Contact).where(Contact.full_name == "Marc")))
        .scalars()
        .one()
    )
    db_session.add(
        OutreachActivity(
            organization_id=organization_id,
            contact_id=marc.id,
            channel="email",
            activity_type="sent",
        )
    )
    await db_session.commit()

    overview = await build_overview(db_session, organization_id, run.id)
    assert overview is not None
    kinds = {e.kind for e in overview.activity}
    assert {"search", "draft", "outreach"} <= kinds
    assert any(e.text == "Draft written for Marc at DPD" for e in overview.activity)
    assert any(e.text == "Message sent to Marc at DPD" for e in overview.activity)
    assert [e.at for e in overview.activity] == sorted(
        (e.at for e in overview.activity), reverse=True
    )


async def test_failed_and_running_searches_have_honest_headlines(
    db_session, organization_id
) -> None:
    failed = await _run(db_session, organization_id, status="failed")
    failed.error = "Gemini extraction failed"
    running = await _run(db_session, organization_id, status="running", raw="Running one")
    await db_session.commit()

    bad = await build_overview(db_session, organization_id, failed.id)
    assert bad is not None
    assert bad.headline == "This search did not finish: Gemini extraction failed"
    live = await build_overview(db_session, organization_id, running.id)
    assert live is not None and live.headline.startswith("This search is still running")
    everything = await build_overview(db_session, organization_id)
    assert everything is not None
    searches_item = next(a for a in everything.attention if a.key == "searches")
    assert searches_item.count == 2


def test_headline_pluralisation() -> None:
    kpis = Kpis(
        searches=1, companies=1, fit=1, needs_closer_look=0, rejected=0, contacts=0,
        likely_decision_makers=0, drafts_to_review=0, drafts_sent=0, credits_used=0,
    )
    text = build_headline("search", 1, kpis, 1, "done", None)
    assert text == "This search found 1 company — 1 is ready for you to contact."


async def test_loading_the_dashboard_never_writes(db_session, organization_id) -> None:
    run = await _seed_one_search(db_session, organization_id)

    async def counts() -> dict[str, int]:
        out = {}
        for table in Base.metadata.sorted_tables:
            out[table.name] = (
                await db_session.execute(select(func.count()).select_from(table))
            ).scalar_one()
        return out

    before = await counts()
    await build_overview(db_session, organization_id)
    await build_overview(db_session, organization_id, run.id)
    await build_overview(db_session, organization_id, None, "7d")
    await list_run_stats(db_session, organization_id)
    await get_overview(None, "all", db_session)
    await get_runs(10, 0, "all", db_session)
    assert not db_session.dirty and not db_session.new and not db_session.deleted
    assert await counts() == before
