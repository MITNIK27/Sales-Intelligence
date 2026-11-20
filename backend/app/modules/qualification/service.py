import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.ai_recommendation.gemini_client import GeminiClientError
from app.modules.companies.models import Company
from app.modules.companies.service import (
    active_company_ids,
    get_company_detail,
    get_or_create_company,
)
from app.modules.enrichment.models import EnrichmentRecord
from app.modules.enrichment.providers.base import (
    CompanyDataProvider,
    ContactDataProvider,
    DomainDiscoveryProvider,
    SignalDataProvider,
)
from app.modules.enrichment.providers.factory import build_company_providers
from app.modules.enrichment.providers.search_contacts import (
    ContactSearchProvider,
    SerperContactSearchProvider,
)
from app.modules.enrichment.providers.search_serper import SerperSearchProvider
from app.modules.enrichment.providers.website_scraper import WebsiteScraperProvider
from app.modules.enrichment.service import _enrich_company, list_company_signals
from app.modules.jobs.models import Job
from app.modules.llm.structured import StructuredLLM, build_structured_llm
from app.modules.opportunity.models import ORIGIN_QUICK_CHECK, CompanyOpportunity
from app.modules.opportunity.quickcheck import run_quick_check_opportunity
from app.modules.opportunity.research.sources import build_research_sources
from app.modules.opportunity.research.types import ResearchSources
from app.modules.opportunity.service import get_or_create_opportunity, save_focus_evidence
from app.modules.qualification.evidence import describe_source, status_for_verdict
from app.modules.qualification.models import (
    QualificationCriterion,
    QualificationCriterionResult,
    QualificationResult,
)
from app.modules.qualification.prompts import PROMPT_VERSION
from app.modules.qualification.qualification_generator import (
    GeminiQualificationGenerator,
    QualificationGenerator,
)

ProgressCallback = Callable[..., Awaitable[None]]
JOB_TYPE_BULK_QUALIFY = "bulk_qualify"
JOB_TYPE_ADHOC_QUALIFY = "adhoc_qualify"
# A check that did not decide anything about the company: no criteria were chosen for the run, or
# the person asked for an informational check on one company. Never Qualified / Not qualified.
VERDICT_NOT_CHECKED = "not_checked"


class CompanyNotFoundError(Exception):
    """Raised by `run_qualification_check` when the company doesn't exist or belongs to a
    different organization — the router surfaces this as a 404."""


class NoCriteriaConfiguredError(Exception):
    """Raised by `run_qualification_check` when there is nothing to judge against: judging against
    no criteria isn't a check. The router surfaces this as a 422."""


