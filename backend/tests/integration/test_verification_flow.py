import uuid

from app.modules.companies.service import get_or_create_company
from app.modules.contacts.models import VERIFICATION_UNVERIFIED, VERIFICATION_VALID
from app.modules.contacts.service import get_or_create_contact, upsert_contact_channel
from app.modules.jobs.worker import _HANDLERS
from app.modules.verification.providers.base import VerificationResult
from app.modules.verification.providers.mock import (
    MockEmailVerificationProvider,
    MockPhoneVerificationProvider,
)
from app.modules.verification.service import (
    JOB_TYPE_VERIFY_CONTACTS,
    _run_bulk_verify,
    start_bulk_verify,
    verify_channel,
)


def test_verify_contacts_job_type_is_registered_with_worker() -> None:
    assert JOB_TYPE_VERIFY_CONTACTS in _HANDLERS


async def _make_contact_with_channel(db_session, organization_id, channel_type, value):
    company, _ = await get_or_create_company(
        db_session, organization_id, name="Acme", domain="acme.com"
    )
    contact, _ = await get_or_create_contact(
        db_session, organization_id, company_id=company.id, full_name="Jane Doe",
        role_title="CEO", email=None,
    )
    channel = await upsert_contact_channel(
        db_session, contact.id, channel_type, value, source="test"
    )
    await db_session.commit()
    return contact, channel


async def test_verify_channel_updates_status_from_email_provider(
    db_session, organization_id
) -> None:
    _, channel = await _make_contact_with_channel(
        db_session, organization_id, "email", "jane@acme.com"
    )
    assert channel.verification_status == VERIFICATION_UNVERIFIED

    updated = await verify_channel(
        db_session,
        organization_id,
        channel.id,
        email_provider=MockEmailVerificationProvider(VerificationResult(status="valid")),
        phone_provider=MockPhoneVerificationProvider(),
    )
    await db_session.commit()

    assert updated is not None
    assert updated.verification_status == VERIFICATION_VALID


async def test_verify_channel_returns_none_for_unknown_channel(db_session, organization_id) -> None:
    result = await verify_channel(
        db_session,
        organization_id,
        uuid.uuid4(),
        email_provider=MockEmailVerificationProvider(),
        phone_provider=MockPhoneVerificationProvider(),
    )
    assert result is None


async def test_start_bulk_verify_enqueues_job(db_session, organization_id) -> None:
    job = await start_bulk_verify(db_session, organization_id)
    await db_session.commit()

    assert job.job_type == JOB_TYPE_VERIFY_CONTACTS
    assert job.organization_id == organization_id


async def test_bulk_verify_only_touches_unverified_channels(db_session, organization_id) -> None:
    _, unverified_channel = await _make_contact_with_channel(
        db_session, organization_id, "email", "jane@acme.com"
    )
    _, already_verified_channel = await _make_contact_with_channel(
        db_session, organization_id, "email", "john@acme.com"
    )
    already_verified_channel.verification_status = VERIFICATION_VALID
    await db_session.commit()

    job = await start_bulk_verify(db_session, organization_id)
    await db_session.commit()

    result = await _run_bulk_verify(
        db_session,
        job,
        email_provider=MockEmailVerificationProvider(VerificationResult(status="valid")),
        phone_provider=MockPhoneVerificationProvider(),
    )
    await db_session.commit()

    assert result["channels_verified"] == 1

    await db_session.refresh(unverified_channel)
    assert unverified_channel.verification_status == VERIFICATION_VALID
