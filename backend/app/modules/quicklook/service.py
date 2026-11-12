"""Quick Look: type a company name, get a short answer. Resolve the name to a website (asking when
it is ambiguous), read the homepage and a few search results, ask the model once, and keep the
answer as a snapshot. Nothing is added to the companies list until the person saves it.

Besides the homepage and search results, a look-up reads recent news and open jobs and searches
for the company's work in the areas we sell in (see `research.py`), so the answer says what they
are working on, not only what their website says."""

import re
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from bs4 import BeautifulSoup
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import (
    ENRICHMENT_STATUS_NEVER_ENRICHED,
    Company,
)
from app.modules.companies.service import get_or_create_company, normalize_domain
from app.modules.enrichment.providers.base import FetchedPage
from app.modules.enrichment.service import start_company_scrape
from app.modules.enrichment.signals import looks_blocked
from app.modules.llm.structured import StructuredLLM
from app.modules.opportunity.discovery import offering_areas
from app.modules.opportunity.research.types import ResearchSources
from app.modules.products.models import STATUS_ACTIVE, Product
from app.modules.qualification.service import add_company_criteria
from app.modules.quicklook.models import CompanySnapshot
from app.modules.quicklook.prompts import PROMPT_VERSION
from app.modules.quicklook.research import gather_research
from app.modules.quicklook.resolve import Candidate, build_candidates, name_tokens, pick
from app.modules.quicklook.snapshot import (
    KIND_SEARCH,
    KIND_SITE,
    Evidence,
    OfferingRef,
    build_summary,
    offerings_fingerprint,
)

SNAPSHOT_MAX_AGE = timedelta(days=7)
SEARCH_RESULTS = 10
PAGE_CHARS = 3000
SNIPPET_EVIDENCE = 5
FOCUS_RESULTS = 5
_ABOUT_PATHS = ("/about", "/about-us", "/company")
_AREA_WORD = re.compile(r"[a-z]{4,}")

STATUS_READY = "ready"
STATUS_NEEDS_CHOICE = "needs_choice"
STATUS_NOT_FOUND = "not_found"


class Searcher(Protocol):
    async def search_raw(self, query: str, num: int) -> list[dict[str, str]]: ...


class PageFetcher(Protocol):
    async def fetch_page(self, domain: str, path: str) -> FetchedPage | None: ...


@dataclass
class LookupOutcome:
    status: str
    snapshot: CompanySnapshot | None = None
    cached: bool = False
    candidates: list[Candidate] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class SnapshotNotFoundError(LookupError):
    pass


async def _offerings(session: AsyncSession, organization_id: uuid.UUID) -> list[OfferingRef]:
    products = (
        (
            await session.execute(
                select(Product)
                .where(Product.organization_id == organization_id, Product.status == STATUS_ACTIVE)
                .order_by(Product.name)
            )
        )
        .scalars()
        .all()
    )
    return [
        OfferingRef(f"O{i}", str(p.id), p.name, (p.description or "").strip())
        for i, p in enumerate(products, start=1)
    ]


def _area_words(offerings: list[OfferingRef]) -> set[str]:
    """Words from our offerings' names and descriptions, used to prefer the search result that is
    about what we sell when several companies share a name."""
    text = " ".join(f"{o.name} {o.description}" for o in offerings).lower()
    return set(_AREA_WORD.findall(text))


