"""Read-only dashboard queries. Nothing here writes: every function only SELECTs, so loading the
dashboard can never change existing data (a test asserts every table's row count is unchanged).

Two scopes share one code path so the numbers always agree:
  - one search: the companies that search covers (created by it, or reused from the index and
    listed in its summary — the same membership rule the results list uses);
  - all searches: the union of those sets over the chosen period, de-duplicated by company id, so a
    company reused by two searches is counted once.

Drafts carry no run id, so a search's drafts are the drafts of its companies. JSON is read in Python
(not with database JSON operators) so everything also runs on the SQLite test database."""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.companies.models import ENRICHMENT_STATUS_FAILED, Company
from app.modules.contacts.models import Contact
from app.modules.dashboard.schemas import (
    ActivityEvent,
    AttentionItem,
    FunnelStage,
    Health,
    Kpis,
    Overview,
    RequirementResult,
    RunHeader,
    RunList,
    RunStats,
    SearchOption,
    Setup,
    TopCompany,
)
from app.modules.draft.models import (
    DRAFT_STATUS_DISCARDED,
    DRAFT_STATUS_DRAFT,
    DRAFT_STATUS_SENT,
    Draft,
)
from app.modules.ingestion.models import (
    SOURCE_TYPE_MARKET_DISCOVERY,
    STATUS_AWAITING_CONFIRMATION,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    IngestionRun,
)
from app.modules.jobs.service import find_job_for_run
from app.modules.outreach.models import OutreachActivity
from app.modules.products.models import Product
from app.modules.qualification.evidence import PASS, status_for_verdict
from app.modules.qualification.models import QualificationCriterion, QualificationResult
from app.modules.role_relevance.models import RoleCategory, RoleRelevanceResult

JOB_TYPE_AUTO_PIPELINE = "auto_pipeline"  # mirrors orchestrator.service (avoids importing it)
PERIODS = {"7d": 7, "30d": 30, "all": None}
MAX_SEARCH_OPTIONS = 30
ACTIVITY_LIMIT = 10
TOP_COMPANIES = 5

VERDICT_QUALIFIED = "qualified"
VERDICT_NEEDS_LOOK = "could_not_determine"
VERDICT_REJECTED = "not_qualified"


def _aware(value: datetime) -> datetime:
    # SQLite does not round-trip tzinfo; treat naive values as UTC.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


# -- pure text helpers -------------------------------------------------------------------------


def run_title(run: IngestionRun) -> str:
    text = " ".join((run.raw_input or "").split())
    if not text:
        return "Untitled search"
    return text if len(text) <= 140 else text[:137] + "..."


def run_summary_line(run: IngestionRun) -> str:
    parsed = run.parsed_fields or {}
    parts: list[str] = []
    keywords = (parsed.get("industry_keywords") or {}).get("value") or []
    if keywords:
        parts.append(", ".join(str(k) for k in keywords))
    location = (parsed.get("location") or {}).get("value")
    if location:
        parts.append(str(location))
    size = (parsed.get("employee_size_range") or {}).get("value")
    if size:
        parts.append(f"{size} employees")
    return " · ".join(parts)


