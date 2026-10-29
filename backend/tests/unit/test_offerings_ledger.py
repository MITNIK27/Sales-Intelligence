from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import Settings
from app.modules.llm.structured import LLMError, StructuredLLM
from app.modules.offerings.extractor import OfferingExtraction
from app.modules.offerings.grounding import check_grounding
from app.modules.offerings.models import (
    LANE_POST,
    VERDICT_FAILED,
    VERDICT_NOT_OFFERING,
    VERDICT_OFFERING,
    OfferingPage,
    OfferingProposal,
)
from app.modules.offerings.service import run_sync
from app.modules.offerings.sitemaps import SitemapEntry, parse_lastmod, parse_sitemap
from app.modules.offerings.sources import OfferingPageSource
from app.modules.offerings.triage import TriagePage, TriageResult, title_from_url, triage_posts

CLOUD = "https://infobeans.ai/cloud"
SPACEWARP = "https://infobeans.ai/spacewarp"
EXPONA = "https://infobeans.ai/expona"
POST_SITEMAP = "https://infobeans.ai/post-sitemap.xml"
T1 = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
T2 = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)


def settings(**overrides) -> Settings:
    base = {
        "offerings_site_domain": "infobeans.ai",
        "offerings_extra_urls": [],
        "offerings_post_sitemap_url": "",
        "offerings_full_recheck_days": 30,
    }
    return Settings(_env_file=None, **{**base, **overrides})


class Site(OfferingPageSource):
    """A fake website: page text, last-modified times, and a log of every page it was asked for."""

    name = "site"

    def __init__(self, pages, lastmods=None, posts=None, info=None) -> None:
        self.pages = pages
        self.lastmods = lastmods or {}
        self.posts = posts or {}
        self.info = info or {}
        self.fetched: list[str] = []

    async def list_urls(self) -> list[str]:
        return list(self.pages)

    async def list_entries(self, sitemap_url):
        if sitemap_url == POST_SITEMAP:
            return [SitemapEntry(u, m) for u, m in self.posts.items()]
        return [SitemapEntry(u, self.lastmods.get(u)) for u in self.pages]

    async def describe(self, sitemap_url):
        return self.info

    async def fetch_text(self, url):
        self.fetched.append(url)
        return self.pages.get(url) or self.posts_text.get(url)

    posts_text: dict[str, str] = {}


class Model(StructuredLLM):
    name = "model"

    def __init__(self, answers) -> None:
        self.answers = answers
        self.calls: list[str] = []

    async def generate(self, prompt, schema):
        self.calls.append(prompt)
        for key, answer in self.answers.items():
            if key in prompt:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise LLMError("no answer")


def offering(name, kind="service", description="Does a thing."):
    return OfferingExtraction(is_offering=True, kind=kind, name=name, description=description)


NOT = OfferingExtraction(is_offering=False)


async def ledger(session):
    return {r.url: r for r in (await session.execute(select(OfferingPage))).scalars()}


async def test_unchanged_lastmod_skips_everything_on_the_next_sync(
    db_session, organization_id
) -> None:
    site = Site({CLOUD: "cloud text", SPACEWARP: "spacewarp text"}, {CLOUD: T1, SPACEWARP: T1})
    model = Model({CLOUD: offering("Cloud"), SPACEWARP: NOT})
    s = settings()

    first = await run_sync(db_session, organization_id, site, model, s)
    site.fetched.clear()
    model.calls.clear()
    second = await run_sync(db_session, organization_id, site, model, s)

    assert first["pages_checked"] == 2 and first["new"] == 1 and first["not_offering"] == 1
    assert second["skipped"] == 2 and second["pages_checked"] == 0
    assert site.fetched == [] and model.calls == []  # not even the not-offering page is re-read
    rows = await ledger(db_session)
    assert rows[CLOUD].verdict == VERDICT_OFFERING
    assert rows[SPACEWARP].verdict == VERDICT_NOT_OFFERING


async def test_moved_lastmod_with_identical_text_reads_the_page_but_asks_no_model(
    db_session, organization_id
) -> None:
    site = Site({CLOUD: "cloud text"}, {CLOUD: T1})
    model = Model({CLOUD: offering("Cloud")})
    await run_sync(db_session, organization_id, site, model, settings())
    site.lastmods[CLOUD] = T2
    site.fetched.clear()
    model.calls.clear()

    counts = await run_sync(db_session, organization_id, site, model, settings())

    assert site.fetched == [CLOUD] and model.calls == []
    assert counts["unchanged"] == 1
    assert _aware((await ledger(db_session))[CLOUD].lastmod) == T2


