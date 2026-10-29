import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.ai_recommendation.gemini_client import GeminiClientError
from app.modules.companies.models import Company
from app.modules.companies.service import get_company_detail, get_or_create_company
from app.modules.enrichment.models import ENTITY_TYPE_COMPANY, EnrichmentRecord
from app.modules.enrichment.providers.base import (
    CompanyDataProvider,
    ContactDataProvider,
    DomainDiscoveryProvider,
    SignalDataProvider,
)
from app.modules.enrichment.providers.factory import build_company_providers
from app.modules.enrichment.providers.search_serper import SerperSearchProvider
from app.modules.enrichment.providers.website_scraper import WebsiteScraperProvider
from app.modules.enrichment.service import _enrich_company, list_company_signals
from app.modules.jobs.models import Job
from app.modules.qualification.evidence import describe_source, status_for_verdict
from app.modules.qualification.models import QualificationCriterion, QualificationResult
from app.modules.qualification.qualification_generator import (
    GeminiQualificationGenerator,
    QualificationGenerator,
)

ProgressCallback = Callable[..., Awaitable[None]]
JOB_TYPE_BULK_QUALIFY = "bulk_qualify"
JOB_TYPE_ADHOC_QUALIFY = "adhoc_qualify"


async def create_criterion(
    session: AsyncSession,
    organization_id: uuid.UUID,
    name: str,
    description: str | None,
    is_disqualifying: bool,
    is_active: bool,
) -> QualificationCriterion:
    criterion = QualificationCriterion(
        organization_id=organization_id,
        name=name,
        description=description,
        is_disqualifying=is_disqualifying,
        is_active=is_active,
    )
    session.add(criterion)
    await session.flush()
    return criterion


async def list_criteria(
    session: AsyncSession, organization_id: uuid.UUID, limit: int = 50, offset: int = 0
) -> tuple[list[QualificationCriterion], int]:
    count_stmt = select(func.count()).select_from(QualificationCriterion).where(
        QualificationCriterion.organization_id == organization_id
    )
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = (
        select(QualificationCriterion)
        .where(QualificationCriterion.organization_id == organization_id)
        .order_by(QualificationCriterion.name)
        .limit(limit)
        .offset(offset)
    )
    criteria = (await session.execute(stmt)).scalars().all()
    return list(criteria), total


async def get_criterion(
    session: AsyncSession, organization_id: uuid.UUID, criterion_id: uuid.UUID
) -> QualificationCriterion | None:
    criterion = await session.get(QualificationCriterion, criterion_id)
    if criterion is None or criterion.organization_id != organization_id:
        return None
    return criterion


async def update_criterion(
    session: AsyncSession,
    organization_id: uuid.UUID,
    criterion_id: uuid.UUID,
    updates: dict[str, object],
) -> QualificationCriterion | None:
    """`updates` should already be limited to explicitly-provided fields (e.g. via
    `CriterionUpdate.model_dump(exclude_unset=True)`) so an omitted field is left untouched
    while an explicit `null` still clears it."""
    criterion = await get_criterion(session, organization_id, criterion_id)
    if criterion is None:
        return None
    for field, value in updates.items():
        setattr(criterion, field, value)
    await session.flush()
    return criterion


async def delete_criterion(
    session: AsyncSession, organization_id: uuid.UUID, criterion_id: uuid.UUID
) -> bool:
    criterion = await get_criterion(session, organization_id, criterion_id)
    if criterion is None:
        return False
    await session.delete(criterion)
    await session.flush()
    return True


async def list_active_criteria(
    session: AsyncSession, organization_id: uuid.UUID
) -> list[QualificationCriterion]:
    stmt = (
        select(QualificationCriterion)
        .where(
            QualificationCriterion.organization_id == organization_id,
            QualificationCriterion.is_active.is_(True),
        )
        .order_by(QualificationCriterion.name)
    )
    return list((await session.execute(stmt)).scalars().all())


class CompanyNotFoundError(Exception):
    """Raised by `run_qualification_check` when the company doesn't exist or belongs to a
    different organization — the router surfaces this as a 404."""