def build_headline(
    scope: str,
    searches: int,
    kpis: Kpis,
    ready: int,
    run_status: str | None,
    run_error: str | None,
    checked_so_far: int = 0,
) -> str:
    """One plain sentence that says what happened. Built from the same numbers as the charts, so
    the text and the visuals cannot disagree."""
    if scope == "search" and run_status in (STATUS_PENDING, STATUS_RUNNING):
        return (
            "This search is still running — "
            f"{plural(kpis.companies, 'company', 'companies')} found so far."
            if checked_so_far == 0
            else f"This search is still running — {checked_so_far} of "
            f"{plural(kpis.companies, 'company', 'companies')} checked so far."
        )
    if scope == "search" and run_status == STATUS_FAILED:
        return f"This search did not finish{': ' + run_error if run_error else '.'}"
    if searches == 0:
        return "No searches yet — describe a market above to find your first prospects."
    subject = "This search" if scope == "search" else f"{plural(searches, 'search', 'searches')}"
    found = plural(kpis.companies, "company", "companies")
    parts = [f"{ready} {'is' if ready == 1 else 'are'} ready for you to contact"]
    if kpis.rejected:
        was = "was" if kpis.rejected == 1 else "were"
        parts.append(f"{kpis.rejected} {was} rejected as a poor fit")
    if kpis.needs_closer_look:
        parts.append(f"{kpis.needs_closer_look} need a closer look")
    verb = "found" if scope == "search" else "found"
    sentence = f"{subject} {verb} {found} — " + ", ".join(parts) + "."
    drafts = kpis.drafts_to_review + kpis.drafts_sent
    if drafts:
        sentence += f" {plural(drafts, 'draft')} written."
    return sentence


# -- loading -----------------------------------------------------------------------------------