async def test_moved_lastmod_with_new_text_asks_the_model_again(
    db_session, organization_id
) -> None:
    site = Site({CLOUD: "cloud text"}, {CLOUD: T1})
    model = Model({CLOUD: offering("Cloud")})
    await run_sync(db_session, organization_id, site, model, settings())
    site.pages[CLOUD] = "completely different cloud text"
    site.lastmods[CLOUD] = T2
    model.answers = {CLOUD: offering("Cloud", description="A new description.")}

    counts = await run_sync(db_session, organization_id, site, model, settings())

    assert len(model.calls) == 2 and counts["new"] == 1  # nothing is live yet, so still "new"


async def test_failed_pages_are_retried_and_pages_without_a_sitemap_time_are_read_weekly(
    db_session, organization_id
) -> None:
    site = Site({CLOUD: None, SPACEWARP: "spacewarp text"}, {CLOUD: T1})  # no time for Spacewarp
    model = Model({SPACEWARP: offering("Spacewarp", "product")})

    first = await run_sync(db_session, organization_id, site, model, settings())
    assert first["failed"] == 1
    assert (await ledger(db_session))[CLOUD].verdict == VERDICT_FAILED

    site.fetched.clear()
    second = await run_sync(db_session, organization_id, site, model, settings())

    assert site.fetched == [CLOUD]  # the failed one is retried; the untimed one is not re-read
    assert second["skipped"] == 1

    row = (await ledger(db_session))[SPACEWARP]
    row.last_checked_at = datetime.now(UTC) - timedelta(days=7)
    await db_session.commit()
    site.fetched.clear()
    await run_sync(db_session, organization_id, site, model, settings())
    assert SPACEWARP in site.fetched  # a week on, it is read again


async def test_full_recheck_ignores_lastmod_after_the_interval(db_session, organization_id) -> None:
    site = Site({CLOUD: "cloud text"}, {CLOUD: T1})
    model = Model({CLOUD: offering("Cloud")})
    await run_sync(db_session, organization_id, site, model, settings())
    row = (await ledger(db_session))[CLOUD]
    row.last_checked_at = datetime.now(UTC) - timedelta(days=31)
    await db_session.commit()
    site.fetched.clear()

    await run_sync(db_session, organization_id, site, model, settings())
    assert site.fetched == [CLOUD]

    site.fetched.clear()  # now freshly checked again, so it is skipped
    await run_sync(db_session, organization_id, site, model, settings())
    assert site.fetched == []

    no_recheck = settings(offerings_full_recheck_days=0)
    await run_sync(db_session, organization_id, site, model, no_recheck)
    assert site.fetched == []  # periodic re-read switched off


def _aware(moment):
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


async def test_named_extra_pages_are_read_even_though_they_are_not_in_the_page_sitemap(
    db_session, organization_id
) -> None:
    site = Site({CLOUD: "cloud text"})
    site.posts_text = {EXPONA: "Expona is an instant knowledge assistant."}
    model = Model({CLOUD: NOT, EXPONA: offering("Expona", "product")})

    counts = await run_sync(
        db_session, organization_id, site, model, settings(offerings_extra_urls=[EXPONA])
    )

    assert counts["new"] == 1
    [proposal] = (await db_session.execute(select(OfferingProposal))).scalars().all()
    assert (proposal.name, proposal.origin, proposal.source_url) == ("Expona", "extra", EXPONA)
    assert (await ledger(db_session))[EXPONA].lane == "extra"


async def test_blog_posts_are_screened_by_title_and_only_likely_ones_are_read(
    db_session, organization_id
) -> None:
    keep = "https://infobeans.ai/insanesdd-launch"
    skip = "https://infobeans.ai/five-cloud-trends"
    site = Site(
        {},
        posts={keep: T1, skip: T1},
        info={
            keep: ("InsaneSDD 2.0", "AI-native spec-driven development"),
            skip: ("Five trends", None),
        },
    )
    site.posts_text = {keep: "InsaneSDD turns specs into pull requests."}
    model = Model({"InsaneSDD turns": offering("InsaneSDD", "product")})
    triage = Model({"InsaneSDD 2.0": TriageResult(offering_numbers=[1])})
    s = settings(offerings_post_sitemap_url=POST_SITEMAP)

    counts = await run_sync(db_session, organization_id, site, model, s, triage_llm=triage)

    assert site.fetched == [keep]  # the article was never scraped
    assert counts["screened_out"] == 1 and counts["new"] == 1
    [proposal] = (await db_session.execute(select(OfferingProposal))).scalars().all()
    assert proposal.origin == LANE_POST
    rows = await ledger(db_session)
    assert rows[skip].verdict == VERDICT_NOT_OFFERING and rows[skip].reason.startswith("screened")

    # Nothing about either post changed: the next sync does no work at all.
    site.fetched.clear()
    triage.calls.clear()
    again = await run_sync(db_session, organization_id, site, model, s, triage_llm=triage)
    assert again["skipped"] == 2 and site.fetched == [] and triage.calls == []


