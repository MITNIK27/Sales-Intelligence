from datetime import UTC, datetime, timedelta

from app.modules.jobs.models import STATUS_PENDING, STATUS_RUNNING
from app.modules.jobs.service import enqueue_job, requeue_stale_jobs


async def test_requeue_stale_jobs_resets_long_running_jobs(db_session, organization_id) -> None:
    job = await enqueue_job(db_session, organization_id, "ingest_csv", {"rows": []})
    job.status = STATUS_RUNNING
    job.started_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.flush()

    requeued_count = await requeue_stale_jobs(db_session)

    assert requeued_count == 1
    assert job.status == STATUS_PENDING
    assert job.started_at is None
    assert job.error is not None and "requeued" in job.error


async def test_requeue_stale_jobs_leaves_recent_running_jobs_alone(
    db_session, organization_id
) -> None:
    job = await enqueue_job(db_session, organization_id, "ingest_csv", {"rows": []})
    job.status = STATUS_RUNNING
    job.started_at = datetime.now(UTC)
    await db_session.flush()

    requeued_count = await requeue_stale_jobs(db_session)

    assert requeued_count == 0
    assert job.status == STATUS_RUNNING
