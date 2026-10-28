"""The rep-facing worklist of a Market Discovery run, plus the run summary and auto-pipeline
wiring that feed it."""

import asyncio
import dataclasses
import importlib.util
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.modules.ai_recommendation.mock import MockMarketDescriptionParser
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.discovery_agent.schemas import DiscoveredCompany
from app.modules.discovery_agent.testing import StubCompanyDiscoveryAgent
from app.modules.draft.mock import MockDraftGenerator
from app.modules.enrichment.providers.base import (
    FetchedPage,
    ScrapedCompanyData,
    ScrapedContact,
)
from app.modules.enrichment.providers.context_dev import ContextDevProvider
from app.modules.enrichment.providers.factory import ScraperWithContextDevFallback
from app.modules.enrichment.providers.mock import (
    MockCompanyDataProvider,
    MockContactDataProvider,
    MockContactSearchProvider,
    MockDomainDiscoveryProvider,
    MockSignalDataProvider,
)
from app.modules.enrichment.providers.website_scraper import WebsiteScraperProvider
from app.modules.ingestion.market_discovery import (
    _tally_enrichment,
    confirm_market_discovery,
    start_market_discovery_parse,
)
from app.modules.ingestion.run_results import build_run_worklist
from app.modules.jobs.models import Job
from app.modules.orchestrator.service import JOB_TYPE_AUTO_PIPELINE, _run_auto_pipeline
from app.modules.products.service import create_product
from app.modules.qualification.qualification_generator import (
    CriterionVerdict,
    QualificationJudgment,
)
from app.modules.qualification.service import create_criterion
from app.modules.role_relevance.mock import MockRoleRelevanceGenerator
from app.modules.role_relevance.service import create_category
from tests.unit.test_auto_pipeline import _CRITERIA  # shared parsed-criteria fixture value


class _AllMetQualificationGenerator:
    @property
    def model_name(self) -> str:
        return "fake-model"

    async def generate(self, company, signals, criteria) -> QualificationJudgment:  # type: ignore[no-untyped-def]
        return QualificationJudgment(
            criteria_results=[
                CriterionVerdict(criterion_id=str(c.id), verdict="met", reasoning="has the budget")
                for c in criteria
            ]
        )


async def _run_pipeline(
    db_session,
    organization_id,
    *,
    contact_search=None,
    needs_review=False,
    site_contacts=None,
    extra_candidates=(),
    signal_provider=None,
    progress_callback=None,
    market_fit_criteria=None,
    generator=None,
    company_provider=None,
):
    await create_criterion(
        db_session, organization_id, name="IT spend", description=None,
        is_disqualifying=True, is_active=True,
    )
    await create_category(
        db_session, organization_id, name="Vendor / IT", description=None,
        is_primary_target=True, is_active=True,
    )
    product = await create_product(db_session, organization_id, name="Widget", description=None)
    await db_session.commit()

    run = await start_market_discovery_parse(
        db_session, organization_id, "SaaS companies", MockMarketDescriptionParser(_CRITERIA)
    )
    await db_session.commit()
    confirmed = await confirm_market_discovery(
        db_session, organization_id, run.id,
        industry_keywords=["SaaS"], location=None, employee_size_range=None,
    )
    await db_session.commit()
    assert confirmed is not None

    job = Job(
        organization_id=organization_id,
        job_type=JOB_TYPE_AUTO_PIPELINE,
        payload={
            "ingestion_run_id": str(run.id),
            "product_ids": [str(product.id)],
            "market_fit_criteria": market_fit_criteria or [],
        },
    )
    result = await _run_auto_pipeline(
        db_session,
        job,
        StubCompanyDiscoveryAgent(
            [
                DiscoveredCompany(
                    name="Acme Inc", domain="acme.com", source_snippet="Acme",
                    needs_review=needs_review,
                    needs_review_reason="suspicious name" if needs_review else None,
                ),
                *extra_candidates,
            ]
        ),
        MockDomainDiscoveryProvider(),
        company_provider
        or MockCompanyDataProvider(
            ScrapedCompanyData(
                description="d", industry="Logistics", source_label="contextdev:scrape"
            )
        ),
        MockContactDataProvider(site_contacts or []),
        signal_provider or MockSignalDataProvider([]),
        generator or _AllMetQualificationGenerator(),
        MockRoleRelevanceGenerator(),
        MockDraftGenerator(),
        progress_callback=progress_callback,
        contact_search_provider=contact_search,
    )
    await db_session.commit()
    return run, result


