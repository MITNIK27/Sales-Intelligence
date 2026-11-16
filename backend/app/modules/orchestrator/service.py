import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.ai_recommendation.gemini_client import GeminiClientError
from app.modules.companies.models import Company
from app.modules.companies.service import (
    active_company_ids,
    confirm_company,
    list_company_ids_by_source_run,
)
from app.modules.contacts.models import Contact
from app.modules.contacts.service import confirm_contact
from app.modules.discovery_agent.agent import (
    CompanyDiscoveryAgentProtocol,
    get_default_discovery_agent,
)
from app.modules.draft.draft_generator import DraftGenerator, GeminiDraftGenerator
from app.modules.draft.models import DRAFT_TYPE_FIRST_TOUCH
from app.modules.draft.service import NeedsReviewError as DraftNeedsReviewError
from app.modules.draft.service import generate_draft
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
from app.modules.ingestion.market_discovery import _run_market_discovery
from app.modules.ingestion.models import IngestionRun
from app.modules.jobs.models import Job
from app.modules.opportunity.focus import offerings_for_keywords
from app.modules.opportunity.run_stage import queue_run_area_research, queue_run_fit
from app.modules.orchestrator.ranking_step import rank_judged_companies
from app.modules.qualification.qualification_generator import (
    GeminiQualificationGenerator,
    QualificationGenerator,
)
from app.modules.qualification.service import (
    _run_bulk_qualification,
    add_company_criteria,
    build_run_criteria,
    clean_criteria,
)
from app.modules.role_relevance.role_relevance_generator import (
    GeminiRoleRelevanceGenerator,
    RoleRelevanceGenerator,
)
from app.modules.role_relevance.service import (
    CompanyNeedsReviewError,
    CompanyNotFoundError,
    NoContactsError,
    list_active_categories,
    list_latest_role_relevance,
    run_role_relevance_check,
)

# (done, total, **extra) — extra keys (detail, stage, counts) are merged into the job's progress.
ProgressCallback = Callable[..., Awaitable[None]]
JOB_TYPE_AUTO_PIPELINE = "auto_pipeline"
JOB_TYPE_BULK_CONFIRM = "bulk_confirm"
STAGE_NAMES = ("Discovery & enrichment", "Qualification", "Role classification", "Drafting")


TRAIL_LENGTH = 5


def _stage_callback(
    parent: ProgressCallback | None, stage: int, trail: list[str] | None = None
) -> ProgressCallback | None:
    """Wraps the job's progress callback so a stage's per-company ticks report as "stage N, item
    i of M" while the overall bar still counts completed stages (N-1 of 4).

    `trail` is the run's list of recent messages, shared by every stage: each new `detail` is added
    (newest last, repeats skipped) and the last few are sent along as `trail`, so the screen can
    show what has really just happened."""
    if parent is None:
        return None

    async def callback(done: int, total: int, **extra: object) -> None:
        detail = extra.get("detail")
        if trail is not None and isinstance(detail, str) and (not trail or trail[-1] != detail):
            trail.append(detail)
            del trail[:-TRAIL_LENGTH]
        if trail is not None:
            extra["trail"] = list(trail)
        await parent(
            stage - 1,
            4,
            stage=stage,
            stage_name=STAGE_NAMES[stage - 1],
            stage_done=done,
            stage_total=total,
            **extra,
        )

    return callback


