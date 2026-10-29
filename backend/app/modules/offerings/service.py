"""The website sync: reads InfoBeans' site and records what changed as proposals for a person to
review. It never creates or edits a live offering itself — only approving a proposal does that —
and it never touches manual offerings at all.

Every page it considers is remembered in the `offering_pages` ledger. A page whose sitemap
`lastmod` has not moved since it was last looked at is skipped outright: no scrape, no model call,
no credit. A page that did move is read, and the model is only called when its text really
changed."""

import hashlib
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.modules.jobs.models import Job
from app.modules.llm.structured import LLMError, StructuredLLM, build_structured_llm
from app.modules.offerings.extractor import extract_offering
from app.modules.offerings.grounding import check_grounding, source_excerpt
from app.modules.offerings.menu import read_menu
from app.modules.offerings.models import (
    CHANGE_CHANGED,
    CHANGE_NEW,
    CHANGE_REMOVED,
    LANE_EXTRA,
    LANE_MENU,
    LANE_POST,
    LANE_SITE,
    PROPOSAL_PENDING,
    PROPOSAL_REJECTED,
    VERDICT_FAILED,
    VERDICT_NOT_OFFERING,
    VERDICT_OFFERING,
    OfferingPage,
    OfferingProposal,
)
from app.modules.offerings.names import names_match
from app.modules.offerings.sitemaps import SitemapEntry
from app.modules.offerings.sources import (
    OfferingPageSource,
    PageSourceError,
    build_page_source,
    filter_offering_urls,
)
from app.modules.offerings.triage import TriagePage, title_from_url, triage_posts
from app.modules.offerings.urls import canonical_url
from app.modules.products.models import SOURCE_WEBSITE, STATUS_ACTIVE, Product

logger = logging.getLogger(__name__)

JOB_TYPE_SYNC_OFFERINGS = "sync_offerings"

ProgressCallback = Callable[..., Awaitable[None]]

_COMMIT_EVERY = 10

REASON_OFFERING = "read as an offering"
REASON_NOT_OFFERING = "the model judged it not to be an offering"
REASON_SCREENED_OUT = "screened out from its title"
REASON_UNREADABLE = "the page could not be read"
REASON_MODEL_FAILED = "no model could read it"


class SyncFailed(RuntimeError):
    """The sync could not do its job (for example the network was down). Raised so the check is
    recorded as failed, with a message a person can read, instead of "done" with nothing in it."""


@dataclass
class PageRef:
    url: str
    lane: str
    lastmod: datetime | None
    title: str | None = None


