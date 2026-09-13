import uuid
from datetime import UTC, datetime

from app.modules.companies.models import Company
from app.modules.companies.service import (
    get_or_create_company,
    list_companies,
    list_company_ids_by_source_run,
    normalize_domain,
    search_company_index,
)
from app.modules.qualification.models import QualificationResult


def test_normalize_domain_strips_protocol_www_and_path() -> None:
    assert normalize_domain("https://www.Acme.com/about") == "acme.com"
    assert normalize_domain("acme.com") == "acme.com"
    assert normalize_domain(None) is None
    assert normalize_domain("") is None


def test_normalize_domain_strips_malformed_trailing_garbage() -> None:
    # Observed live: Serper returning a link with a stray, path-separator-less closing HTML tag
    # baked in (`</b` has no `/` before the `<`, so the naive path-split alone doesn't catch it).
    assert normalize_domain("https://www.knightfintech.com</b") == "knightfintech.com"
    assert normalize_domain("https://acme.com<") == "acme.com"
    assert normalize_domain("https://acme.com>") == "acme.com"


async def test_get_or_create_company_cleans_url_shaped_name(db_session, organization_id) -> None:
    company, _ = await get_or_create_company(
        db_session, organization_id, name="https://www.Sennder.com/", domain=None
    )
    assert company.name == "sennder.com"


async def test_get_or_create_company_leaves_genuine_name_untouched(
    db_session, organization_id
) -> None:
    company, _ = await get_or_create_company(
        db_session, organization_id, name="  Acme Inc  ", domain="acme.com"
    )
    assert company.name == "Acme Inc"


async def test_get_or_create_company_dedupes_by_domain(db_session, organization_id) -> None:
    company1, created1 = await get_or_create_company(
        db_session, organization_id, name="Acme Inc", domain="https://acme.com"
    )
    company2, created2 = await get_or_create_company(
        db_session, organization_id, name="Acme Incorporated", domain="www.acme.com/"
    )

    assert created1 is True
    assert created2 is False
    assert company1.id == company2.id


async def test_get_or_create_company_dedupes_by_name_when_no_domain(
    db_session, organization_id
) -> None:
    company1, created1 = await get_or_create_company(
        db_session, organization_id, name="Acme Inc", domain=None
    )
    company2, created2 = await get_or_create_company(
        db_session, organization_id, name="  acme inc  ", domain=None
    )

    assert created1 is True
    assert created2 is False
    assert company1.id == company2.id


async def test_different_companies_are_not_merged(db_session, organization_id) -> None:
    company1, _ = await get_or_create_company(
        db_session, organization_id, name="Acme", domain="acme.com"
    )
    company2, _ = await get_or_create_company(
        db_session, organization_id, name="Globex", domain="globex.com"
    )

    assert company1.id != company2.id


async def test_search_company_index_matches_industry_and_description(
    db_session, organization_id
) -> None:
    saas_co = Company(
        organization_id=organization_id, name="Acme", domain="acme.com", industry="SaaS"
    )
    fintech_co = Company(
        organization_id=organization_id,
        name="Globex",
        domain="globex.com",
        description="A leading fintech platform",
    )
    unrelated_co = Company(
        organization_id=organization_id, name="Initech", domain="initech.com", industry="Retail"
    )
    db_session.add_all([saas_co, fintech_co, unrelated_co])
    await db_session.commit()

    results = await search_company_index(
        db_session, organization_id, industry_keywords=["SaaS", "fintech"], limit=10
    )

    assert {c.domain for c in results} == {"acme.com", "globex.com"}


async def test_search_company_index_respects_limit_and_empty_keywords(
    db_session, organization_id
) -> None:
    for i in range(3):
        db_session.add(
            Company(
                organization_id=organization_id,
                name=f"Company {i}",
                domain=f"company{i}.com",
                industry="SaaS",
            )
        )
    await db_session.commit()

    limited = await search_company_index(
        db_session, organization_id, industry_keywords=["SaaS"], limit=2
    )
    assert len(limited) == 2

    empty = await search_company_index(
        db_session, organization_id, industry_keywords=[], limit=10
    )
    assert empty == []


async def test_list_companies_returns_none_verdict_when_never_qualified(
    db_session, organization_id
) -> None:
    db_session.add(Company(organization_id=organization_id, name="Acme", domain="acme.com"))
    await db_session.commit()

    rows, total = await list_companies(db_session, organization_id)
    assert total == 1
    _, _, verdict = rows[0]
    assert verdict is None


async def test_list_companies_returns_latest_verdict_only(db_session, organization_id) -> None:
    # Explicit, distinct timestamps rather than relying on real wall-clock ordering between two
    # back-to-back inserts — created_at is a Python-side default, so two rows added in the same
    # test can otherwise land in the same microsecond and make the "latest" ordering a coin flip.
    company = Company(organization_id=organization_id, name="Acme", domain="acme.com")
    db_session.add(company)
    await db_session.flush()

    older = datetime(2026, 1, 1, tzinfo=UTC)
    newer = datetime(2026, 1, 2, tzinfo=UTC)
    db_session.add(
        QualificationResult(
            organization_id=organization_id,
            company_id=company.id,
            overall_verdict="not_qualified",
            criteria_results=[],
            model_used="fake-model",
            created_at=older,
        )
    )
    db_session.add(
        QualificationResult(
            organization_id=organization_id,
            company_id=company.id,
            overall_verdict="qualified",
            criteria_results=[],
            model_used="fake-model",
            created_at=newer,
        )
    )
    await db_session.commit()

    rows, _ = await list_companies(db_session, organization_id)
    _, _, verdict = rows[0]
    assert verdict == "qualified"  # the newer row, not the first one inserted


async def test_list_company_ids_by_source_run_scopes_by_run_and_org(
    db_session, organization_id
) -> None:
    run_id = uuid.uuid4()
    other_run_id = uuid.uuid4()
    matching = Company(
        organization_id=organization_id, name="Acme", domain="acme.com",
        source_ingestion_run_id=run_id,
    )
    other_run = Company(
        organization_id=organization_id, name="Globex", domain="globex.com",
        source_ingestion_run_id=other_run_id,
    )
    no_run = Company(organization_id=organization_id, name="Initech", domain="initech.com")
    db_session.add_all([matching, other_run, no_run])
    await db_session.commit()

    ids = await list_company_ids_by_source_run(db_session, organization_id, run_id)
    assert ids == [matching.id]