def page_text(html: str, limit: int = PAGE_CHARS) -> str:
    """The readable text of a page: title, description and the start of the body."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "svg"]):
        tag.decompose()
    parts: list[str] = []
    if soup.title and soup.title.string:
        parts.append(soup.title.string.strip())
    meta = soup.find("meta", attrs={"name": "description"})
    content = meta.get("content") if meta else None
    if isinstance(content, str) and content.strip():
        parts.append(content.strip())
    parts.append(" ".join(soup.get_text(" ").split()))
    return " ".join(p for p in parts if p)[:limit]


async def _gather_evidence(
    fetcher: PageFetcher,
    searcher_results: list[dict[str, str]],
    name: str,
    domain: str,
) -> tuple[list[Evidence], list[str]]:
    """The homepage (and an about page) and the search snippets about the company, plus a note
    when the site could not be used: a block or error page is never treated as what the company
    says about itself."""
    evidence: list[Evidence] = []
    blocked = False
    for path in ("/", *_ABOUT_PATHS):
        if len(evidence) >= 2:
            break
        try:
            page = await fetcher.fetch_page(domain, path)
        except Exception:  # noqa: BLE001 - an unreadable page just means less evidence
            page = None
        if page is not None:
            text = page_text(page.text)
            if looks_blocked(text):
                blocked = True
            elif text:
                evidence.append(Evidence("", page.url, KIND_SITE, text))
    tokens = name_tokens(name) or [domain.split(".")[0]]
    for item in searcher_results:
        if len([e for e in evidence if e.kind == KIND_SEARCH]) >= SNIPPET_EVIDENCE:
            break
        snippet = (item.get("snippet") or "").strip()
        text = f"{item.get('title') or ''}. {snippet}".strip(". ")
        if snippet and any(t in text.lower() for t in tokens) and not looks_blocked(text):
            evidence.append(
                Evidence("", item.get("link") or domain, KIND_SEARCH, text, item.get("date"))
            )
    notes: list[str] = []
    if blocked and not any(e.kind == KIND_SITE for e in evidence):
        notes.append(
            "Their website blocks automated reading, so this comes from search results and news."
        )
    elif not any(e.kind == KIND_SITE for e in evidence):
        notes.append("Their website could not be read, so this comes from search results only.")
    return evidence, notes


def _label(evidence: list[Evidence]) -> list[Evidence]:
    return [replace(e, label=f"E{i}") for i, e in enumerate(evidence, start=1)]


async def _add_focus_evidence(
    searcher: Searcher, evidence: list[Evidence], name: str, focus: str
) -> list[Evidence]:
    """Search results about the company and the focus area, kept as search evidence: they can
    support a "maybe" but never a "yes" by themselves. A failed search just means less evidence."""
    try:
        results = await searcher.search_raw(f"{name} {focus}", FOCUS_RESULTS)
    except Exception:  # noqa: BLE001 - extra evidence is best-effort
        return evidence
    extra = list(evidence)
    for item in results:
        snippet = (item.get("snippet") or "").strip()
        if not snippet:
            continue
        text = f"{item.get('title') or ''}. {snippet}".strip(". ")
        extra.append(Evidence(f"E{len(extra) + 1}", item.get("link") or name, KIND_SEARCH, text))
    return extra


async def _find_snapshot(
    session: AsyncSession, organization_id: uuid.UUID, domain: str
) -> CompanySnapshot | None:
    return (
        await session.execute(
            select(CompanySnapshot).where(
                CompanySnapshot.organization_id == organization_id,
                CompanySnapshot.domain == domain,
            )
        )
    ).scalar_one_or_none()


def _is_fresh(snapshot: CompanySnapshot, fingerprint: str) -> bool:
    updated = snapshot.updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    return snapshot.offerings_hash == fingerprint and datetime.now(UTC) - updated < SNAPSHOT_MAX_AGE


async def existing_company_id(
    session: AsyncSession, organization_id: uuid.UUID, domain: str
) -> uuid.UUID | None:
    return (
        await session.execute(
            select(Company.id).where(
                Company.organization_id == organization_id,
                func.lower(Company.domain) == domain,
            )
        )
    ).scalar_one_or_none()


async def existing_company_dismissal(
    session: AsyncSession, organization_id: uuid.UUID, domain: str
) -> str | None:
    """The reason a person gave when they marked this website's company not a fit, or None when
    there is no such company or it was not dismissed."""
    return (
        await session.execute(
            select(Company.dismissed_reason).where(
                Company.organization_id == organization_id,
                func.lower(Company.domain) == domain,
                Company.dismissed_at.is_not(None),
            )
        )
    ).scalar_one_or_none()


async def snapshot_note_for_domain(
    session: AsyncSession, organization_id: uuid.UUID, domain: str
) -> dict[str, object] | None:
    """The call and reason Quick Check gave for this website, if it was ever looked up."""
    snapshot = await _find_snapshot(session, organization_id, domain.lower())
    if snapshot is None:
        return None
    summary = snapshot.summary or {}
    if not summary.get("call"):
        return None
    return {
        "call": summary["call"],
        "call_reason": summary.get("call_reason") or "",
        "relevance": summary.get("relevance"),
        "updated_at": snapshot.updated_at,
    }


async def look_up(
    session: AsyncSession,
    organization_id: uuid.UUID,
    searcher: Searcher,
    fetcher: PageFetcher,
    llm: StructuredLLM,
    denylist: list[str],
    name: str | None,
    domain: str | None,
    avoid: set[str] | None = None,
    refresh: bool = False,
    always_ask: bool = False,
    focus: str | None = None,
    criteria: list[str] | None = None,
    sources: ResearchSources | None = None,
) -> LookupOutcome:
    """`domain` wins when the person gave one (a pasted website, or a candidate they chose);
    otherwise the name is resolved. `avoid` lists websites already rejected with "not this one";
    `always_ask` returns the candidates instead of picking one. `focus` is an area to research the
    company around and `criteria` are the person's own questions; both are optional extras that
    never change the call."""
    focus = (focus or "").strip() or None
    criteria = [c.strip() for c in criteria or [] if c.strip()]
    offerings = await _offerings(session, organization_id)
    notes: list[str] = []
    if not offerings:
        notes.append("No active offerings are set up, so fit to our offerings cannot be judged.")
    query = (name or domain or "").strip()
    results = await searcher.search_raw(f"{query} company", SEARCH_RESULTS) if query else []
    if not results:
        notes.append(
            "Web search returned nothing. If this keeps happening, check that search is set up."
        )

    chosen_domain = normalize_domain(domain)
    chosen_name = (name or "").strip() or (chosen_domain or "")
    if chosen_domain is None:
        candidates = build_candidates(query, results, denylist, _area_words(offerings), avoid)
        chosen = None if always_ask else pick(candidates)
        if chosen is None:
            status = STATUS_NEEDS_CHOICE if candidates else STATUS_NOT_FOUND
            if not candidates:
                notes.append("No company website matching that name was found.")
            return LookupOutcome(status, candidates=candidates, notes=notes)
        chosen_domain, chosen_name = chosen.domain, chosen.name

    fingerprint = offerings_fingerprint(offerings, focus, criteria)
    existing = await _find_snapshot(session, organization_id, chosen_domain)
    if existing is not None and not refresh and _is_fresh(existing, fingerprint):
        return LookupOutcome(STATUS_READY, existing, cached=True, notes=notes)

    evidence, evidence_notes = await _gather_evidence(fetcher, results, chosen_name, chosen_domain)
    notes.extend(evidence_notes)
    if sources is not None:
        area_tags = await offering_areas(session, organization_id)
        found, research_notes = await gather_research(
            sources, chosen_name, chosen_domain, area_tags
        )
        evidence.extend(found)
        notes.extend(research_notes)
    if focus:
        evidence = await _add_focus_evidence(searcher, evidence, chosen_name, focus)
    evidence = _label(evidence)
    summary = await build_summary(
        llm, chosen_name, chosen_domain, evidence, offerings, criteria, focus
    )
    notes.extend(summary.pop("notes", []))
    sources = [{"url": e.url, "kind": e.kind} for e in evidence]
    snapshot = existing or CompanySnapshot(organization_id=organization_id, domain=chosen_domain)
    snapshot.name = str(summary["name"])[:255]
    snapshot.summary = summary
    snapshot.sources = sources
    snapshot.offerings_hash = fingerprint
    snapshot.model_used = getattr(llm, "last_model", None)
    snapshot.prompt_version = PROMPT_VERSION
    snapshot.updated_at = datetime.now(UTC)
    session.add(snapshot)
    await session.flush()
    return LookupOutcome(STATUS_READY, snapshot, notes=notes)


async def get_snapshot(
    session: AsyncSession, organization_id: uuid.UUID, snapshot_id: uuid.UUID
) -> CompanySnapshot:
    snapshot = await session.get(CompanySnapshot, snapshot_id)
    if snapshot is None or snapshot.organization_id != organization_id:
        raise SnapshotNotFoundError(
            "That look-up is no longer available. Look the company up again."
        )
    return snapshot


async def save_as_company(
    session: AsyncSession, organization_id: uuid.UUID, snapshot_id: uuid.UUID, go_deeper: bool
) -> dict[str, Any]:
    """Adds the company to the companies list (or finds it when it is already there). With
    `go_deeper`, a company that was never researched also gets its research started."""
    snapshot = await get_snapshot(session, organization_id, snapshot_id)
    summary = snapshot.summary or {}
    company, created = await get_or_create_company(
        session,
        organization_id,
        name=snapshot.name,
        domain=snapshot.domain,
        industry=summary.get("industry"),
    )
    # The questions typed for this look-up stay with the company, so its page shows them.
    add_company_criteria(
        company,
        [{"name": c.get("name")} for c in summary.get("criteria") or [] if c.get("name")],
    )
    await session.flush()
    job_id = None
    if go_deeper and company.enrichment_status == ENRICHMENT_STATUS_NEVER_ENRICHED:
        job = await start_company_scrape(session, organization_id, company.id)
        job_id = job.id if job else None
    return {"company_id": company.id, "created": created, "job_id": job_id}
