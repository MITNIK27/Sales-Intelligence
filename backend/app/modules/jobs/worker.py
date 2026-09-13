import asyncio
import logging

from app.core.logging import configure_logging
from app.db import models as _models  # noqa: F401 - registers all models with SQLAlchemy
from app.db.session import SessionLocal
from app.modules.enrichment.service import JOB_TYPE_SCRAPE_COMPANY, process_scrape_company_job
from app.modules.ingestion.market_discovery import (
    JOB_TYPE_MARKET_DISCOVERY,
    process_market_discovery_job,
)
from app.modules.ingestion.service import JOB_TYPE_INGEST_CSV, process_csv_ingestion_job
from app.modules.jobs.models import Job
from app.modules.jobs.service import (
    claim_next_pending_job,
    mark_job_done,
    mark_job_failed,
    report_job_progress,
    requeue_stale_jobs,
)
from app.modules.qualification.service import (
    JOB_TYPE_ADHOC_QUALIFY,
    JOB_TYPE_BULK_QUALIFY,
    run_adhoc_qualification_job,
    run_bulk_qualification_job,
)
from app.modules.verification.service import (
    JOB_TYPE_VERIFY_CONTACTS,
    process_verify_contacts_job,
)

logger = logging.getLogger(__name__)

# job_type -> handler(session, job) -> result dict. Registered here rather than looked up
# dynamically so it's obvious, at a glance, what job types this worker knows how to run.
_HANDLERS = {
    JOB_TYPE_INGEST_CSV: process_csv_ingestion_job,
    JOB_TYPE_SCRAPE_COMPANY: process_scrape_company_job,
    JOB_TYPE_MARKET_DISCOVERY: process_market_discovery_job,
    JOB_TYPE_VERIFY_CONTACTS: process_verify_contacts_job,
    JOB_TYPE_BULK_QUALIFY: run_bulk_qualification_job,
    JOB_TYPE_ADHOC_QUALIFY: run_adhoc_qualification_job,
}


async def _process_one_job(job: Job) -> None:
    async def progress_callback(done: int, total: int) -> None:
        await report_job_progress(job.id, {"done": done, "total": total})

    logger.info("job started: %s (%s)", job.id, job.job_type)
    async with SessionLocal() as session:
        handler = _HANDLERS.get(job.job_type)
        try:
            if handler is None:
                raise ValueError(f"no handler registered for job_type={job.job_type!r}")
            job_in_session = await session.get_one(Job, job.id)
            result = await handler(session, job_in_session, progress_callback)
            await mark_job_done(session, job_in_session, result)
            logger.info("job done: %s (%s)", job.id, job.job_type)
        except Exception as exc:  # noqa: BLE001 - isolate worker loop from any handler failure
            logger.warning("job failed: %s (%s) — %s", job.id, job.job_type, exc)
            logger.debug("job %s traceback", job.id, exc_info=True)
            await session.rollback()
            job_in_session = await session.get_one(Job, job.id)
            await mark_job_failed(session, job_in_session, str(exc))
        await session.commit()


async def run_worker(poll_interval_seconds: float = 2.0) -> None:
    logger.info("job worker starting, poll_interval=%.1fs", poll_interval_seconds)
    while True:
        async with SessionLocal() as session:
            requeued = await requeue_stale_jobs(session)
            if requeued:
                logger.warning("requeued %d stale job(s)", requeued)
            job = await claim_next_pending_job(session)
            await session.commit()

        if job is None:
            await asyncio.sleep(poll_interval_seconds)
            continue

        await _process_one_job(job)


if __name__ == "__main__":
    configure_logging()
    asyncio.run(run_worker())