class NoCriteriaConfiguredError(Exception):
    """Raised by `run_qualification_check` when the org has zero active qualification criteria —
    judging against nothing isn't a qualification. The router surfaces this as a 422."""


def build_run_criteria(
    organization_id: uuid.UUID, specs: list[dict[str, Any]] | None
) -> list[QualificationCriterion]:
    """Turns the per-search "hard requirements" from the confirm card into transient criteria.
    They are always hard (that is the point of defining them for a search), have fresh ids and
    are never added to a session — they exist only for this run's judgments."""
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
                is_disqualifying=True,
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
        raise GeminiClientError(
            "Gemini did not return exactly one verdict per given criterion"
        )

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
    extra_criteria: list[QualificationCriterion] | None = None,
    focus: str | None = None,
    focus_signals: list[EnrichmentRecord] | None = None,
) -> QualificationResult:
    """`extra_criteria` are per-run requirements (never persisted) judged in the same call as the
    organization's saved criteria. `focus` is the area a Quick Check was asked to judge fit around;
    `focus_signals` are evidence gathered for it, shown to the model first (they are not stored
    as company signals, so a focused search never colours the company's general record)."""
    company = await get_company_detail(session, organization_id, company_id)
    if company is None:
        raise CompanyNotFoundError(f"company {company_id} not found")

    extra = extra_criteria or []
    criteria = [*await list_active_criteria(session, organization_id), *extra]
    if not criteria:
        raise NoCriteriaConfiguredError("no active qualification criteria configured")

    signals = [
        *(focus_signals or []),
        *await list_company_signals(session, organization_id, company_id),
    ]
    overall_verdict, criteria_results = await judge_qualification(
        company, signals, criteria, generator, frozenset(str(c.id) for c in extra), focus
    )

    result = QualificationResult(
        organization_id=organization_id,
        company_id=company_id,
        overall_verdict=overall_verdict,
        criteria_results=criteria_results,
        model_used=generator.model_name,
        focus=focus,
    )
    session.add(result)
    await session.flush()
    return result


_FOCUS_RESULTS = 5


async def _focus_evidence(
    domain_provider: DomainDiscoveryProvider, company: Company, focus: str
) -> list[EnrichmentRecord]:
    """A web search for "{company} {focus}", turned into evidence the judgment can cite. In-memory
    only (never added to a session): focused research must not colour the company's general
    record. A provider that cannot search, or a failed search, just means no extra evidence."""
    search = getattr(domain_provider, "search_raw", None)
    if search is None:
        return []
    try:
        results = await search(f"{company.name} {focus}", _FOCUS_RESULTS)
    except Exception:  # noqa: BLE001 - extra evidence is best-effort
        return []
    now = datetime.now(UTC)
    records: list[EnrichmentRecord] = []
    for item in results:
        title = (item.get("title") or "").strip()
        snippet = (item.get("snippet") or "").strip()
        if not (title or snippet):
            continue
        records.append(
            EnrichmentRecord(
                organization_id=company.organization_id,
                entity_type=ENTITY_TYPE_COMPANY,
                entity_id=company.id,
                source="serper:focus_search",
                raw_payload={
                    "signal_type": "focus_search",
                    "text": f"{title}. {snippet}".strip(),
                    "url": item.get("link"),
                    "date": item.get("date"),
                    "provider": "serper",
                },
                fetched_at=now,
            )
        )
    return records