async def test_contact_search_reaches_the_auto_pipeline_and_feeds_the_worklist(
    db_session, organization_id
) -> None:
    # The website yields no contacts; only the search-based provider finds one. Before this was
    # wired into the auto-pipeline, such a company ended with nobody to draft to.
    search = MockContactSearchProvider(
        [ScrapedContact(full_name="Jane Doe", role_title="Procurement Manager", email=None)]
    )
    run, result = await _run_pipeline(db_session, organization_id, contact_search=search)

    contacts = (await db_session.execute(select(Contact))).scalars().all()
    assert [c.full_name for c in contacts] == ["Jane Doe"]

    # Search-found contacts are flagged needs_review ("not confirmed"), so no draft is written for
    # them automatically - but the company is still READY: the rep sees the candidate and confirms
    # the right person with one click, which is what then triggers a draft.
    worklist = await build_run_worklist(db_session, organization_id, run.id)
    assert worklist.not_shown == []
    (row,) = worklist.ready
    (candidate,) = row.candidates
    assert candidate.full_name == "Jane Doe"
    assert candidate.needs_review is True
    assert candidate.draft is None
    assert candidate.linkedin_url is None  # nothing found -> shown as "not found", not guessed
    assert candidate.email is None


async def test_run_summary_records_data_source_and_enrichment_outcome(
    db_session, organization_id
) -> None:
    run, result = await _run_pipeline(db_session, organization_id)
    await db_session.refresh(run)

    summary = run.summary
    assert summary["company_data_source"] == get_settings().company_data_source
    assert summary["enrichment"]["enriched"] == 1
    assert summary["enrichment"]["failed"] == 0
    assert summary["enrichment"]["industry_filled"] == 1
    assert summary["enrichment"]["by_source"] == {"contextdev:scrape": 1}


def test_tally_enrichment_counts_failures_and_sources() -> None:
    tally = {"enriched": 0, "failed": 0, "industry_filled": 0, "by_source": {}}
    _tally_enrichment(tally, {"status": "failed", "reason": "no_domain"})
    _tally_enrichment(
        tally,
        {
            "status": "enriched",
            "industry_filled": False,
            "firmographics_source": "scraper:companysite",
        },
    )
    assert tally == {
        "enriched": 1, "failed": 1, "industry_filled": 0,
        "by_source": {"scraper:companysite": 1},
    }


async def test_worklist_ready_row_has_reason_contact_and_draft(
    db_session, organization_id
) -> None:
    run, result = await _run_pipeline(
        db_session,
        organization_id,
        site_contacts=[
            ScrapedContact(
                full_name="Jane Doe", role_title="Procurement Manager", email="jane@acme.com"
            )
        ],
    )
    assert result["drafting"]["drafts_generated"] == 1

    worklist = await build_run_worklist(db_session, organization_id, run.id)

    assert worklist.not_shown == []
    (row,) = worklist.ready
    assert row.name == "Acme Inc"
    assert row.industry == "Logistics"
    assert row.verdict == "qualified"
    assert row.why == "IT spend: has the budget"
    (candidate,) = row.candidates
    assert candidate.full_name == "Jane Doe"
    assert candidate.email == "jane@acme.com"
    assert candidate.needs_review is False
    assert candidate.draft is not None and candidate.draft.body
    assert row.skip_reason is None


async def test_worklist_explains_why_a_company_is_not_shown(db_session, organization_id) -> None:
    run, _ = await _run_pipeline(db_session, organization_id, needs_review=True)

    worklist = await build_run_worklist(db_session, organization_id, run.id)

    assert worklist.ready == []
    assert len(worklist.not_shown) == 1
    assert worklist.not_shown[0].skip_reason == "needs review - suspicious name"
    assert worklist.not_shown[0].why == "IT spend: has the budget"


async def test_worklist_failed_enrichment_reason_and_empty_run(db_session, organization_id) -> None:
    run, _ = await _run_pipeline(db_session, organization_id)
    company = (await db_session.execute(select(Company))).scalars().one()
    company.enrichment_status = "failed"
    company.enrichment_error = "could not fetch homepage for acme.com"
    await db_session.commit()

    worklist = await build_run_worklist(db_session, organization_id, run.id)
    assert worklist.not_shown[0].skip_reason == (
        "enrichment failed - could not fetch homepage for acme.com"
    )

    import uuid

    empty = await build_run_worklist(db_session, organization_id, uuid.uuid4())
    assert empty.ready == [] and empty.not_shown == []