async def _run_auto_pipeline(
    session: AsyncSession,
    job: Job,
    discovery_agent: CompanyDiscoveryAgentProtocol,
    domain_provider: DomainDiscoveryProvider,
    company_provider: CompanyDataProvider,
    contact_provider: ContactDataProvider,
    signal_provider: SignalDataProvider,
    qualification_generator: QualificationGenerator,
    role_relevance_generator: RoleRelevanceGenerator,
    draft_generator: DraftGenerator,
    progress_callback: ProgressCallback | None = None,
    contact_search_provider: ContactSearchProvider | None = None,
) -> dict[str, Any]:
    """Testable core of the "one prompt, the system does the rest" pipeline. Stages run in a
    fixed order; each stage's prerequisites are checked before it runs — a missing prerequisite
    (no active criteria/categories, no product specified) is recorded as
    `{"ran": False, "skipped_reason": ...}`, not a failure, so the pipeline gets as far as it
    validly can rather than aborting the whole run over one optional later stage.

    Progress is reported coarsely, one tick per stage (1 of 4 .. 4 of 4) rather than per item
    within a stage — the detailed breakdown lives in the returned result, not the progress bar."""
    payload = job.payload or {}
    settings = get_settings()
    trail: list[str] = []

    # Stage 1: discovery — always runs, this is why the job exists.
    discovery_result = await _run_market_discovery(
        session,
        job,
        discovery_agent,
        domain_provider,
        company_provider,
        contact_provider,
        signal_provider,
        progress_callback=_stage_callback(progress_callback, 1, trail),
        contact_search_provider=contact_search_provider,
    )
    stage_two = _stage_callback(progress_callback, 2, trail)
    if stage_two:
        found_count = len(discovery_result.get("company_ids") or [])
        await stage_two(
            0, found_count or 1, detail=f"Found {found_count} companies, now checking fit"
        )

    # Companies reused from the existing index belong to this run too (they used to be skipped);
    # the discovery summary lists them alongside the newly created ones.
    summary_ids = discovery_result.get("company_ids")
    if summary_ids is not None:
        company_ids = [uuid.UUID(cid) for cid in summary_ids]
    else:
        company_ids = await list_company_ids_by_source_run(
            session, job.organization_id, uuid.UUID(payload["ingestion_run_id"])
        )
    # A company a person marked not a fit takes no part in automatic work, however it got here.
    company_ids = await active_company_ids(session, job.organization_id, company_ids)

    # Stage 2: qualification.
    # Only the criteria chosen for this run apply; none chosen is fine: companies stay "not
    # checked", are ranked by offering fit, and nothing is excluded.
    run_criteria = build_run_criteria(job.organization_id, payload.get("criteria"))
    run_specs = clean_criteria(payload.get("criteria") or [])
    if run_specs:
        for found in (
            await session.execute(select(Company).where(Company.id.in_(company_ids)))
        ).scalars():
            add_company_criteria(found, run_specs)
        await session.flush()
    qual = await _run_bulk_qualification(
        session,
        job.organization_id,
        company_ids,
        qualification_generator,
        progress_callback=_stage_callback(progress_callback, 2, trail),
        criteria=run_criteria,
    )
    qualification_result: dict[str, Any] = {
        "ran": True,
        "criteria_chosen": len(run_criteria),
        **qual,
    }
    eligible_company_ids = [uuid.UUID(cid) for cid in qual["eligible_company_ids"]]
    await session.commit()  # qualification results are durable before ranking starts

    # Ranking: score every judged company, then take the best N — not the first N discovered.
    # Companies that clearly fail a hard requirement are excluded; ones that could not be
    # verified stay eligible but rank below fully-qualified ones.
    run = await session.get(IngestionRun, uuid.UUID(payload["ingestion_run_id"]))
    parsed = (run.parsed_fields if run else None) or {}
    ranked = await rank_judged_companies(
        session,
        job.organization_id,
        eligible_company_ids,
        requested_keywords=(parsed.get("industry_keywords") or {}).get("value") or [],
        requested_size=(parsed.get("employee_size_range") or {}).get("value"),
    )
    await session.commit()
    ranked_ids = [r.company_id for r in ranked if not r.excluded]
    ranking_result = {
        "ranked": len(ranked_ids),
        "top": [
            {"company_id": str(r.company_id), "score": r.score, "verdict": r.verdict}
            for r in ranked
            if not r.excluded
        ][: settings.auto_pipeline_max_companies_to_draft],
    }
    # Light fit stage: queue (never wait for) a judgment of the run's offerings per ranked company.
    # The offerings the Brief is about: the ones chosen for drafting, else the ones the searched
    # words point to. Drafting itself still uses only what was chosen.
    search_product_ids = [uuid.UUID(p) for p in (payload.get("product_ids") or [])] or (
        await offerings_for_keywords(
            session,
            job.organization_id,
            (parsed.get("industry_keywords") or {}).get("value") or [],
        )
    )
    fit_queued = await queue_run_fit(
        session,
        job.organization_id,
        uuid.UUID(payload["ingestion_run_id"]),
        ranked_ids,
        search_product_ids,
        settings.auto_pipeline_max_companies_to_draft,
    )
    await session.commit()
    ranking_result["offering_fit_queued"] = fit_queued
    # Research the offerings the run was about, so each company's Brief opens with an answer.
    area_research_queued = await queue_run_area_research(
        session,
        job.organization_id,
        uuid.UUID(payload["ingestion_run_id"]),
        ranked_ids,
        search_product_ids,
        settings.run_area_research_company_limit,
        settings.run_area_research_offering_limit,
    )
    await session.commit()
    ranking_result["area_research_queued"] = area_research_queued

    qualified_company_ids = ranked_ids
    capped = qualified_company_ids[: settings.auto_pipeline_max_companies_to_draft]
    was_capped = len(qualified_company_ids) > len(capped)
    stage_three = _stage_callback(progress_callback, 3, trail)
    if stage_three:
        if was_capped:
            message = (
                f"{len(qualified_company_ids)} companies fit; finding people at the top "
                f"{len(capped)} by score"
            )
        else:
            message = f"{len(capped)} companies fit, now finding the right people"
        await stage_three(0, len(capped) or 1, detail=message)
    contact_counts: dict[uuid.UUID, int] = {}
    company_names: dict[uuid.UUID, str] = {}
    if capped:
        company_names = {
            cid: name
            for cid, name in (
                await session.execute(
                    select(Company.id, Company.name).where(Company.id.in_(capped))
                )
            ).all()
        }
        contact_counts = {
            cid: n
            for cid, n in (
                await session.execute(
                    select(Contact.company_id, func.count())
                    .where(Contact.company_id.in_(capped))
                    .group_by(Contact.company_id)
                )
            ).all()
        }

    # Stage 3: role classification — capped set only, to bound Gemini calls on a broad prompt.
    # A company still flagged `needs_review` (unconfirmed discovery hit, listicle-shaped name,
    # etc.) is skipped here rather than classified — see `classify_and_draft_company`'s docstring
    # for why this must never be silently bypassed on the road to a customer-facing draft.
    primary_by_company: dict[uuid.UUID, list[uuid.UUID]] = {}
    # Optional focus chosen when the run was started; none means every matched role is a target.
    target_category_ids = {uuid.UUID(c) for c in (payload.get("role_category_ids") or [])}
    if not qualified_company_ids:
        role_result: dict[str, Any] = {"ran": False, "skipped_reason": "no qualified companies"}
    elif not await list_active_categories(session, job.organization_id):
        role_result = {"ran": False, "skipped_reason": "no active role categories configured"}
    else:
        classified = 0
        role_errors: list[dict[str, str]] = []
        role_skipped_needs_review: list[dict[str, str]] = []
        for position, company_id in enumerate(capped, start=1):
            role_progress = _stage_callback(progress_callback, 3, trail)
            if role_progress:
                people = contact_counts.get(company_id, 0)
                await role_progress(
                    position - 1,
                    len(capped),
                    detail=(
                        f"Finding decision-makers at {company_names.get(company_id, 'company')}"
                        f" ({position} of {len(capped)})"
                        + (f", sorting {people} people by role" if people else "")
                    ),
                )
            try:
                await run_role_relevance_check(
                    session,
                    job.organization_id,
                    company_id,
                    role_relevance_generator,
                    target_category_ids=target_category_ids,
                )
                classified += 1
                latest = await list_latest_role_relevance(session, job.organization_id, company_id)
                primary_by_company[company_id] = [
                    contact_id for contact_id, r in latest.items() if r.priority == "primary"
                ]
            except CompanyNeedsReviewError as exc:
                role_skipped_needs_review.append(
                    {"company_id": str(company_id), "reason": str(exc)}
                )
            except (CompanyNotFoundError, NoContactsError, GeminiClientError) as exc:
                role_errors.append({"company_id": str(company_id), "error": str(exc)})
        role_result = {
            "ran": True,
            "companies_classified": classified,
            "errors": role_errors,
            "skipped_needs_review": role_skipped_needs_review,
        }
    await session.commit()
    stage_four = _stage_callback(progress_callback, 4, trail)
    if stage_four:
        await stage_four(0, 1, detail="People sorted. Drafts are written when you choose someone")

    # Stage 4: drafting — only the primary-target contacts identified above. A contact still
    # flagged `needs_review` (e.g. a company that's fine but one scraped/searched contact isn't)
    # is skipped independently of the company-level gate above.
    product_ids = [uuid.UUID(p) for p in (payload.get("product_ids") or [])]
    total_primary = sum(len(v) for v in primary_by_company.values())
    if not product_ids:
        draft_result: dict[str, Any] = {"ran": False, "skipped_reason": "no product specified"}
    elif total_primary == 0:
        draft_result = {"ran": False, "skipped_reason": "no primary-target contacts identified"}
    else:
        generated = 0
        draft_errors: list[dict[str, str]] = []
        draft_skipped_needs_review: list[dict[str, str]] = []
        for company_id, contact_ids in primary_by_company.items():
            for contact_id in contact_ids:
                try:
                    await generate_draft(
                        session,
                        job.organization_id,
                        company_id,
                        contact_id,
                        product_ids,
                        DRAFT_TYPE_FIRST_TOUCH,
                        draft_generator,
                    )
                    generated += 1
                except DraftNeedsReviewError as exc:
                    draft_skipped_needs_review.append(
                        {
                            "company_id": str(company_id),
                            "contact_id": str(contact_id),
                            "reason": str(exc),
                        }
                    )
                except GeminiClientError as exc:
                    draft_errors.append({"contact_id": str(contact_id), "error": str(exc)})
        draft_result = {
            "ran": True,
            "drafts_generated": generated,
            "errors": draft_errors,
            "skipped_needs_review": draft_skipped_needs_review,
        }
    if progress_callback:
        await progress_callback(4, 4, stage=4, stage_name=STAGE_NAMES[3], detail="Done")

    return {
        "discovery": discovery_result,
        "qualification": qualification_result,
        "ranking": ranking_result,
        "role_classification": role_result,
        "drafting": draft_result,
        "capped": was_capped,
        "needs_review_summary": {
            "companies_skipped_at_role_classification": len(
                role_result.get("skipped_needs_review", [])
            ),
            "contacts_skipped_at_drafting": len(draft_result.get("skipped_needs_review", [])),
        },
    }