async def _run_adhoc_qualification(
    session: AsyncSession,
    job: Job,
    domain_provider: DomainDiscoveryProvider,
    company_provider: CompanyDataProvider,
    contact_provider: ContactDataProvider,
    signal_provider: SignalDataProvider,
    generator: QualificationGenerator,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Testable core — takes providers/generator explicitly so tests inject fakes/mocks instead
    of hitting the network or Gemini. Resolves-or-creates a Company from a name/domain the user
    typed, ENRICHES it (this used to be missing — a brand-new company had nothing but a bare
    name/domain to judge against, so every criterion landed on could_not_determine by default,
    not because the company was genuinely unqualified), then runs the same judgment core used for
    an existing company.

    Checks active criteria FIRST, before creating or enriching anything, so a misconfigured org
    fails fast without a wasted scrape (same reasoning as the bulk-qualify job checking once up
    front instead of per company)."""
    if not await list_active_criteria(session, job.organization_id):
        raise NoCriteriaConfiguredError("no active qualification criteria configured")

    payload = job.payload or {}
    focus = (payload.get("focus") or "").strip() or None
    # Steps: gather company info, (only with a focus) look for evidence about it, judge.
    steps_total = 3 if focus else 2
    company, created = await get_or_create_company(
        session, job.organization_id, name=payload.get("name"), domain=payload.get("domain")
    )
    await session.flush()
    if progress_callback:
        await progress_callback(0, steps_total, detail="Finding the website and company info")

    # No progress_callback passed through — _enrich_company's own internal 4-step tally would
    # conflict with this job's coarser progress below.
    await _enrich_company(
        session, job.organization_id, company,
        domain_provider, company_provider, contact_provider, signal_provider,
    )
    done = 1
    if progress_callback:
        next_step = f"Looking for evidence about {focus}" if focus else "Judging fit"
        await progress_callback(done, steps_total, detail=next_step)

    focus_signals: list[EnrichmentRecord] = []
    if focus:
        focus_signals = await _focus_evidence(domain_provider, company, focus)
        done += 1
        if progress_callback:
            await progress_callback(done, steps_total, detail="Judging fit")

    result = await run_qualification_check(
        session, job.organization_id, company.id, generator,
        focus=focus, focus_signals=focus_signals,
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
        )
    finally:
        await scraper.aclose()


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
    extra_criteria: list[QualificationCriterion] | None = None,
) -> dict[str, Any]:
    """Testable core — qualifies every given company id sequentially, same judgment core as a
    single check (`run_qualification_check`), so a Market Discovery run's newly-found companies
    can go from "found" to "judged" without a rep opening each one individually. Moved out of
    `run_bulk_qualification_job` so the auto-pipeline orchestrator can call it directly with an
    explicit id list, without needing a `Job` row of its own — same reasoning as
    `_run_adhoc_qualification`.

    Checks active criteria exist once up front rather than per company: a misconfigured org
    should fail the whole job immediately and clearly, not produce N identical per-company
    failures. A single company's `GeminiClientError` (e.g. a transient Gemini hiccup) is caught
    and recorded in `errors` rather than aborting the rest of the batch — one bad company
    shouldn't cost every other company in the run its result."""
    if not extra_criteria and not await list_active_criteria(session, organization_id):
        raise NoCriteriaConfiguredError("no active qualification criteria configured")

    total = len(company_ids) or 1
    counts = {"qualified": 0, "not_qualified": 0, "could_not_determine": 0}
    qualified_company_ids: list[str] = []
    needs_evidence_company_ids: list[str] = []
    errors: list[dict[str, str]] = []
    for i, company_id in enumerate(company_ids, start=1):
        try:
            result = await run_qualification_check(
                session, organization_id, company_id, generator, extra_criteria
            )
            counts[result.overall_verdict] += 1
            if result.overall_verdict == "qualified":
                qualified_company_ids.append(str(company_id))
            elif result.overall_verdict == "could_not_determine":
                needs_evidence_company_ids.append(str(company_id))
        except (CompanyNotFoundError, GeminiClientError) as exc:
            errors.append({"company_id": str(company_id), "error": str(exc)})
        if progress_callback:
            await progress_callback(i, total)
    return {
        **counts,
        "qualified_company_ids": qualified_company_ids,
        "needs_evidence_company_ids": needs_evidence_company_ids,
        "errors": errors,
    }


async def run_bulk_qualification_job(
    session: AsyncSession, job: Job, progress_callback: ProgressCallback | None = None
) -> dict[str, Any]:
    """Handler registered with the job worker (Phase A2.4) — unpacks `job.payload["company_ids"]`
    and delegates to `_run_bulk_qualification`."""
    generator = GeminiQualificationGenerator(get_settings())
    payload = job.payload or {}
    company_ids = [uuid.UUID(cid) for cid in payload.get("company_ids", [])]
    return await _run_bulk_qualification(
        session, job.organization_id, company_ids, generator, progress_callback
    )