async def _runs(
    session: AsyncSession, organization_id: uuid.UUID
) -> list[IngestionRun]:
    stmt = (
        select(IngestionRun)
        .where(
            IngestionRun.organization_id == organization_id,
            IngestionRun.source_type == SOURCE_TYPE_MARKET_DISCOVERY,
            IngestionRun.status != STATUS_AWAITING_CONFIRMATION,
        )
        .order_by(IngestionRun.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def _company_ids_for_run(
    session: AsyncSession, organization_id: uuid.UUID, run: IngestionRun
) -> set[uuid.UUID]:
    ids = {uuid.UUID(cid) for cid in (run.summary or {}).get("company_ids", [])}
    created = await session.execute(
        select(Company.id).where(
            Company.organization_id == organization_id,
            Company.source_ingestion_run_id == run.id,
        )
    )
    ids.update(created.scalars().all())
    return ids


@dataclass
class _Scope:
    runs: list[IngestionRun]
    company_ids: set[uuid.UUID]
    single: bool


@dataclass
class _Data:
    companies: dict[uuid.UUID, Company] = field(default_factory=dict)
    latest: dict[uuid.UUID, QualificationResult] = field(default_factory=dict)
    contacts: list[Contact] = field(default_factory=list)
    primary_contacts: set[uuid.UUID] = field(default_factory=set)
    drafts: list[Draft] = field(default_factory=list)

    def verdict(self, company_id: uuid.UUID) -> str | None:
        result = self.latest.get(company_id)
        return result.overall_verdict if result else None

    def live_drafts_by_company(self) -> dict[uuid.UUID, int]:
        counts: dict[uuid.UUID, int] = defaultdict(int)
        for draft in self.drafts:
            if draft.status != DRAFT_STATUS_DISCARDED:
                counts[draft.company_id] += 1
        return counts


async def _load(session: AsyncSession, ids: set[uuid.UUID]) -> _Data:
    data = _Data()
    if not ids:
        return data
    id_list = list(ids)
    for company in (
        await session.execute(select(Company).where(Company.id.in_(id_list)))
    ).scalars():
        data.companies[company.id] = company
    for result in (
        await session.execute(
            select(QualificationResult)
            .where(QualificationResult.company_id.in_(id_list))
            .order_by(QualificationResult.created_at.asc())
        )
    ).scalars():
        data.latest[result.company_id] = result  # newest wins
    data.contacts = list(
        (await session.execute(select(Contact).where(Contact.company_id.in_(id_list)))).scalars()
    )
    latest_role: dict[uuid.UUID, RoleRelevanceResult] = {}
    for role in (
        await session.execute(
            select(RoleRelevanceResult)
            .where(RoleRelevanceResult.company_id.in_(id_list))
            .order_by(RoleRelevanceResult.created_at.asc())
        )
    ).scalars():
        latest_role[role.contact_id] = role
    data.primary_contacts = {cid for cid, r in latest_role.items() if r.priority == "primary"}
    data.drafts = list(
        (await session.execute(select(Draft).where(Draft.company_id.in_(id_list)))).scalars()
    )
    return data


# -- aggregation -------------------------------------------------------------------------------


def _kpis(runs: list[IngestionRun], data: _Data) -> Kpis:
    counts: dict[str, int] = defaultdict(int)
    for company_id in data.companies:
        counts[data.verdict(company_id) or "none"] += 1
    likely_cutoff = get_settings().contact_confidence_likely
    credits = sum(
        int(((r.summary or {}).get("context_dev") or {}).get("credits_used") or 0) for r in runs
    )
    return Kpis(
        searches=len(runs),
        companies=len(data.companies),
        fit=counts[VERDICT_QUALIFIED],
        needs_closer_look=counts[VERDICT_NEEDS_LOOK],
        rejected=counts[VERDICT_REJECTED],
        contacts=len(data.contacts),
        likely_decision_makers=sum(
            1 for c in data.contacts if (c.confidence or 0.0) >= likely_cutoff
        ),
        drafts_to_review=sum(1 for d in data.drafts if d.status == DRAFT_STATUS_DRAFT),
        drafts_sent=sum(1 for d in data.drafts if d.status == DRAFT_STATUS_SENT),
        credits_used=credits,
    )


def _funnel(data: _Data) -> list[FunnelStage]:
    live = data.live_drafts_by_company()
    contact_companies = {c.company_id for c in data.contacts}
    checked = [cid for cid in data.companies if cid in data.latest]
    worth = [
        cid for cid in checked if data.verdict(cid) in (VERDICT_QUALIFIED, VERDICT_NEEDS_LOOK)
    ]
    with_contact = [cid for cid in worth if cid in contact_companies]
    with_draft = [cid for cid in worth if live.get(cid)]
    stages = [
        ("found", "Found", len(data.companies)),
        ("checked", "Checked against your requirements", len(checked)),
        ("worth_pursuing", "Worth pursuing", len(worth)),
        ("have_contact", "Have a contact", len(with_contact)),
        ("draft_written", "Draft written", len(with_draft)),
    ]
    out: list[FunnelStage] = []
    previous: int | None = None
    for key, label, count in stages:
        percent = round(count * 100 / previous) if previous else None
        out.append(FunnelStage(key=key, label=label, count=count, percent_of_previous=percent))
        previous = count
    return out


def _requirements(data: _Data) -> list[RequirementResult]:
    live = data.live_drafts_by_company()
    table: dict[tuple[str, str, bool], dict[str, int]] = {}
    for company_id in data.companies:
        result = data.latest.get(company_id)
        if result is None:
            continue
        for entry in result.criteria_results or []:
            name = str(entry.get("criterion_name") or "")
            key = (name, str(entry.get("scope") or "org"), bool(entry.get("is_disqualifying")))
            row = table.setdefault(key, {"meets": 0, "unknown": 0, "fails": 0, "drafts": 0})
            status = str(entry.get("status") or status_for_verdict(str(entry.get("verdict"))))
            if status == PASS:
                row["meets"] += 1
                if live.get(company_id):
                    row["drafts"] += 1
            elif status == "FAIL":
                row["fails"] += 1
            else:
                row["unknown"] += 1
    items = [
        RequirementResult(
            name=name,
            scope=scope,
            hard=hard,
            meets=row["meets"],
            couldnt_verify=row["unknown"],
            doesnt_meet=row["fails"],
            drafts_for_meeting=row["drafts"],
        )
        for (name, scope, hard), row in table.items()
    ]
    return sorted(items, key=lambda r: (not r.hard, r.scope != "run", r.name))


def _top_companies(data: _Data) -> list[TopCompany]:
    ranked = [
        (cid, r)
        for cid, r in data.latest.items()
        if cid in data.companies and r.overall_verdict != VERDICT_REJECTED
    ]
    ranked.sort(key=lambda item: -(item[1].priority_score or 0.0))
    top: list[TopCompany] = []
    for cid, result in ranked[:TOP_COMPANIES]:
        company = data.companies[cid]
        reason: str | None = None
        if result.overall_verdict == VERDICT_NEEDS_LOOK:
            reason = "Needs a closer look — a requirement could not be verified"
        else:
            for entry in result.criteria_results or []:
                if entry.get("status") == PASS and entry.get("reasoning"):
                    reason = str(entry["reasoning"])
                    break
        top.append(
            TopCompany(
                company_id=cid,
                name=company.name,
                domain=company.domain,
                score=result.priority_score,
                verdict=result.overall_verdict,
                reason=reason,
            )
        )
    return top


def _ready_company_ids(data: _Data) -> set[uuid.UUID]:
    """Worth pursuing, has a likely decision-maker, nothing drafted yet: the rep's next move."""
    live = data.live_drafts_by_company()
    with_primary = {c.company_id for c in data.contacts if c.id in data.primary_contacts}
    return {
        cid
        for cid in with_primary
        if cid in data.companies
        and data.verdict(cid) in (VERDICT_QUALIFIED, VERDICT_NEEDS_LOOK)
        and not live.get(cid)
    }


async def _health(
    session: AsyncSession, runs: list[IngestionRun], data: _Data, pipeline: dict[str, Any] | None
) -> Health:
    summaries = [r.summary or {} for r in runs]
    cd: list[dict[str, Any]] = [
        s["context_dev"] for s in summaries if isinstance(s.get("context_dev"), dict)
    ]
    errors: dict[str, int] = defaultdict(int)
    for summary in summaries:
        for branch, n in ((summary.get("enrichment") or {}).get("branch_errors") or {}).items():
            errors[str(branch)] += int(n)
    notes: list[str] = []
    for stage in (pipeline or {}).values():
        if isinstance(stage, dict) and stage.get("skipped_reason"):
            notes.append(str(stage["skipped_reason"]))
    if (pipeline or {}).get("capped"):
        notes.append(
            "More companies qualified than the automatic limit; the rest were not classified."
        )
    return Health(
        credits_used=sum(int(c.get("credits_used") or 0) for c in cd),
        credit_ceiling=max(
            (int(c["credit_ceiling"]) for c in cd if c.get("credit_ceiling")), default=None
        ),
        budget_exhausted=any(bool(c.get("budget_exhausted")) for c in cd),
        companies_needing_no_paid_lookup=sum(int(c.get("skipped_sufficient") or 0) for c in cd),
        enrichment_failed=sum(
            1 for c in data.companies.values() if c.enrichment_status == ENRICHMENT_STATUS_FAILED
        ),
        provider_errors=dict(errors),
        notes=notes,
    )


async def _setup(session: AsyncSession, organization_id: uuid.UUID) -> Setup:
    async def count(stmt: Any) -> int:
        return int((await session.execute(stmt)).scalar_one())

    return Setup(
        products=await count(
            select(func.count())
            .select_from(Product)
            .where(Product.organization_id == organization_id)
        ),
        active_criteria=await count(
            select(func.count())
            .select_from(QualificationCriterion)
            .where(
                QualificationCriterion.organization_id == organization_id,
                QualificationCriterion.is_active.is_(True),
            )
        ),
        active_role_categories=await count(
            select(func.count())
            .select_from(RoleCategory)
            .where(
                RoleCategory.organization_id == organization_id,
                RoleCategory.is_active.is_(True),
            )
        ),
    )


async def _activity(
    session: AsyncSession, runs: list[IngestionRun], data: _Data
) -> list[ActivityEvent]:
    events: list[ActivityEvent] = []
    for run in runs[:ACTIVITY_LIMIT]:
        title = run_title(run)
        if run.status == STATUS_FAILED:
            events.append(
                ActivityEvent(
                    at=_aware(run.created_at),
                    kind="failure",
                    text=f"Search failed: {title}",
                    run_id=run.id,
                )
            )
        else:
            word = "finished" if run.status == STATUS_DONE else "started"
            events.append(
                ActivityEvent(
                    at=_aware(run.created_at),
                    kind="search",
                    text=f"Search {word}: {title}",
                    run_id=run.id,
                )
            )
    contacts = {c.id: c for c in data.contacts}
    for draft in data.drafts:
        contact = contacts.get(draft.contact_id)
        company = data.companies.get(draft.company_id)
        who = contact.full_name if contact and contact.full_name else "a contact"
        where = f" at {company.name}" if company else ""
        events.append(
            ActivityEvent(
                at=_aware(draft.created_at),
                kind="draft",
                text=f"Draft written for {who}{where}",
                company_id=draft.company_id,
            )
        )
    if contacts:
        rows = await session.execute(
            select(OutreachActivity).where(OutreachActivity.contact_id.in_(list(contacts)))
        )
        for activity in rows.scalars():
            contact = contacts[activity.contact_id]
            company = data.companies.get(contact.company_id)
            sent = activity.activity_type == "sent"
            verb = "Message sent to" if sent else "Response received from"
            events.append(
                ActivityEvent(
                    at=_aware(activity.created_at),
                    kind="outreach",
                    text=f"{verb} {contact.full_name or 'a contact'}"
                    + (f" at {company.name}" if company else ""),
                    company_id=contact.company_id,
                )
            )
    events.sort(key=lambda e: e.at, reverse=True)
    return events[:ACTIVITY_LIMIT]


def _attention(
    runs: list[IngestionRun], data: _Data, ready: set[uuid.UUID], now: datetime
) -> list[AttentionItem]:
    # Everything links to the most recent search in scope; its results list is where the rep acts.
    target = f"/?search={runs[0].id}" if runs else "/market-discovery"
    due = sum(
        1
        for c in data.contacts
        if c.next_follow_up_at is not None and _aware(c.next_follow_up_at) <= now
    )
    problem_runs = [r for r in runs if r.status in (STATUS_RUNNING, STATUS_PENDING, STATUS_FAILED)]
    needs_look = sum(1 for cid in data.companies if data.verdict(cid) == VERDICT_NEEDS_LOOK)
    items = [
        AttentionItem(
            key="ready_to_contact",
            label="Companies ready — pick a person and write the draft",
            count=len(ready),
            href=target,
        ),
        AttentionItem(
            key="drafts_to_review",
            label="Drafts waiting for your review",
            count=sum(1 for d in data.drafts if d.status == DRAFT_STATUS_DRAFT),
            href="/drafts?status=draft",
        ),
        AttentionItem(key="follow_ups_due", label="Follow-ups due", count=due, href="/follow-ups"),
        AttentionItem(
            key="needs_closer_look",
            label="Companies that need a closer look",
            count=needs_look,
            href=target,
        ),
        AttentionItem(
            key="searches",
            label="Searches running or failed",
            count=len(problem_runs),
            href=f"/?search={problem_runs[0].id}" if problem_runs else target,
        ),
    ]
    return items


def _run_stats(run: IngestionRun, data: _Data) -> RunStats:
    k = _kpis([run], data)
    scores = [
        r.priority_score for r in data.latest.values() if r.priority_score is not None
    ]
    credits = ((run.summary or {}).get("context_dev") or {}).get("credits_used")
    return RunStats(
        run_id=run.id,
        title=run_title(run),
        summary=run_summary_line(run),
        status=run.status,
        created_at=_aware(run.created_at),
        error=run.error,
        companies=k.companies,
        fit=k.fit,
        needs_closer_look=k.needs_closer_look,
        rejected=k.rejected,
        contacts=k.contacts,
        drafts=k.drafts_to_review + k.drafts_sent,
        top_score=max(scores) if scores else None,
        credits_used=int(credits) if credits is not None else None,
    )


# -- public API --------------------------------------------------------------------------------


async def _scope(
    session: AsyncSession, organization_id: uuid.UUID, run_id: uuid.UUID | None, period: str
) -> _Scope | None:
    runs = await _runs(session, organization_id)
    if run_id is not None:
        chosen = [r for r in runs if r.id == run_id]
        if not chosen:
            return None
        single_ids = await _company_ids_for_run(session, organization_id, chosen[0])
        return _Scope(chosen, single_ids, True)
    days = PERIODS.get(period)
    if days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        runs = [r for r in runs if _aware(r.created_at) >= cutoff]
    ids: set[uuid.UUID] = set()
    for run in runs:
        ids |= await _company_ids_for_run(session, organization_id, run)
    return _Scope(runs, ids, False)


async def build_overview(
    session: AsyncSession,
    organization_id: uuid.UUID,
    run_id: uuid.UUID | None = None,
    period: str = "all",
) -> Overview | None:
    """None when `run_id` is given but no such search exists."""
    period = period if period in PERIODS else "all"
    scope = await _scope(session, organization_id, run_id, period)
    if scope is None:
        return None
    data = await _load(session, scope.company_ids)
    kpis = _kpis(scope.runs, data)
    ready = _ready_company_ids(data)

    run_header: RunHeader | None = None
    pipeline: dict[str, Any] | None = None
    progress: dict[str, Any] | None = None
    run_status: str | None = None
    run_error: str | None = None
    checked_so_far = 0
    if scope.single:
        run = scope.runs[0]
        run_status, run_error = run.status, run.error
        job = await find_job_for_run(session, organization_id, JOB_TYPE_AUTO_PIPELINE, run.id)
        if job is not None:
            pipeline = dict(job.result) if job.result else None
            progress = dict(job.progress) if job.progress else None
        checked_so_far = len(data.latest)
        run_header = RunHeader(
            run_id=run.id,
            title=run_title(run),
            summary=run_summary_line(run),
            status=run.status,
            created_at=_aware(run.created_at),
            error=run.error,
            data_source=(run.summary or {}).get("company_data_source"),
            pipeline=pipeline,
            progress=progress,
        )

    all_runs = await _runs(session, organization_id)
    return Overview(
        scope="search" if scope.single else "all",
        period=period,
        headline=build_headline(
            "search" if scope.single else "all",
            len(scope.runs),
            kpis,
            len(ready),
            run_status,
            run_error,
            checked_so_far,
        ),
        kpis=kpis,
        funnel=_funnel(data),
        requirements=_requirements(data),
        top_companies=_top_companies(data),
        attention=_attention(scope.runs, data, ready, datetime.now(UTC)),
        activity=await _activity(session, scope.runs, data),
        health=await _health(session, scope.runs, data, pipeline),
        setup=await _setup(session, organization_id),
        run=run_header,
        searches=[
            SearchOption(run_id=r.id, label=run_title(r), created_at=_aware(r.created_at))
            for r in all_runs[:MAX_SEARCH_OPTIONS]
        ],
    )


async def list_run_stats(
    session: AsyncSession,
    organization_id: uuid.UUID,
    limit: int = 10,
    offset: int = 0,
    period: str = "all",
) -> RunList:
    runs = await _runs(session, organization_id)
    days = PERIODS.get(period if period in PERIODS else "all")
    if days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        runs = [r for r in runs if _aware(r.created_at) >= cutoff]
    page = runs[offset : offset + limit]
    items: list[RunStats] = []
    for run in page:
        ids = await _company_ids_for_run(session, organization_id, run)
        items.append(_run_stats(run, await _load(session, ids)))
    return RunList(items=items, total=len(runs), limit=limit, offset=offset)
