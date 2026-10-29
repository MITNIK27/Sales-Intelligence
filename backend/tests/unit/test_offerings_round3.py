"""The "36 removed" false alarm and the network blip: addresses spelled differently, removals
that need the site's own 404/410, a run that reads nothing, the website menu, and retries."""

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.modules.llm.structured import LLMError, StructuredLLM
from app.modules.offerings.extractor import OfferingExtraction
from app.modules.offerings.models import (
    CHANGE_REMOVED,
    PROPOSAL_PENDING,
    PROPOSAL_REJECTED,
    VERDICT_FAILED,
    VERDICT_OFFERING,
    OfferingPage,
    OfferingProposal,
)
from app.modules.offerings.service import SyncFailed, run_sync
from app.modules.offerings.sitemaps import SitemapEntry
from app.modules.offerings.sources import OfferingPageSource
from app.modules.offerings.urls import canonical_url
from app.modules.products.service import create_product

CLOUD = "https://infobeans.ai/cloud"
T1 = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
NOT = OfferingExtraction(is_offering=False)


def settings() -> Settings:
    return Settings(
        _env_file=None,
        offerings_site_domain="infobeans.ai",
        offerings_extra_urls=[],
        offerings_post_sitemap_url="",
    )


class Site(OfferingPageSource):
    name = "site"

    def __init__(self, pages, lastmods=None, gone=(), extra_text=None) -> None:
        self.pages = pages
        self.lastmods = lastmods or {}
        self.gone = set(gone)
        self.extra_text = extra_text or {}
        self.fetched: list[str] = []

    async def list_urls(self):
        return list(self.pages)

    async def list_entries(self, sitemap_url):
        return [SitemapEntry(u, self.lastmods.get(u)) for u in self.pages]

    async def is_gone(self, url):
        return url in self.gone

    async def fetch_text(self, url):
        self.fetched.append(url)
        return self.pages.get(url) or self.extra_text.get(url)


class Model(StructuredLLM):
    name = "model"

    def __init__(self, answers=None) -> None:
        self.answers = answers or {}

    async def generate(self, prompt, schema):
        for key, answer in self.answers.items():
            if key in prompt:
                return answer
        raise LLMError("no answer")


def offering(name, kind="service"):
    return OfferingExtraction(is_offering=True, kind=kind, name=name, description="Does a thing.")


async def website_product(session, organization_id, url, name="Agentforce"):
    product = await create_product(session, organization_id, name=name, description="Old.")
    product.source = "website"
    product.source_url = url
    product.source_hash = "old"
    await session.commit()
    return product


async def all_proposals(session):
    return list((await session.execute(select(OfferingProposal))).scalars())


async def ledger(session):
    return {r.url: r for r in (await session.execute(select(OfferingPage))).scalars()}


async def test_a_sitemap_spelling_difference_never_marks_a_live_offering_as_removed(
    db_session, organization_id
) -> None:
    # Saved without a trailing slash (as the first import did); the sitemap writes one.
    live = await website_product(db_session, organization_id, "https://infobeans.ai/agentforce")
    site = Site({"https://infobeans.ai/agentforce/": "agentforce text"})

    counts = await run_sync(
        db_session, organization_id, site, Model({"agentforce": offering("Agentforce")}), settings()
    )

    assert counts["removed"] == 0
    assert [p.change for p in await all_proposals(db_session)] == []  # unchanged text, no news
    await db_session.refresh(live)
    assert live.status == "active"


async def test_a_page_missing_from_the_sitemap_is_only_removed_if_the_site_says_it_is_gone(
    db_session, organization_id
) -> None:
    await website_product(db_session, organization_id, "https://infobeans.ai/alive", "Alive")
    await website_product(db_session, organization_id, "https://infobeans.ai/dead", "Dead")
    site = Site({CLOUD: "cloud"}, gone={"https://infobeans.ai/dead"})

    counts = await run_sync(db_session, organization_id, site, Model({CLOUD: NOT}), settings())

    assert counts["removed"] == 1
    [removal] = await all_proposals(db_session)
    assert (removal.change, removal.name) == (CHANGE_REMOVED, "Dead")


