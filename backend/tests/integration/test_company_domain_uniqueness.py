import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.companies.models import Company


async def test_duplicate_domain_is_rejected_at_db_level(db_session, organization_id) -> None:
    """Backstop for the application-level dedup in companies/service.py: even if two inserts
    for the same (org, domain) somehow both reach the database, the second must fail rather
    than silently create a duplicate company."""
    db_session.add(Company(organization_id=organization_id, name="Acme", domain="acme.com"))
    await db_session.flush()

    db_session.add(
        Company(organization_id=organization_id, name="Acme Duplicate", domain="acme.com")
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_multiple_companies_with_null_domain_are_allowed(db_session, organization_id) -> None:
    """The uniqueness constraint is partial (WHERE domain IS NOT NULL) — companies with no
    known domain yet must not collide with each other."""
    db_session.add(Company(organization_id=organization_id, name="No Domain A", domain=None))
    db_session.add(Company(organization_id=organization_id, name="No Domain B", domain=None))
    await db_session.flush()  # should not raise
