import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.service import get_or_create_company
from app.modules.contacts.service import get_or_create_contact, upsert_contact_channel
from app.modules.ingestion.csv_parser import ParsedRow, parse_csv
from app.modules.ingestion.models import SOURCE_TYPE_CSV, STATUS_PENDING, IngestionRun
from app.modules.jobs.models import Job
from app.modules.jobs.service import enqueue_job

JOB_TYPE_INGEST_CSV = "ingest_csv"

ProgressCallback = Callable[[int, int], Awaitable[None]]


async def start_csv_ingestion(
    session: AsyncSession, organization_id: uuid.UUID, filename: str, raw_text: str
) -> tuple[IngestionRun, Job]:
    parsed = parse_csv(raw_text)

    run = IngestionRun(
        organization_id=organization_id,
        source_type=SOURCE_TYPE_CSV,
        status=STATUS_PENDING,
    )
    session.add(run)
    await session.flush()

    payload = {
        "filename": filename,
        "ingestion_run_id": str(run.id),
        "rows": [
            {"row_number": r.row_number, "fields": r.fields, "error": r.error} for r in parsed.rows
        ],
    }
    job = await enqueue_job(session, organization_id, JOB_TYPE_INGEST_CSV, payload)
    return run, job


async def process_csv_ingestion_job(
    session: AsyncSession, job: Job, progress_callback: ProgressCallback | None = None
) -> dict[str, Any]:
    payload = job.payload or {}
    ingestion_run_id = uuid.UUID(payload["ingestion_run_id"])
    run = await session.get(IngestionRun, ingestion_run_id)
    if run is None:
        raise ValueError(f"ingestion run {ingestion_run_id} not found")

    companies_created = 0
    companies_updated = 0
    contacts_created = 0
    rows_skipped = 0
    errors: list[dict[str, Any]] = []

    rows = payload.get("rows", [])
    total_rows = len(rows)

    for i, raw_row in enumerate(rows, start=1):
        row = ParsedRow(
            row_number=raw_row["row_number"], fields=raw_row["fields"], error=raw_row.get("error")
        )
        try:
            if row.error:
                rows_skipped += 1
                errors.append({"row_number": row.row_number, "error": row.error})
                continue

            try:
                # A savepoint per row: if this row's writes fail (e.g. a constraint
                # violation), only this row rolls back — earlier rows already processed in
                # this job stay intact.
                async with session.begin_nested():
                    company, created = await get_or_create_company(
                        session,
                        job.organization_id,
                        name=row.fields.get("company_name") or None,
                        domain=row.fields.get("domain") or None,
                        industry=row.fields.get("industry") or None,
                        employee_count_range=row.fields.get("employee_count_range") or None,
                        source_ingestion_run_id=run.id,
                    )

                    if row.fields.get("contact_full_name") or row.fields.get("contact_email"):
                        contact, contact_created = await get_or_create_contact(
                            session,
                            job.organization_id,
                            company_id=company.id,
                            full_name=row.fields.get("contact_full_name") or None,
                            role_title=row.fields.get("contact_role") or None,
                            email=row.fields.get("contact_email") or None,
                        )

                        if row.fields.get("contact_email"):
                            await upsert_contact_channel(
                                session,
                                contact.id,
                                "email",
                                row.fields["contact_email"],
                                source="csv",
                            )
                        if row.fields.get("contact_phone"):
                            await upsert_contact_channel(
                                session,
                                contact.id,
                                "phone",
                                row.fields["contact_phone"],
                                source="csv",
                            )
                    else:
                        contact_created = False
            except Exception as exc:  # noqa: BLE001 - row-level isolation, don't fail the run
                rows_skipped += 1
                errors.append({"row_number": row.row_number, "error": str(exc)})
                continue

            if created:
                companies_created += 1
            else:
                companies_updated += 1
            if contact_created:
                contacts_created += 1
        finally:
            if progress_callback:
                await progress_callback(i, total_rows)

    summary = {
        "companies_created": companies_created,
        "companies_updated": companies_updated,
        "contacts_created": contacts_created,
        "rows_skipped": rows_skipped,
        "errors": errors,
    }
    run.status = "done"
    run.summary = summary
    await session.flush()
    return summary