# -- hung-site handling ---------------------------------------------------------------------


async def test_scraper_gives_up_on_a_hung_server_within_the_hard_timeout() -> None:
    async def hang(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(30)  # a server that never finishes responding
        return httpx.Response(200, text="never")

    settings = Settings(
        scraper_user_agent="T/1", scraper_request_delay_seconds=0.0,
        scraper_hard_timeout_seconds=0.2,
    )
    provider = WebsiteScraperProvider(settings)
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(hang))  # noqa: SLF001
    try:
        started = asyncio.get_running_loop().time()
        with pytest.raises(ValueError, match="could not fetch homepage"):
            await provider.fetch_company_data("slow.example")
        assert asyncio.get_running_loop().time() - started < 5
    finally:
        await provider.aclose()


class _HangingScraper:
    async def fetch_company_data(self, domain: str) -> ScrapedCompanyData:
        await asyncio.sleep(30)
        return ScrapedCompanyData()


class _CannedContextDev(ContextDevProvider):
    def __init__(self, data: ScrapedCompanyData) -> None:
        super().__init__(Settings(context_dev_api_key="k"))
        self._data = data

    async def fetch_company_data(self, domain: str) -> ScrapedCompanyData:
        return self._data


async def test_fallback_recovers_a_hung_scraper_through_contextdev() -> None:
    recovered = ScrapedCompanyData(
        description="recovered",
        pages_fetched=[FetchedPage(url="https://dhl.com/", status_code=200, text="<html/>")],
    )
    provider = ScraperWithContextDevFallback(
        _HangingScraper(), _CannedContextDev(recovered), scraper_timeout_seconds=0.1
    )
    assert await provider.fetch_company_data("dhl.com") is recovered


# -- reset script guard -----------------------------------------------------------------------


