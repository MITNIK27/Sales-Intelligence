import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.modules.jobs.models import STATUS_DONE, STATUS_FAILED, STATUS_PENDING, STATUS_RUNNING, Job

# A `running` job whose worker died (crash, kill, power loss) would otherwise sit stuck forever
# with nothing to notice or retry it. This is a coarse threshold, not a true heartbeat — a
# legitimately slow job running longer than this gets wrongly requeued. Acceptable for now given
# expected job durations; revisit if Phase 2 jobs routinely run this long.
STALE_JOB_THRESHOLD = timedelta(minutes=30)


async def enqueue_job(
    session: AsyncSession, organization_id: uuid.UUID, job_type: str, payload: dict[str, Any]
) -> Job:
    job = Job(organization_id=organization_id, job_type=job_type, payload=payload)
    session.add(job)
    await session.flush()
    return job


async def claim_next_pending_job(session: AsyncSession) -> Job | None:
    """Locks and claims the oldest pending job, if any. Caller is responsible for
    committing/closing the session to release the row lock."""
    stmt = (
        select(Job)
        .where(Job.status == STATUS_PENDING)
        .order_by(Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    result = await session.execute(stmt)
    job = result.scalar_one_or_none()
    if job is None:
        return None
    job.status = STATUS_RUNNING
    job.started_at = datetime.now(UTC)
    await session.flush()
    return job


async def mark_job_done(session: AsyncSession, job: Job, result: dict[str, Any]) -> None:
    job.status = STATUS_DONE
    job.result = result
    job.finished_at = datetime.now(UTC)
    await session.flush()


async def mark_job_failed(session: AsyncSession, job: Job, error: str) -> None:
    job.status = STATUS_FAILED
    job.error = error
    job.finished_at = datetime.now(UTC)
    await session.flush()


async def get_job(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    return await session.get(Job, job_id)


async def report_job_progress(job_id: uuid.UUID, progress: dict[str, Any]) -> None:
    """Commits immediately in its own session, independent of the caller's still-open work
    transaction — so GET /jobs/{id} can observe progress while a job is still running, rather
    than only after the whole job's transaction eventually commits."""
    async with SessionLocal() as session:
        await session.execute(update(Job).where(Job.id == job_id).values(progress=progress))
        await session.commit()


async def requeue_stale_jobs(session: AsyncSession) -> int:
    """Recovers jobs stuck `running` because the worker that owned them died mid-job."""
    threshold = datetime.now(UTC) - STALE_JOB_THRESHOLD
    stmt = select(Job).where(Job.status == STATUS_RUNNING, Job.started_at < threshold)
    stale_jobs = (await session.execute(stmt)).scalars().all()
    for job in stale_jobs:
        job.status = STATUS_PENDING
        job.started_at = None
        note = "[requeued: exceeded stale-running threshold, worker may have died]"
        job.error = f"{job.error} {note}" if job.error else note
    await session.flush()
    return len(stale_jobs)