async def classify_and_draft_company(
    session: AsyncSession,
    organization_id: uuid.UUID,
    company_id: uuid.UUID,
    role_relevance_generator: RoleRelevanceGenerator,
    draft_generator: DraftGenerator,
    product_ids: list[uuid.UUID],
) -> dict[str, Any]:
    """The single-company equivalent of stages 3+4 above — classify roles, then draft to any
    primary-target contacts found. This is what `POST /companies/{id}/confirm` calls right after
    clearing `needs_review`, so confirming a company also resumes its pipeline in one action
    rather than leaving a rep to separately trigger classification and drafting by hand. Never
    raises — every expected outcome (skip, error) is returned as data, same convention as
    `_run_auto_pipeline`'s stage results."""
    try:
        await run_role_relevance_check(
            session, organization_id, company_id, role_relevance_generator
        )
    except CompanyNeedsReviewError as exc:
        return {
            "role_classification": {"ran": False, "skipped_reason": str(exc)},
            "drafting": {"ran": False, "skipped_reason": "role classification did not run"},
        }
    except (CompanyNotFoundError, NoContactsError, GeminiClientError) as exc:
        return {
            "role_classification": {"ran": False, "error": str(exc)},
            "drafting": {"ran": False, "skipped_reason": "role classification did not run"},
        }

    latest = await list_latest_role_relevance(session, organization_id, company_id)
    primary_contact_ids = [
        contact_id for contact_id, r in latest.items() if r.priority == "primary"
    ]
    role_result: dict[str, Any] = {"ran": True, "primary_contacts": len(primary_contact_ids)}

    if not product_ids:
        return {
            "role_classification": role_result,
            "drafting": {"ran": False, "skipped_reason": "no product specified"},
        }
    if not primary_contact_ids:
        return {
            "role_classification": role_result,
            "drafting": {"ran": False, "skipped_reason": "no primary-target contacts identified"},
        }

    generated = 0
    draft_errors: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for contact_id in primary_contact_ids:
        try:
            await generate_draft(
                session,
                organization_id,
                company_id,
                contact_id,
                product_ids,
                DRAFT_TYPE_FIRST_TOUCH,
                draft_generator,
            )
            generated += 1
        except DraftNeedsReviewError as exc:
            skipped.append({"contact_id": str(contact_id), "reason": str(exc)})
        except GeminiClientError as exc:
            draft_errors.append({"contact_id": str(contact_id), "error": str(exc)})
    return {
        "role_classification": role_result,
        "drafting": {
            "ran": True,
            "drafts_generated": generated,
            "errors": draft_errors,
            "skipped_needs_review": skipped,
        },
    }