def test_reset_script_classifies_every_table_exactly_once() -> None:
    """A new table must be consciously put in the wipe set or the keep set — never silently left
    out (it would survive a "clean slate") or double-listed."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "reset_test_data.py"
    spec = importlib.util.spec_from_file_location("reset_test_data", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    wipe, keep = set(module.WIPE_TABLES), set(module.KEEP_TABLES)
    assert not wipe & keep
    assert wipe | keep == set(Base.metadata.tables)
    # The InfoBeans setup the user cares about must never be wiped.
    assert {"products", "qualification_criteria", "role_categories"} <= keep


# -- failures must not sink the run ---------------------------------------------------------


async def test_overlong_news_url_cannot_break_the_enrichment_insert(
    db_session, organization_id
) -> None:
    """EnrichmentRecord.source is VARCHAR(100); a long third-party news URL used to abort the
    whole job on Postgres (SQLite, used in tests, doesn't enforce the length — so check it)."""
    from app.modules.enrichment.models import EnrichmentRecord
    from app.modules.enrichment.providers.base import ScrapedSignal
    from app.modules.enrichment.service import _SOURCE_MAX_LEN

    assert EnrichmentRecord.__table__.c.source.type.length == _SOURCE_MAX_LEN

    long_url = "https://news.example/" + "x" * 300
    signal = ScrapedSignal(
        signal_type="news", text="Acme wins a deal", url=long_url, source_label="contextdev"
    )
    await _run_pipeline(
        db_session, organization_id, signal_provider=MockSignalDataProvider([signal])
    )

    records = (await db_session.execute(select(EnrichmentRecord))).scalars().all()
    signal_records = [r for r in records if ":signals:" in r.source]
    assert len(signal_records) == 1
    assert len(signal_records[0].source) <= _SOURCE_MAX_LEN
    assert signal_records[0].source.startswith("contextdev:signals:")
    assert signal_records[0].raw_payload["url"] == long_url  # nothing lost: full URL kept


class _SignalsThatCrashFor(MockSignalDataProvider):
    def __init__(self, bad_domain: str) -> None:
        super().__init__([])
        self._bad = bad_domain

    async def fetch_signals(self, domain: str):  # type: ignore[no-untyped-def]
        if domain == self._bad:
            raise RuntimeError("boom: unexpected provider failure")
        return []


class _CorruptCompanyDataFor(MockCompanyDataProvider):
    """Returns structurally broken data for one domain, so the failure happens in OUR persistence
    code (not inside an isolated provider branch) — the case the per-company savepoint covers."""

    def __init__(self, bad_domain: str) -> None:
        super().__init__(
            ScrapedCompanyData(description="d", industry="Logistics", source_label="x")
        )
        self._bad = bad_domain

    async def fetch_company_data(self, domain: str):  # type: ignore[no-untyped-def]
        data = await super().fetch_company_data(domain)
        if domain == self._bad:
            broken = dataclasses.replace(data)
            object.__setattr__(broken, "pages_fetched", None)
            return broken
        return data


async def test_one_company_crashing_does_not_sink_the_rest_of_the_run(
    db_session, organization_id
) -> None:
    run, _ = await _run_pipeline(
        db_session,
        organization_id,
        extra_candidates=[
            DiscoveredCompany(name="Globex Corp", domain="globex.com", source_snippet="Globex")
        ],
        company_provider=_CorruptCompanyDataFor("acme.com"),
    )
    await db_session.refresh(run)

    by_domain = {
        c.domain: c for c in (await db_session.execute(select(Company))).scalars().all()
    }
    assert by_domain["acme.com"].enrichment_status == "failed"
    assert by_domain["globex.com"].enrichment_status == "enriched"
    assert run.summary["enrichment"]["failed"] == 1
    assert run.summary["enrichment"]["enriched"] == 1

    worklist = await build_run_worklist(db_session, organization_id, run.id)
    acme_row = next(r for r in worklist.not_shown if r.name == "Acme Inc")
    assert acme_row.skip_reason.startswith("enrichment failed - enrichment crashed")


async def test_a_failing_signal_source_does_not_fail_the_company(
    db_session, organization_id
) -> None:
    run, _ = await _run_pipeline(
        db_session,
        organization_id,
        site_contacts=[_JANE],
        signal_provider=_SignalsThatCrashFor("acme.com"),
    )
    await db_session.refresh(run)

    acme = (await db_session.execute(select(Company))).scalars().one()
    assert acme.enrichment_status == "enriched"  # news failed; the company did not
    assert run.summary["enrichment"]["enriched"] == 1
    assert run.summary["enrichment"]["branch_errors"] == {"signals": 1}


async def test_pipeline_reports_stage_and_per_company_detail(db_session, organization_id) -> None:
    ticks: list[dict] = []

    async def progress(done: int, total: int, **extra) -> None:  # type: ignore[no-untyped-def]
        ticks.append({"done": done, "total": total, **extra})

    await _run_pipeline(db_session, organization_id, progress_callback=progress)

    details = [t["detail"] for t in ticks if t.get("detail")]
    assert any(d.startswith("Enriching 1 of 1: acme.com") for d in details)
    assert any(d.startswith("Finished 1 of 1: acme.com") for d in details)
    discovery_ticks = [t for t in ticks if t.get("stage") == 1 and "stage_done" in t]
    assert discovery_ticks and all(t["total"] == 4 and t["done"] == 0 for t in discovery_ticks)
    assert ticks[-1]["done"] == 4 and ticks[-1]["detail"] == "Done"


class _FailsRunCriterion:
    """Judges the per-search requirement as not met, everything else as met, with evidence."""

    @property
    def model_name(self) -> str:
        return "fake-model"

    async def generate(self, company, signals, criteria) -> QualificationJudgment:  # type: ignore[no-untyped-def]
        return QualificationJudgment(
            criteria_results=[
                CriterionVerdict(
                    criterion_id=str(c.id),
                    verdict="not_met" if c.name == "Operates in logistics" else "met",
                    reasoning="checked",
                    evidence_ref="company.industry",
                    evidence_quote="Logistics",
                    confidence=0.9,
                )
                for c in criteria
            ]
        )


async def test_per_search_requirement_is_judged_and_can_reject_a_company(
    db_session, organization_id
) -> None:
    run, result = await _run_pipeline(
        db_session,
        organization_id,
        market_fit_criteria=[{"name": "Operates in logistics", "description": "parcel / freight"}],
        generator=_FailsRunCriterion(),
    )

    assert result["qualification"]["not_qualified"] == 1
    assert result["qualification"]["qualified"] == 0
    # the transient criterion is not saved as an organization setting
    from app.modules.qualification.models import QualificationCriterion

    saved = (await db_session.execute(select(QualificationCriterion))).scalars().all()
    assert [c.name for c in saved] == ["IT spend"]

    worklist = await build_run_worklist(db_session, organization_id, run.id)
    row = worklist.not_shown[0]
    assert row.skip_reason.startswith("does not qualify - Operates in logistics")
    by_name = {c.name: c for c in row.criteria}
    assert by_name["Operates in logistics"].status == "FAIL"
    assert by_name["Operates in logistics"].scope == "run"
    assert by_name["IT spend"].status == "PASS" and by_name["IT spend"].scope == "org"
    assert row.confidence == 0.9


async def test_pipeline_runs_qualification_with_only_per_search_requirements(
    db_session, organization_id
) -> None:
    from app.modules.qualification.models import QualificationCriterion

    run, result = await _run_pipeline(
        db_session,
        organization_id,
        market_fit_criteria=[{"name": "Operates in logistics"}],
        generator=_AllMetQualificationGenerator(),
    )
    assert result["qualification"]["ran"] is True
    assert result["qualification"]["qualified"] == 1
    assert run is not None and QualificationCriterion is not None


class _UnknownFor:
    """Everything is met with evidence, except the named company, whose hard criterion cannot be
    verified (UNKNOWN)."""

    def __init__(self, unknown_company: str) -> None:
        self._unknown = unknown_company

    @property
    def model_name(self) -> str:
        return "fake-model"

    async def generate(self, company, signals, criteria) -> QualificationJudgment:  # type: ignore[no-untyped-def]
        unknown = company.name == self._unknown
        return QualificationJudgment(
            criteria_results=[
                CriterionVerdict(
                    criterion_id=str(c.id),
                    verdict="could_not_determine" if unknown else "met",
                    reasoning="no evidence" if unknown else "ok",
                    evidence_ref=None if unknown else "company.industry",
                    evidence_quote=None if unknown else "Logistics",
                    confidence=None if unknown else 0.9,
                )
                for c in criteria
            ]
        )


_JANE = ScrapedContact(
    full_name="Jane Doe", role_title="Procurement Manager", email="jane@acme.com"
)


async def test_ranking_happens_before_the_cap_so_the_best_company_is_not_the_first_found(
    db_session, organization_id, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "auto_pipeline_max_companies_to_draft", 1)

    # Acme is discovered first but cannot be verified; Globex is verified. A cap that took the
    # first N discovered would classify Acme; ranking must pick Globex.
    run, result = await _run_pipeline(
        db_session,
        organization_id,
        extra_candidates=[
            DiscoveredCompany(name="Globex Corp", domain="globex.com", source_snippet="Globex")
        ],
        site_contacts=[_JANE],
        generator=_UnknownFor("Acme Inc"),
    )

    names = {
        str(c.id): c.name for c in (await db_session.execute(select(Company))).scalars().all()
    }
    assert [names[t["company_id"]] for t in result["ranking"]["top"]] == ["Globex Corp"]
    assert result["ranking"]["ranked"] == 2
    assert result["role_classification"]["companies_classified"] == 1
    assert result["capped"] is True

    worklist = await build_run_worklist(db_session, organization_id, run.id)
    assert [r.name for r in worklist.ready] == ["Globex Corp"]
    assert worklist.ready[0].priority_score is not None
    breakdown = worklist.ready[0].score_breakdown
    assert breakdown is not None and "components" in breakdown
    # the company that lost the slot says so
    (acme,) = [r for r in worklist.not_shown if r.name == "Acme Inc"]
    assert "not classified yet (run limit)" in (acme.skip_reason or "")


async def test_needs_evidence_company_stays_visible_and_labelled(
    db_session, organization_id
) -> None:
    run, result = await _run_pipeline(
        db_session,
        organization_id,
        site_contacts=[_JANE],
        generator=_UnknownFor("Acme Inc"),
    )
    assert result["qualification"]["could_not_determine"] == 1
    assert result["ranking"]["ranked"] == 1

    worklist = await build_run_worklist(db_session, organization_id, run.id)
    (row,) = worklist.ready
    assert row.verdict == "could_not_determine"
    assert row.why == "Needs evidence - could not verify: IT spend"
    assert row.criteria[0].status == "UNKNOWN"


async def test_companies_reused_from_the_index_are_qualified_and_ranked_too(
    db_session, organization_id
) -> None:
    existing = Company(
        organization_id=organization_id,
        name="Existing Logistics Co",
        domain="existing.com",
        industry="SaaS Logistics",
    )
    db_session.add(existing)
    await db_session.commit()

    run, result = await _run_pipeline(db_session, organization_id, site_contacts=[_JANE])
    await db_session.refresh(run)

    assert run.summary["reused_from_index"] == 1
    assert str(existing.id) in run.summary["company_ids"]
    assert result["qualification"]["qualified"] == 2  # the new one AND the reused one
    worklist = await build_run_worklist(db_session, organization_id, run.id)
    all_names = {r.name for r in [*worklist.ready, *worklist.not_shown]}
    assert "Existing Logistics Co" in all_names


class _FailingCompanyData(MockCompanyDataProvider):
    def __init__(self) -> None:
        super().__init__(ScrapedCompanyData())

    async def fetch_company_data(self, domain: str):  # type: ignore[no-untyped-def]
        raise ValueError(f"could not fetch homepage for {domain}")


class _OneSearchContact:
    async def search_contacts(self, company_name, domain):  # type: ignore[no-untyped-def]
        return [
            ScrapedContact(
                full_name="Jane Doe",
                role_title="CEO",
                linkedin_url="https://www.linkedin.com/in/janedoe",
                confidence=0.95,
                source="serper:linkedin",
            )
        ]


async def test_contacts_are_still_found_when_the_company_website_cannot_be_fetched(
    db_session, organization_id
) -> None:
    from app.modules.contacts.models import ContactChannel

    run, _ = await _run_pipeline(
        db_session,
        organization_id,
        company_provider=_FailingCompanyData(),
        contact_search=_OneSearchContact(),
    )
    await db_session.refresh(run)

    acme = (await db_session.execute(select(Company))).scalars().one()
    assert acme.enrichment_status == "failed"  # company data itself is still reported as failed
    contact = (await db_session.execute(select(Contact))).scalars().one()  # ...contacts survive
    assert contact.full_name == "Jane Doe"
    assert contact.source == "serper:linkedin" and contact.confidence == 0.95
    assert contact.needs_review is True
    assert contact.needs_review_reason == "found via contact search (likely match), not confirmed"
    channel = (await db_session.execute(select(ContactChannel))).scalars().one()
    assert (channel.channel_type, channel.value) == (
        "linkedin",
        "https://www.linkedin.com/in/janedoe",
    )
    assert run.summary["enrichment"]["failed"] == 1


async def test_an_unreachable_host_is_not_retried_for_every_other_page(monkeypatch) -> None:
    scraper = WebsiteScraperProvider(Settings(scraper_request_delay_seconds=0.0))
    calls: list[str] = []

    async def always_times_out(url: str):  # type: ignore[no-untyped-def]
        calls.append(url)
        raise TimeoutError

    monkeypatch.setattr(scraper, "_get", always_times_out)
    try:
        with pytest.raises(ValueError):
            await scraper.fetch_company_data("blocked.example")
        calls_for_homepage = len(calls)
        assert await scraper.fetch_signals("blocked.example") == []
        assert len(calls) == calls_for_homepage  # /news, /press, /careers cost nothing more
    finally:
        await scraper.aclose()


async def test_each_filled_field_records_where_it_came_from(db_session, organization_id) -> None:
    provider = MockCompanyDataProvider(
        ScrapedCompanyData(
            description="Acme runs parcel networks across Europe for many large retailers.",
            industry="Logistics",
            source_label="scraper:companysite",
            field_sources={"industry": "contextdev:brand"},
        )
    )
    run, _ = await _run_pipeline(db_session, organization_id, company_provider=provider)
    await db_session.refresh(run)

    acme = (await db_session.execute(select(Company))).scalars().one()
    assert acme.field_provenance["industry"]["source"] == "contextdev:brand"
    assert acme.field_provenance["industry"]["confidence"] == 0.9
    assert acme.field_provenance["description"]["source"] == "scraper:companysite"
    assert acme.field_provenance["description"]["confidence"] == 0.7
    assert run.summary["context_dev"] is None  # scraper-only provider: nothing paid, no usage

    worklist = await build_run_worklist(db_session, organization_id, run.id)
    row = [*worklist.ready, *worklist.not_shown][0]
    assert row.provenance["industry"]["source"] == "contextdev:brand"
