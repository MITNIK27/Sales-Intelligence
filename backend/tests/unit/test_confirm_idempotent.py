"""Confirming a Market Discovery run twice must not start the pipeline twice."""

from sqlalchemy import select

from app.api.v1.market_discovery import confirm_market_discovery_endpoint
from app.modules.ai_recommendation.mock import MockMarketDescriptionParser
from app.modules.ingestion.market_discovery import start_market_discovery_parse
from app.modules.ingestion.models import STATUS_FAILED, IngestionRun
from app.modules.ingestion.schemas import MarketDiscoveryConfirmRequest
from app.modules.jobs.models import Job
from tests.unit.test_auto_pipeline import _CRITERIA


async def _parsed_run(db_session, organization_id) -> IngestionRun:
    run = await start_market_discovery_parse(
        db_session, organization_id, "SaaS companies", MockMarketDescriptionParser(_CRITERIA)
    )
    await db_session.commit()
    return run


async def _jobs(db_session) -> list[Job]:
    return list((await db_session.execute(select(Job))).scalars())


async def test_second_confirm_returns_the_same_job_and_enqueues_nothing(
    db_session, organization_id
) -> None:
    run = await _parsed_run(db_session, organization_id)
    body = MarketDiscoveryConfirmRequest(industry_keywords=["SaaS"])

    first = await confirm_market_discovery_endpoint(run.id, body, db_session)
    second = await confirm_market_discovery_endpoint(run.id, body, db_session)

    assert second.job_id == first.job_id
    assert len(await _jobs(db_session)) == 1


async def test_a_failed_run_can_be_retried_with_a_new_job(db_session, organization_id) -> None:
    run = await _parsed_run(db_session, organization_id)
    body = MarketDiscoveryConfirmRequest(industry_keywords=["SaaS"])
    first = await confirm_market_discovery_endpoint(run.id, body, db_session)

    refreshed = await db_session.get(IngestionRun, run.id)
    assert refreshed is not None
    refreshed.status = STATUS_FAILED
    await db_session.commit()

    retry = await confirm_market_discovery_endpoint(run.id, body, db_session)

    assert retry.job_id != first.job_id
    assert len(await _jobs(db_session)) == 2


async def test_confirm_stores_per_search_requirements_on_the_job(
    db_session, organization_id
) -> None:
    from app.modules.ingestion.schemas import MarketFitCriterionIn

    run = await _parsed_run(db_session, organization_id)
    body = MarketDiscoveryConfirmRequest(
        industry_keywords=["SaaS"],
        market_fit_criteria=[MarketFitCriterionIn(name="Operates in logistics", description="x")],
    )
    started = await confirm_market_discovery_endpoint(run.id, body, db_session)

    job = await db_session.get(Job, started.job_id)
    assert job is not None
    assert job.payload["market_fit_criteria"] == [
        {"name": "Operates in logistics", "description": "x"}
    ]