async def _run_bulk_confirm(
    session: AsyncSession,
    organization_id: uuid.UUID,
    company_ids: list[uuid.UUID],
    contact_ids: list[uuid.UUID],
    product_ids: list[uuid.UUID],
    role_relevance_generator: RoleRelevanceGenerator,
    draft_generator: DraftGenerator,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Clears `needs_review` on every given company/contact id in one batch — the bulk
    equivalent of the one-at-a-time `POST /companies/{id}/confirm` and
    `POST /contacts/{id}/confirm`, for a rep clearing an entire Needs Review queue rather than
    clicking through each entry. Each confirmed company also resumes role classification/drafting
    exactly like the single-company confirm endpoint does (`classify_and_draft_company`), so
    bulk-confirming has the same downstream effect as confirming one company at a time — just
    batched. Confirming a contact only clears its flag (matching the single-contact endpoint,
    which doesn't draft on its own since drafting is triggered per-contact independently)."""
    total = (len(company_ids) + len(contact_ids)) or 1
    done = 0
    companies_confirmed = 0
    company_results: list[dict[str, Any]] = []
    for company_id in company_ids:
        company = await confirm_company(session, organization_id, company_id)
        if company is None:
            company_results.append({"company_id": str(company_id), "error": "company not found"})
        else:
            companies_confirmed += 1
            resumed = await classify_and_draft_company(
                session,
                organization_id,
                company_id,
                role_relevance_generator,
                draft_generator,
                product_ids,
            )
            company_results.append({"company_id": str(company_id), **resumed})
        done += 1
        if progress_callback:
            await progress_callback(done, total)

    contacts_confirmed = 0
    for contact_id in contact_ids:
        contact = await confirm_contact(session, organization_id, contact_id)
        if contact is not None:
            contacts_confirmed += 1
        done += 1
        if progress_callback:
            await progress_callback(done, total)

    return {
        "companies_confirmed": companies_confirmed,
        "contacts_confirmed": contacts_confirmed,
        "company_results": company_results,
    }


async def run_bulk_confirm_job(
    session: AsyncSession, job: Job, progress_callback: ProgressCallback | None = None
) -> dict[str, Any]:
    """Handler registered with the job worker — unpacks `job.payload` (`company_ids`,
    `contact_ids`, optional `product_ids`) and delegates to `_run_bulk_confirm`."""
    settings = get_settings()
    payload = job.payload or {}
    company_ids = [uuid.UUID(cid) for cid in payload.get("company_ids", [])]
    contact_ids = [uuid.UUID(cid) for cid in payload.get("contact_ids", [])]
    product_ids = [uuid.UUID(p) for p in (payload.get("product_ids") or [])]
    return await _run_bulk_confirm(
        session,
        job.organization_id,
        company_ids,
        contact_ids,
        product_ids,
        GeminiRoleRelevanceGenerator(settings),
        GeminiDraftGenerator(settings),
        progress_callback,
    )


async def run_auto_pipeline_job(
    session: AsyncSession, job: Job, progress_callback: ProgressCallback | None = None
) -> dict[str, Any]:
    """Handler registered with the job worker — builds every real provider/generator this
    pipeline touches and delegates to `_run_auto_pipeline`."""
    settings = get_settings()
    discovery_agent = get_default_discovery_agent(settings)
    scraper = WebsiteScraperProvider(settings)
    providers = build_company_providers(settings, scraper)
    domain_provider = SerperSearchProvider(settings)
    # Same search-based contact discovery the standalone discovery job already uses — without it
    # a company whose site lists no decision-makers ends up with no contact to draft to.
    contact_search_provider = SerperContactSearchProvider(settings, domain_provider)
    try:
        return await _run_auto_pipeline(
            session,
            job,
            discovery_agent,
            domain_provider,
            providers.company,
            scraper,
            providers.signals,
            GeminiQualificationGenerator(settings),
            GeminiRoleRelevanceGenerator(settings),
            GeminiDraftGenerator(settings),
            progress_callback,
            contact_search_provider,
        )
    finally:
        await scraper.aclose()
