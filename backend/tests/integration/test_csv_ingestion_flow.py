from app.modules.ingestion.service import process_csv_ingestion_job, start_csv_ingestion
from app.modules.jobs.service import get_job


async def test_csv_upload_creates_companies_and_contacts_end_to_end(
    db_session, organization_id
) -> None:
    raw_csv = (
        "company_name,domain,contact_full_name,contact_role,contact_email,contact_phone\n"
        "Acme Inc,acme.com,Jane Doe,CEO,jane@acme.com,555-1234\n"
        "Acme Inc,acme.com,John Roe,CTO,john@acme.com,\n"
        ",,\n"  # malformed row: no company name or domain
    )

    run, job = await start_csv_ingestion(db_session, organization_id, "prospects.csv", raw_csv)
    await db_session.commit()

    result = await process_csv_ingestion_job(db_session, job)
    await db_session.commit()

    assert result["companies_created"] == 1
    assert result["contacts_created"] == 2
    assert result["rows_skipped"] == 1
    assert len(result["errors"]) == 1

    stored_job = await get_job(db_session, job.id)
    assert stored_job is not None


async def test_reuploading_same_company_updates_instead_of_duplicating(
    db_session, organization_id
) -> None:
    raw_csv = "company_name,domain\nAcme Inc,acme.com\n"

    _, job1 = await start_csv_ingestion(db_session, organization_id, "a.csv", raw_csv)
    await db_session.commit()
    result1 = await process_csv_ingestion_job(db_session, job1)
    await db_session.commit()

    _, job2 = await start_csv_ingestion(db_session, organization_id, "b.csv", raw_csv)
    await db_session.commit()
    result2 = await process_csv_ingestion_job(db_session, job2)
    await db_session.commit()

    assert result1["companies_created"] == 1
    assert result2["companies_created"] == 0
    assert result2["companies_updated"] == 1