def clean_criteria(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The criteria a person typed, as plain specs `{name, description, must_have}`. Blank ones
    and repeats (ignoring case) are dropped."""
    specs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        specs.append(
            {
                "name": name[:255],
                "description": (str(item.get("description") or "").strip() or None),
                "must_have": bool(item.get("must_have")),
            }
        )
    return specs


def add_company_criteria(company: Company, specs: list[dict[str, Any]]) -> None:
    """Adds the criteria to the company's own list, skipping names it already has."""
    merged = clean_criteria([*(company.criteria or []), *specs])
    company.criteria = merged  # a new list, so the change is saved


def build_run_criteria(
    organization_id: uuid.UUID, specs: list[dict[str, Any]] | None
) -> list[QualificationCriterion]:
    """Turns the criteria chosen for a run (or one check) into transient criteria. A criterion is
    hard only when the person marked it "must have" for this run; each has a fresh id and is never
    added to a session, so it exists only for this run's judgments."""
    criteria: list[QualificationCriterion] = []
    for spec in specs or []:
        name = str(spec.get("name") or "").strip()
        if not name:
            continue
        criteria.append(
            QualificationCriterion(
                id=uuid.uuid4(),
                organization_id=organization_id,
                name=name[:255],
                description=(str(spec.get("description") or "").strip() or None),
                is_disqualifying=bool(spec.get("must_have")),
                is_active=True,
            )
        )
    return criteria


def _compute_overall_verdict(criteria_results: list[dict[str, object]]) -> str:
    """Deterministic — never decided by the LLM. Only `is_disqualifying` ("hard requirement")
    criteria gate the overall verdict; non-disqualifying criteria are informational context for
    the rep and never flip it on their own. An org with zero disqualifying criteria configured
    gets "qualified" by default (nothing was set up to block it)."""
    disqualifying = [c for c in criteria_results if c["is_disqualifying"]]
    if any(c["verdict"] == "not_met" for c in disqualifying):
        return "not_qualified"
    if any(c["verdict"] == "could_not_determine" for c in disqualifying):
        return "could_not_determine"
    return "qualified"


async def judge_qualification(
    company: Company,
    signals: list[EnrichmentRecord],
    criteria: list[QualificationCriterion],
    generator: QualificationGenerator,
    run_criterion_ids: frozenset[str] = frozenset(),
    focus: str | None = None,
) -> tuple[str, list[dict[str, object]]]:
    """Pure core: no session, no persistence. Calls the generator, snapshots each criterion AS
    JUDGED (not a live reference — a later edit to the criterion must never rewrite this
    history), and computes the deterministic overall verdict."""
    # `focus` is only passed when there is one, so a generator written without it still works.
    judgment = await generator.generate(
        company, signals, criteria, **({"focus": focus} if focus else {})
    )

    criteria_by_id = {str(criterion.id): criterion for criterion in criteria}
    verdicts_by_id = {v.criterion_id: v for v in judgment.criteria_results}
    if set(verdicts_by_id) != set(criteria_by_id):
        raise GeminiClientError("Gemini did not return exactly one verdict per given criterion")

    criteria_results: list[dict[str, object]] = []
    for criterion_id, criterion in criteria_by_id.items():
        item = verdicts_by_id[criterion_id]
        criteria_results.append(
            {
                "criterion_id": criterion_id,
                "criterion_name": criterion.name,
                "is_disqualifying": criterion.is_disqualifying,
                # "run" = defined for this search on the confirm card, "org" = saved criteria.
                "scope": "run" if criterion_id in run_criterion_ids else "org",
                "verdict": item.verdict,
                # PASS / FAIL / UNKNOWN is the rep-facing vocabulary; `verdict` keeps the stored
                # met / not_met / could_not_determine values so older rows and the badges agree.
                "status": status_for_verdict(item.verdict),
                "reasoning": item.reasoning,
                "evidence_ref": item.evidence_ref,
                "evidence_quote": item.evidence_quote,
                "confidence": item.confidence,
                **describe_source(item.evidence_ref, signals),
            }
        )

    return _compute_overall_verdict(criteria_results), criteria_results


async def run_qualification_check(
    session: AsyncSession,
    organization_id: uuid.UUID,
    company_id: uuid.UUID,
    generator: QualificationGenerator,
    criteria: list[QualificationCriterion],
    run_criterion_ids: frozenset[str] = frozenset(),
    informational: bool = False,
    allow_empty: bool = False,
    focus: str | None = None,
    focus_signals: list[EnrichmentRecord] | None = None,
) -> QualificationResult:
    """Judges one company against exactly the `criteria` given: nothing is added from the saved
    list, so a saved criterion only counts when someone chose it. With `informational`, the
    per-criterion answers are kept but the overall verdict is "not checked", never Qualified or Not
    qualified. With no criteria and `allow_empty` (a run where none were chosen), a "not checked"
    result is stored without a model call, so the company can still be ranked. `focus` is the area
    a Quick Check was asked to judge fit around; `focus_signals` are evidence gathered for it,
    shown to the model first (not stored as company signals)."""
    company = await get_company_detail(session, organization_id, company_id)
    if company is None:
        raise CompanyNotFoundError(f"company {company_id} not found")

    if not criteria and not allow_empty:
        raise NoCriteriaConfiguredError("no criteria chosen to check against")

    overall_verdict: str
    criteria_results: list[dict[str, Any]]
    if not criteria:
        overall_verdict, criteria_results = VERDICT_NOT_CHECKED, []
    else:
        signals = [
            *(focus_signals or []),
            *await list_company_signals(session, organization_id, company_id),
        ]
        overall_verdict, criteria_results = await judge_qualification(
            company, signals, criteria, generator, run_criterion_ids, focus
        )
        if informational:
            overall_verdict = VERDICT_NOT_CHECKED

    result = QualificationResult(
        organization_id=organization_id,
        company_id=company_id,
        overall_verdict=overall_verdict,
        criteria_results=criteria_results,
        criteria=[
            QualificationCriterionResult.from_entry(organization_id, position, entry)
            for position, entry in enumerate(criteria_results)
        ],
        model_used=generator.model_name,
        prompt_version=PROMPT_VERSION,
        focus=focus,
    )
    session.add(result)
    await session.flush()
    return result


_FOCUS_RESULTS = 5


async def _focus_evidence(
    session: AsyncSession,
    domain_provider: DomainDiscoveryProvider,
    company: Company,
    opportunity: CompanyOpportunity,
    focus: str,
) -> list[EnrichmentRecord]:
    """A web search for "{company} {focus}", kept as evidence tagged with the opportunity so it
    has an id and can be cited and re-checked later. It is evidence for that area only, so it
    never colours the company's general signal list. A provider that cannot search, or a failed
    search, just means no extra evidence."""
    search = getattr(domain_provider, "search_raw", None)
    if search is None:
        return []
    try:
        results = await search(f"{company.name} {focus}", _FOCUS_RESULTS)
    except Exception:  # noqa: BLE001 - extra evidence is best-effort
        return []
    return await save_focus_evidence(session, company, opportunity, results)


async def _run_adhoc_qualification(
    session: AsyncSession,
    job: Job,
    domain_provider: DomainDiscoveryProvider,
    company_provider: CompanyDataProvider,
    contact_provider: ContactDataProvider,
    signal_provider: SignalDataProvider,
    generator: QualificationGenerator,
    progress_callback: ProgressCallback | None = None,
    opportunity_llm: StructuredLLM | None = None,
    research_sources: ResearchSources | None = None,
    contact_search: ContactSearchProvider | None = None,
) -> dict[str, Any]:
    """Testable core — takes providers/generator explicitly so tests inject fakes/mocks instead
    of hitting the network or Gemini. Resolves-or-creates a Company from a name/domain the user
    typed, ENRICHES it (this used to be missing — a brand-new company had nothing but a bare
    name/domain to judge against, so every criterion landed on could_not_determine by default,
    not because the company was genuinely unqualified), then runs the same judgment core used for
    an existing company.

    Checks that criteria were given FIRST, before creating or enriching anything, so a bad request
    fails fast without a wasted scrape (same reasoning as the bulk-qualify job checking once up
    front instead of per company)."""
    payload = job.payload or {}
    typed_criteria = build_run_criteria(job.organization_id, payload.get("criteria"))
    if not typed_criteria:
        raise NoCriteriaConfiguredError("no criteria chosen to check against")
    focus = (payload.get("focus") or "").strip() or None
    # Steps: gather company info, (only with a focus) look for evidence about it, judge, and (when
    # a model is given) look at the opportunity.
    steps_total = (3 if focus else 2) + (1 if opportunity_llm else 0)
    company, created = await get_or_create_company(
        session, job.organization_id, name=payload.get("name"), domain=payload.get("domain")
    )
    await session.flush()
    if progress_callback:
        await progress_callback(0, steps_total, detail="Finding the website and company info")

    # No progress_callback passed through — _enrich_company's own internal 4-step tally would
    # conflict with this job's coarser progress below.
    enriched = await _enrich_company(
        session,
        job.organization_id,
        company,
        domain_provider,
        company_provider,
        contact_provider,
        signal_provider,
    )
    if created and enriched.get("reason") == "duplicate_domain":
        # Typed by name only, but the website found belongs to a company we already have. The
        # row made a moment ago is empty, so drop it and check the existing company instead.
        existing = await session.get(Company, enriched["existing_company_id"])
        if existing is not None:  # if it has gone, keep the company just made rather than lose both
            await session.delete(company)
            await session.flush()
            company, created = existing, False
            await _enrich_company(
                session,
                job.organization_id,
                company,
                domain_provider,
                company_provider,
                contact_provider,
                signal_provider,
            )
    done = 1
    if progress_callback:
        next_step = f"Looking for evidence about {focus}" if focus else "Judging fit"
        await progress_callback(done, steps_total, detail=next_step)

    focus_signals: list[EnrichmentRecord] = []
    focus_opportunity = None
    if focus:
        focus_opportunity, _ = await get_or_create_opportunity(
            session, company, focus, origin=ORIGIN_QUICK_CHECK
        )
        focus_signals = await _focus_evidence(
            session, domain_provider, company, focus_opportunity, focus
        )
        done += 1
        if progress_callback:
            await progress_callback(done, steps_total, detail="Judging fit")

    result = await run_qualification_check(
        session,
        job.organization_id,
        company.id,
        generator,
        typed_criteria,
        focus=focus,
        focus_signals=focus_signals,
    )

    opportunity: dict[str, Any] | None = None
    if opportunity_llm is not None:
        if progress_callback:
            await progress_callback(
                steps_total - 1,
                steps_total,
                detail="Assessing the opportunity" if focus else "Looking for opportunity areas",
            )
        opportunity = await run_quick_check_opportunity(
            session,
            opportunity_llm,
            company,
            focus_opportunity,
            research_sources,
            contact_search=contact_search,
            chosen_ids={uuid.UUID(p) for p in payload.get("product_ids") or []},
        )
    if progress_callback:
        await progress_callback(steps_total, steps_total, detail="Done")

    return {
        "company_id": str(company.id),
        "company_name": company.name,
        "company_domain": company.domain,
        "company_created": created,
        "qualification_result_id": str(result.id),
        "focus": focus,
        "opportunity": opportunity,
        # How the website and company look-up went, so a bare-name check says so.
        "lookup": {
            "status": enriched.get("status"),
            "reason": enriched.get("reason"),
            "domain": company.domain,
        },
    }


async def run_adhoc_qualification_job(
    session: AsyncSession, job: Job, progress_callback: ProgressCallback | None = None
) -> dict[str, Any]:
    """Handler registered with the job worker — builds the real (network/Gemini-calling)
    providers and delegates to `_run_adhoc_qualification`."""
    settings = get_settings()
    domain_provider = SerperSearchProvider(settings)
    scraper = WebsiteScraperProvider(settings)
    providers = build_company_providers(settings, scraper)
    generator = GeminiQualificationGenerator(settings)
    research_sources, closers = build_research_sources(settings, scraper)
    try:
        return await _run_adhoc_qualification(
            session,
            job,
            domain_provider,
            providers.company,
            scraper,
            providers.signals,
            generator,
            progress_callback,
            opportunity_llm=build_structured_llm(settings, order=settings.opportunity_llm_order),
            research_sources=research_sources,
            contact_search=SerperContactSearchProvider(settings, domain_provider),
        )
    finally:
        await scraper.aclose()
        for closer in closers:
            await closer.aclose()


async def list_qualification_results(
    session: AsyncSession, organization_id: uuid.UUID, company_id: uuid.UUID
) -> list[QualificationResult]:
    stmt = (
        select(QualificationResult)
        .where(
            QualificationResult.organization_id == organization_id,
            QualificationResult.company_id == company_id,
        )
        .order_by(QualificationResult.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def _run_bulk_qualification(
    session: AsyncSession,
    organization_id: uuid.UUID,
    company_ids: list[uuid.UUID],
    generator: QualificationGenerator,
    progress_callback: ProgressCallback | None = None,
    criteria: list[QualificationCriterion] | None = None,
) -> dict[str, Any]:
    """Testable core — qualifies every given company id sequentially, same judgment core as a
    single check (`run_qualification_check`), so a Market Discovery run's newly-found companies
    can go from "found" to "judged" without a rep opening each one individually. Moved out of
    `run_bulk_qualification_job` so the auto-pipeline orchestrator can call it directly with an
    explicit id list, without needing a `Job` row of its own — same reasoning as
    `_run_adhoc_qualification`.

    `criteria` are the ones chosen for this run; none chosen is allowed and leaves each company
    "not checked" (it is then ranked by offering fit and nothing is excluded).

    A single company's `GeminiClientError` (e.g. a transient Gemini hiccup) is caught and recorded
    in `errors` rather than aborting the rest of the batch — one bad company shouldn't cost every
    other company in the run its result."""
    company_ids = await active_company_ids(session, organization_id, company_ids)
    chosen = criteria or []
    run_ids = frozenset(str(c.id) for c in chosen)
    total = len(company_ids) or 1
    counts = {"qualified": 0, "not_qualified": 0, "could_not_determine": 0, "not_checked": 0}
    qualified_company_ids: list[str] = []
    needs_evidence_company_ids: list[str] = []
    eligible_company_ids: list[str] = []
    errors: list[dict[str, str]] = []
    names = (
        {
            cid: name
            for cid, name in (
                await session.execute(
                    select(Company.id, Company.name).where(Company.id.in_(company_ids))
                )
            ).all()
        }
        if progress_callback and company_ids
        else {}
    )
    for i, company_id in enumerate(company_ids, start=1):
        if progress_callback:
            await progress_callback(
                i - 1,
                total,
                detail=f"Checking fit: {names.get(company_id, 'company')} ({i} of {total})",
            )
        try:
            result = await run_qualification_check(
                session,
                organization_id,
                company_id,
                generator,
                chosen,
                run_criterion_ids=run_ids,
                allow_empty=True,
            )
            counts[result.overall_verdict] += 1
            if result.overall_verdict == "qualified":
                qualified_company_ids.append(str(company_id))
            elif result.overall_verdict == "could_not_determine":
                needs_evidence_company_ids.append(str(company_id))
            if result.overall_verdict != "not_qualified":
                eligible_company_ids.append(str(company_id))
        except (CompanyNotFoundError, GeminiClientError) as exc:
            errors.append({"company_id": str(company_id), "error": str(exc)})
        if progress_callback:
            await progress_callback(
                i, total, detail=f"{names.get(company_id, 'Company')} checked ({i} of {total})"
            )
    return {
        **counts,
        "qualified_company_ids": qualified_company_ids,
        "needs_evidence_company_ids": needs_evidence_company_ids,
        # Everything that may go on to ranking: not rejected by a must-have criterion.
        "eligible_company_ids": eligible_company_ids,
        "errors": errors,
    }


async def run_bulk_qualification_job(
    session: AsyncSession, job: Job, progress_callback: ProgressCallback | None = None
) -> dict[str, Any]:
    """Handler registered with the job worker (Phase A2.4) — unpacks `job.payload["company_ids"]`
    and the run's chosen `criteria`, and delegates to `_run_bulk_qualification`."""
    generator = GeminiQualificationGenerator(get_settings())
    payload = job.payload or {}
    company_ids = [uuid.UUID(cid) for cid in payload.get("company_ids", [])]
    return await _run_bulk_qualification(
        session,
        job.organization_id,
        company_ids,
        generator,
        progress_callback,
        build_run_criteria(job.organization_id, payload.get("criteria")),
    )