async def test_stale_pending_removals_are_withdrawn_but_a_declined_removal_is_respected(
    db_session, organization_id
) -> None:
    alive = await website_product(db_session, organization_id, CLOUD, "Cloud")
    kept = await website_product(db_session, organization_id, "https://infobeans.ai/kept", "Kept")
    for product, status in ((alive, PROPOSAL_PENDING), (kept, PROPOSAL_REJECTED)):
        db_session.add(
            OfferingProposal(
                organization_id=organization_id,
                product_id=product.id,
                change=CHANGE_REMOVED,
                kind="service",
                name=product.name,
                source_url=product.source_url,
                status=status,
            )
        )
    await db_session.commit()
    site = Site({CLOUD: "cloud"}, gone={"https://infobeans.ai/kept"})

    counts = await run_sync(db_session, organization_id, site, Model({CLOUD: NOT}), settings())

    assert [(p.name, p.status) for p in await all_proposals(db_session)] == [
        ("Kept", PROPOSAL_REJECTED)
    ]
    assert counts["removed"] == 0  # the declined removal is not proposed again


async def test_a_run_that_reads_nothing_fails_and_proposes_no_removals(
    db_session, organization_id
) -> None:
    await website_product(db_session, organization_id, "https://infobeans.ai/gone-page", "X")
    unreadable = {f"https://infobeans.ai/page-{n}": None for n in range(6)}
    site = Site(unreadable, gone={"https://infobeans.ai/gone-page"})

    with pytest.raises(SyncFailed, match="Could not read 6 of 6"):
        await run_sync(db_session, organization_id, site, Model(), settings())

    assert await all_proposals(db_session) == []
    rows = await ledger(db_session)
    assert len(rows) == 6 and all(r.verdict == VERDICT_FAILED for r in rows.values())


async def test_old_ledger_rows_with_a_trailing_slash_are_renamed_not_duplicated(
    db_session, organization_id
) -> None:
    db_session.add(
        OfferingPage(
            organization_id=organization_id,
            url="https://infobeans.ai/cloud/",
            lane="site",
            verdict=VERDICT_OFFERING,
            lastmod=T1,
            last_checked_at=datetime.now(UTC),
        )
    )
    await db_session.commit()
    site = Site({"https://infobeans.ai/cloud/": "cloud"}, {"https://infobeans.ai/cloud/": T1})

    counts = await run_sync(db_session, organization_id, site, Model(), settings())

    assert counts["skipped"] == 1 and site.fetched == []  # the renamed row settled it
    assert list(await ledger(db_session)) == [CLOUD]


async def test_menu_links_the_catalogue_lacks_are_read_once_whatever_site_they_are_on(
    db_session, organization_id
) -> None:
    await website_product(db_session, organization_id, "https://infobeans.ai/stanza", "Stanza")
    site = Site({}, extra_text={"https://expona.io/": "Expona is an instant knowledge assistant."})
    menu = [
        {"group": "Innovation", "label": "Expona AI", "url": "https://expona.io/"},
        {"group": "Innovation", "label": "Stanza", "url": "https://infobeans.ai/stanza"},
    ]
    model = Model({"Expona is": offering("Expona", "product")})

    first = await run_sync(db_session, organization_id, site, model, settings(), menu=menu)
    assert first["new"] == 1
    assert "https://infobeans.ai/stanza" not in site.fetched  # already covered, by name
    site.fetched.clear()
    second = await run_sync(db_session, organization_id, site, model, settings(), menu=menu)

    [proposal] = await all_proposals(db_session)
    assert (proposal.name, proposal.origin) == ("Expona", "menu")
    assert proposal.source_url == "https://expona.io/"
    assert second["pages_checked"] == 0 and site.fetched == []  # read once, then settled


async def test_transient_network_errors_are_retried_but_a_404_is_not(monkeypatch) -> None:
    from app.modules.offerings import retry

    monkeypatch.setattr(retry, "RETRY_WAITS", (0.0, 0.0))
    attempts = {"n": 0}

    async def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise httpx.ConnectError("getaddrinfo failed")
        return "ok"

    assert await retry.with_retries(flaky, "test") == "ok"
    assert attempts["n"] == 3

    async def not_found():
        attempts["n"] += 1
        raise httpx.HTTPStatusError(
            "404", request=httpx.Request("GET", "https://x"), response=httpx.Response(404)
        )

    attempts["n"] = 0
    with pytest.raises(httpx.HTTPStatusError):
        await retry.with_retries(not_found, "test")
    assert attempts["n"] == 1


def test_one_spelling_for_every_address() -> None:
    assert canonical_url("https://www.InfoBeans.ai/agentforce/?a=1#x") == CLOUD.replace(
        "cloud", "agentforce"
    )
    assert canonical_url("https://infobeans.ai") == "https://infobeans.ai/"