def content_hash(text: str) -> str:
    """Hash of a page's text ignoring case and spacing, so cosmetic reflow is not a change."""
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _squash(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _same_text(a: str | None, b: str | None) -> bool:
    return _squash(a) == _squash(b)


def _aware(moment: datetime | None) -> datetime | None:
    """Databases such as SQLite hand back naive times; ours are always UTC."""
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


def can_skip(
    row: OfferingPage | None,
    ref: PageRef,
    now: datetime,
    full_recheck_days: int,
    unknown_lastmod_days: int = 6,
) -> bool:
    """True when the ledger already holds a finished verdict for this page and nothing says it
    has changed since: nothing needs to be fetched or asked."""
    if row is None or row.verdict == VERDICT_FAILED or row.force_extract:
        return False
    checked = _aware(row.last_checked_at)
    if ref.lastmod is None or row.lastmod is None:
        # No time from the site to trust (an external page, or a sitemap without one): do not
        # re-read it on every sync, only once a few days have passed.
        return (
            unknown_lastmod_days > 0
            and checked is not None
            and now - checked < timedelta(days=unknown_lastmod_days)
        )
    if _aware(row.lastmod) != ref.lastmod:
        return False
    if full_recheck_days > 0 and (
        checked is None or now - checked >= timedelta(days=full_recheck_days)
    ):
        return False  # periodic full re-read: last-modified times can be wrong
    return True


def _remember(
    session: AsyncSession,
    ledger: dict[str, OfferingPage],
    organization_id: uuid.UUID,
    ref: PageRef,
    verdict: str,
    reason: str,
    now: datetime,
    digest: str | None = None,
    title: str | None = None,
    fetched: bool = False,
) -> OfferingPage:
    row = ledger.get(ref.url)
    if row is None:
        row = OfferingPage(organization_id=organization_id, url=ref.url)
        session.add(row)
        ledger[ref.url] = row
    row.lane = ref.lane
    row.lastmod = ref.lastmod
    row.verdict = verdict
    row.reason = reason
    row.last_checked_at = now
    if title or ref.title:
        row.title = (title or ref.title or "")[:512]
    if digest is not None:
        row.content_hash = digest
    if fetched:
        row.last_fetched_at = now
    return row


async def _heal_ledger(
    session: AsyncSession, ledger_rows: list[OfferingPage]
) -> dict[str, OfferingPage]:
    """Older rows may hold an address spelled differently (a trailing slash). Rename them to the
    canonical form, dropping a duplicate if the canonical row already exists."""
    by_url: dict[str, OfferingPage] = {}
    for row in sorted(ledger_rows, key=lambda r: r.url == canonical_url(r.url), reverse=True):
        canonical = canonical_url(row.url)
        if canonical in by_url:
            await session.delete(row)
            continue
        if row.url != canonical:
            row.url = canonical
        by_url[canonical] = row
    await session.flush()
    return by_url


async def run_sync(
    session: AsyncSession,
    organization_id: uuid.UUID,
    source: OfferingPageSource,
    llm: StructuredLLM,
    settings: Settings,
    progress_callback: ProgressCallback | None = None,
    triage_llm: StructuredLLM | None = None,
    menu: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    domain = settings.offerings_site_domain
    excluded = settings.offerings_exclude_paths

    site_entries = [
        SitemapEntry(canonical_url(e.url), e.lastmod)
        for e in await source.list_entries(settings.offerings_sitemap_url)
    ]
    site_lastmod = {e.url: e.lastmod for e in site_entries}
    refs = [
        PageRef(url, LANE_SITE, site_lastmod.get(url))
        for url in filter_offering_urls([e.url for e in site_entries], domain, excluded)
    ]
    known = {r.url for r in refs}

    post_entries: list[SitemapEntry] = []
    posts_readable = False
    if settings.offerings_post_sitemap_url and triage_llm is not None:
        try:
            post_entries = [
                SitemapEntry(canonical_url(e.url), e.lastmod)
                for e in await source.list_entries(settings.offerings_post_sitemap_url)
            ]
            posts_readable = True
        except PageSourceError as exc:
            logger.warning("could not read the post sitemap, skipping blog posts: %s", exc)
    post_lastmod = {e.url: e.lastmod for e in post_entries}

    for raw in settings.offerings_extra_urls:
        url = canonical_url(raw)
        if url not in known:
            known.add(url)
            refs.append(PageRef(url, LANE_EXTRA, post_lastmod.get(url) or site_lastmod.get(url)))

    post_refs = [
        PageRef(url, LANE_POST, post_lastmod.get(url))
        for url in filter_offering_urls([e.url for e in post_entries], domain, excluded)
        if url not in known
    ]

    products = (
        await session.execute(
            select(Product).where(
                Product.organization_id == organization_id, Product.source == SOURCE_WEBSITE
            )
        )
    ).scalars().all()
    by_url = {canonical_url(p.source_url): p for p in products if p.source_url}

    proposals = (
        await session.execute(
            select(OfferingProposal).where(OfferingProposal.organization_id == organization_id)
        )
    ).scalars().all()
    pending = [p for p in proposals if p.status == PROPOSAL_PENDING]
    pending_by_url = {
        canonical_url(p.source_url): p for p in pending if p.change != CHANGE_REMOVED
    }
    rejected = {
        (canonical_url(p.source_url), p.content_hash)
        for p in proposals
        if p.status == PROPOSAL_REJECTED
    }

    ledger_rows = (
        await session.execute(
            select(OfferingPage).where(OfferingPage.organization_id == organization_id)
        )
    ).scalars().all()
    ledger = await _heal_ledger(session, list(ledger_rows))

    counts = {
        "pages_checked": 0, "skipped": 0, "screened_out": 0, "deferred": 0, "new": 0,
        "changed": 0, "removed": 0, "unchanged": 0, "not_offering": 0, "failed": 0,
    }
    recheck = settings.offerings_full_recheck_days
    unknown_days = settings.offerings_unknown_lastmod_days

    # What the company's own menu names that the catalogue does not already cover by name is
    # read too, whatever site it lives on: no product is hard-wired, and anything new the
    # company adds to its menu is picked up.
    offering_names = [p.name for p in products] + [p.name for p in pending]
    for item in menu or []:
        url = canonical_url(item["url"])
        if url in known or any(names_match(item["label"], n) for n in offering_names):
            continue
        known.add(url)
        refs.append(PageRef(url, LANE_MENU, None, item["label"]))

    to_read = [r for r in refs if not can_skip(ledger.get(r.url), r, now, recheck, unknown_days)]
    counts["skipped"] += len(refs) - len(to_read)

    if post_refs and triage_llm is not None:
        to_read.extend(
            await _screen_posts(
                session, source, triage_llm, settings, post_refs, ledger, organization_id,
                now, counts,
            )
        )

    # Pages a person has asked to be read as offerings are read even if the sitemap no longer
    # lists them (a screened-out post, or an address added by hand).
    queued = {r.url for r in to_read}
    for row in ledger.values():
        if row.force_extract and row.url not in queued:
            to_read.append(PageRef(row.url, row.lane, _aware(row.lastmod), row.title))

    unreadable = 0
    for index, ref in enumerate(to_read, start=1):
        counts["pages_checked"] += 1
        row = ledger.get(ref.url)
        text = await source.fetch_text(ref.url)
        if text is None:
            _remember(session, ledger, organization_id, ref, VERDICT_FAILED, REASON_UNREADABLE, now)
            counts["failed"] += 1
            unreadable += 1
        else:
            digest = content_hash(text)
            forced = bool(row and row.force_extract)
            if row and row.content_hash == digest and row.verdict != VERDICT_FAILED and not forced:
                # The page reads exactly as before: only its last-modified time moved.
                _remember(
                    session, ledger, organization_id, ref, row.verdict, row.reason or "",
                    now, digest, fetched=True,
                )
                counts["unchanged"] += 1
            else:
                outcome, name = await _process_page(
                    session, organization_id, llm, ref, text, digest, by_url.get(ref.url),
                    pending_by_url, rejected, now, forced,
                )
                verdict, reason = _verdict_for(outcome)
                _remember(
                    session, ledger, organization_id, ref, verdict, reason, now, digest,
                    title=name, fetched=True,
                )
                if forced and ledger[ref.url].force_extract:
                    ledger[ref.url].force_extract = False
                counts[outcome] += 1
        if progress_callback is not None:
            await progress_callback(index, len(to_read), **counts)
        if index % _COMMIT_EVERY == 0:
            await session.commit()

    # A run that could read little or nothing is a failed check, not a quiet success, and it
    # must never conclude that pages have disappeared.
    tried = counts["pages_checked"]
    if (tried >= 5 and unreadable == tried) or (tried >= 10 and unreadable * 2 >= tried):
        await session.commit()
        raise SyncFailed(
            f"Could not read {unreadable} of {tried} pages, most likely a network problem "
            "reaching the website. Nothing was changed; try again in a few minutes."
        )

    counts["removed"] = await _propose_removals(
        session, organization_id, source, by_url, ledger, proposals, pending, refs, post_refs,
        posts_readable, now,
    )
    await session.commit()
    return counts


def _verdict_for(outcome: str) -> tuple[str, str]:
    if outcome == "not_offering":
        return VERDICT_NOT_OFFERING, REASON_NOT_OFFERING
    if outcome == "failed":
        return VERDICT_FAILED, REASON_MODEL_FAILED
    return VERDICT_OFFERING, REASON_OFFERING


async def _screen_posts(
    session: AsyncSession,
    source: OfferingPageSource,
    triage_llm: StructuredLLM,
    settings: Settings,
    post_refs: list[PageRef],
    ledger: dict[str, OfferingPage],
    organization_id: uuid.UUID,
    now: datetime,
    counts: dict[str, int],
) -> list[PageRef]:
    """Looks at blog posts the ledger has not already settled, using only titles, and returns the
    few worth reading in full (newest first, up to the per-sync cap)."""
    recheck = settings.offerings_full_recheck_days
    asked_for = {url for url, row in ledger.items() if row.force_extract}  # read separately
    fresh = [
        r
        for r in post_refs
        if r.url not in asked_for
        and not can_skip(
            ledger.get(r.url), r, now, recheck, settings.offerings_unknown_lastmod_days
        )
    ]
    counts["skipped"] += len(post_refs) - len(fresh) - len(asked_for & {r.url for r in post_refs})
    if not fresh:
        return []

    try:
        info = await source.describe(settings.offerings_post_sitemap_url)
    except PageSourceError:
        info = {}
    pages = []
    for ref in fresh:
        title, description = info.get(ref.url, (None, None))
        ref.title = title or title_from_url(ref.url)
        pages.append(TriagePage(ref.url, ref.title, description))

    likely, screened_out, _undecided = await triage_posts(triage_llm, pages)
    by_ref = {r.url: r for r in fresh}
    for page in screened_out:
        _remember(
            session, ledger, organization_id, by_ref[page.url], VERDICT_NOT_OFFERING,
            REASON_SCREENED_OUT, now,
        )
        counts["screened_out"] += 1

    ordered = sorted(
        (by_ref[p.url] for p in likely),
        key=lambda r: r.lastmod or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    cap = settings.offerings_max_post_suggestions
    counts["deferred"] += max(0, len(ordered) - cap)
    return ordered[:cap]


async def _propose_removals(
    session: AsyncSession,
    organization_id: uuid.UUID,
    source: OfferingPageSource,
    by_url: dict[str, Product],
    ledger: dict[str, OfferingPage],
    proposals: list[OfferingProposal],
    pending: list[OfferingProposal],
    refs: list[PageRef],
    post_refs: list[PageRef],
    posts_readable: bool,
    now: datetime,
) -> int:
    """A website offering whose page is gone: propose archiving it. "Not in the sitemap" is not
    enough: the page itself must answer 404 or 410, so a difference in how an address is spelled,
    or a listing problem, can never mark a live offering as removed. A removal a person already
    turned down ("keep it") is not proposed again, and nothing is proposed for a lane whose
    sitemap could not be read this time. Waiting removals whose page turns out to be alive are
    withdrawn: they are staging rows, and they were wrong."""
    listed = {r.url for r in refs} | {r.url for r in post_refs}
    products = {p.id: p for p in by_url.values()}

    for proposal in pending:
        if proposal.change != CHANGE_REMOVED:
            continue
        product = products.get(proposal.product_id) if proposal.product_id else None
        url = canonical_url(product.source_url or proposal.source_url) if product else None
        if product is None or url in listed or not await source.is_gone(url or ""):
            proposal.status = "withdrawn"  # keeps it out of the "already proposed" check below
            await session.delete(proposal)

    open_removals = {
        p.product_id
        for p in proposals
        if p.change == CHANGE_REMOVED and p.status in (PROPOSAL_PENDING, PROPOSAL_REJECTED)
    }
    removed = 0
    for url, product in by_url.items():
        row = ledger.get(url)
        lane = row.lane if row is not None else LANE_SITE
        if lane == LANE_POST and not posts_readable:
            continue
        if (
            product.status != STATUS_ACTIVE
            or url in listed
            or lane in (LANE_EXTRA, LANE_MENU)
            or product.id in open_removals
        ):
            continue
        if not await source.is_gone(url):
            continue
        session.add(
            OfferingProposal(
                organization_id=organization_id,
                product_id=product.id,
                change=CHANGE_REMOVED,
                kind=product.kind,
                name=product.name,
                description=product.description,
                source_url=url,
                origin=lane,
                detected_at=now,
            )
        )
        removed += 1
    return removed


async def _process_page(
    session: AsyncSession,
    organization_id: uuid.UUID,
    llm: StructuredLLM,
    ref: PageRef,
    text: str,
    digest: str,
    product: Product | None,
    pending_by_url: dict[str, OfferingProposal],
    rejected: set[tuple[str, str | None]],
    now: datetime,
    forced: bool = False,
) -> tuple[str, str | None]:
    """Handles one page; returns (which counter it belongs to, the offering's name if any)."""
    url = ref.url
    if not forced:
        if product is not None and product.source_hash == digest:
            product.last_seen_at = now
            return "unchanged", product.name
        pending = pending_by_url.get(url)
        if pending is not None and pending.content_hash == digest:
            return "unchanged", pending.name  # already waiting for a person to review
        if (url, digest) in rejected:
            return "unchanged", None  # a person already said no to this version of the page

    try:
        extraction = await extract_offering(llm, url, text, forced=forced)
    except LLMError as exc:
        logger.warning("could not read %s: %s", url, exc)
        return "failed", None
    if extraction is None:
        return "not_offering", None
    assert extraction.kind is not None and extraction.name is not None  # extract_offering checked

    name = extraction.name.strip()[:255]
    if (
        product is not None
        and product.name == name
        and _same_text(product.description, extraction.description)
        and product.kind == extraction.kind
    ):
        # The page changed but what it says about the offering did not: nothing to review.
        product.source_hash = digest
        product.last_seen_at = now
        return "unchanged", name

    change = CHANGE_CHANGED if product is not None else CHANGE_NEW
    excerpt = source_excerpt(text)
    flags = check_grounding(name, extraction.description, text) or None
    pending = pending_by_url.get(url)
    if pending is not None:
        pending.change = change
        pending.kind = extraction.kind
        pending.name = name
        pending.description = extraction.description
        pending.content_hash = digest
        pending.detected_at = now
        pending.origin = ref.lane
        pending.source_excerpt = excerpt
        pending.grounding_flags = flags
    else:
        proposal = OfferingProposal(
            organization_id=organization_id,
            product_id=product.id if product is not None else None,
            change=change,
            kind=extraction.kind,
            name=name,
            description=extraction.description,
            source_url=url,
            content_hash=digest,
            detected_at=now,
            origin=ref.lane,
            source_excerpt=excerpt,
            grounding_flags=flags,
        )
        session.add(proposal)
        pending_by_url[url] = proposal
    return ("changed" if change == CHANGE_CHANGED else "new"), name


async def process_sync_offerings_job(
    session: AsyncSession, job: Job, progress_callback: ProgressCallback | None = None
) -> dict[str, Any]:
    """Handler registered with the job worker — builds the real sources and model chains."""
    settings = get_settings()
    source = build_page_source(settings)
    llm = build_structured_llm(settings)
    triage_llm = build_structured_llm(
        settings, settings.offerings_triage_llm_order, settings.groq_triage_model
    )

    # The company's own menu first: an independent list of what it puts forward, used both to
    # find offerings the sitemaps do not name and to check the catalogue afterwards.
    menu: list[dict[str, str]] | None = None
    menu_error: str | None = None
    try:
        items = await read_menu(
            settings.offerings_menu_url, settings.offerings_menu_groups, settings.scraper_user_agent
        )
        menu = [{"group": i.group, "label": i.label, "url": i.url} for i in items]
        if not menu:
            menu_error = "The website menu was read but no offerings were found in it."
    except Exception as exc:  # noqa: BLE001 - a menu problem must never fail the sync
        logger.warning("could not read the website menu: %s", exc)
        menu_error = "Could not reach the website just now to read its menu. Try again in a minute."

    try:
        counts = await run_sync(
            session, job.organization_id, source, llm, settings, progress_callback,
            triage_llm, menu,
        )
    finally:
        await source.aclose()
    return {
        **counts,
        "menu": menu,
        "menu_error": menu_error,
        "listed_by": source.list_source,
        "read_by": sorted(source.text_sources),
        "answered_by": sorted(llm.used),
        "screened_by": sorted(triage_llm.used),
        "context_dev_credits": source.credits_used,
    }