async def test_post_suggestions_are_capped_and_the_rest_wait_for_the_next_sync(
    db_session, organization_id
) -> None:
    urls = [f"https://infobeans.ai/product-{n}" for n in range(3)]
    site = Site({}, posts={u: T1 + timedelta(days=i) for i, u in enumerate(urls)})
    site.posts_text = {u: f"text {u}" for u in urls}
    model = Model({u: offering(f"P{i}", "product") for i, u in enumerate(urls)})
    triage = Model({"product 0": TriageResult(offering_numbers=[1, 2, 3])})
    s = settings(offerings_post_sitemap_url=POST_SITEMAP, offerings_max_post_suggestions=2)

    counts = await run_sync(db_session, organization_id, site, model, s, triage_llm=triage)

    assert counts["new"] == 2 and counts["deferred"] == 1
    assert urls[0] not in site.fetched  # the oldest one waits; newest first
    assert urls[0] not in await ledger(db_session)


async def test_triage_failure_leaves_posts_unrecorded_so_they_are_tried_again(
    db_session, organization_id
) -> None:
    post = "https://infobeans.ai/something"
    site = Site({}, posts={post: T1})
    triage = Model({"something": LLMError("down")})

    counts = await run_sync(
        db_session, organization_id, site, Model({}),
        settings(offerings_post_sitemap_url=POST_SITEMAP), triage_llm=triage,
    )

    assert counts["screened_out"] == 0
    assert post not in await ledger(db_session)


async def test_triage_batches_and_ignores_numbers_outside_the_batch() -> None:
    pages = [TriagePage(f"https://x/{n}", f"page {n}") for n in range(25)]
    model = Model({"page 0": TriageResult(offering_numbers=[2, 99]), "page 20": TriageResult()})

    likely, screened_out, undecided = await triage_posts(model, pages)

    assert len(model.calls) == 2  # 20 + 5
    assert [p.title for p in likely] == ["page 1"]
    assert len(screened_out) == 24 and undecided == []
    assert title_from_url("https://infobeans.ai/data-yaar-unleash") == "data yaar unleash"


def test_grounding_flags_percentages_missing_numbers_names_and_unknown_terms() -> None:
    page = "Spacewarp is a rule-based tool for ServiceNow storage. It cuts costs by 85%."
    clean = "Spacewarp is a rule-based tool for ServiceNow storage."
    assert check_grounding("Spacewarp", clean, page) == []
    flags = check_grounding(
        "Spacewarp", "Spacewarp cuts costs by 85% for 40 teams. It runs on Kubernetes.", page
    )
    assert any("percentage" in f for f in flags)
    assert any("40" in f for f in flags)
    assert any("Kubernetes" in f for f in flags)
    assert check_grounding("Other", "Fine text.", page) == ['the name "Other" is not on the page']


async def test_proposals_carry_the_source_excerpt_and_grounding_flags(
    db_session, organization_id
) -> None:
    site = Site({CLOUD: "Cloud helps teams move to the cloud. " * 40}, {CLOUD: T1})
    model = Model({CLOUD: offering("Cloud", description="Cloud saves 30% on Kubernetes bills.")})

    await run_sync(db_session, organization_id, site, model, settings())

    [proposal] = (await db_session.execute(select(OfferingProposal))).scalars().all()
    assert proposal.source_excerpt.startswith("Cloud helps teams")
    assert len(proposal.source_excerpt) <= 600
    assert any("percentage" in f for f in proposal.grounding_flags)


def test_sitemap_parsing_reads_lastmod_and_ignores_image_entries() -> None:
    xml = """<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
            xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
      <url><loc>https://infobeans.ai/spacewarp/</loc>
        <lastmod>2026-10-07T09:04:58+00:00</lastmod>
        <image:image><image:loc>https://infobeans.ai/a.png</image:loc></image:image></url>
      <url><loc>https://infobeans.ai/no-time/</loc></url>
    </urlset>"""
    entries, children = parse_sitemap(xml)

    assert [e.url for e in entries] == [
        "https://infobeans.ai/spacewarp/",
        "https://infobeans.ai/no-time/",
    ]
    assert entries[0].lastmod == datetime(2026, 10, 7, 9, 4, 58, tzinfo=UTC)
    assert entries[1].lastmod is None and children == []
    index = (
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<sitemap><loc>https://x/a.xml</loc></sitemap></sitemapindex>"
    )
    assert parse_sitemap(index) == ([], ["https://x/a.xml"])
    assert parse_lastmod("not a date") is None and parse_lastmod(None) is None
