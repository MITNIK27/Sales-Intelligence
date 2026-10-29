from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.modules.llm.structured import (
    FallbackStructuredLLM,
    GroqStructuredLLM,
    LLMError,
    StructuredLLM,
)
from app.modules.offerings.extractor import OfferingExtraction
from app.modules.offerings.models import (
    CHANGE_CHANGED,
    CHANGE_NEW,
    CHANGE_REMOVED,
    PROPOSAL_REJECTED,
    OfferingProposal,
)
from app.modules.offerings.service import content_hash, run_sync
from app.modules.offerings.sitemaps import SitemapEntry
from app.modules.offerings.sources import (
    FallbackPageSource,
    OfferingPageSource,
    PageSourceError,
    filter_offering_urls,
)
from app.modules.products.models import Product
from app.modules.products.service import create_product

SETTINGS = Settings(
    _env_file=None,
    offerings_site_domain="infobeans.ai",
    offerings_extra_urls=[],
    offerings_post_sitemap_url="",
)
SPACEWARP = "https://infobeans.ai/spacewarp"
CLOUD = "https://infobeans.ai/cloud"


class FakeSource(OfferingPageSource):
    name = "fake"

    def __init__(self, pages: dict[str, str | None], gone: set[str] | None = None) -> None:
        self.pages = pages
        self.gone = gone or set()
        self.lastmods: dict[str, datetime] = {}

    async def list_urls(self) -> list[str]:
        return list(self.pages)

    async def list_entries(self, sitemap_url):
        return [SitemapEntry(u, self.lastmods.get(u)) for u in self.pages]

    async def is_gone(self, url: str) -> bool:
        return url in self.gone

    async def fetch_text(self, url: str) -> str | None:
        return self.pages.get(url)


class FakeLLM(StructuredLLM):
    name = "fake"

    def __init__(self, answers: dict[str, OfferingExtraction | Exception]) -> None:
        self.answers = answers
        self.calls = 0

    async def generate(self, prompt, schema):
        self.calls += 1
        for url, answer in self.answers.items():
            if url in prompt:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise LLMError("no answer")


def offering(
    name: str, kind: str = "product", description: str = "Does a thing."
) -> OfferingExtraction:
    return OfferingExtraction(is_offering=True, kind=kind, name=name, description=description)


async def proposals(session) -> list[OfferingProposal]:
    return list((await session.execute(select(OfferingProposal))).scalars())


async def test_new_page_becomes_a_proposal_and_creates_no_live_offering(
    db_session, organization_id
) -> None:
    source = FakeSource({SPACEWARP: "Spacewarp moves ServiceNow data."})
    llm = FakeLLM({SPACEWARP: offering("Spacewarp")})

    counts = await run_sync(db_session, organization_id, source, llm, SETTINGS)

    assert counts["new"] == 1
    found = await proposals(db_session)
    assert [(p.name, p.change, p.kind, p.source_url) for p in found] == [
        ("Spacewarp", CHANGE_NEW, "product", SPACEWARP)
    ]
    assert (await db_session.execute(select(Product))).scalars().all() == []


async def test_a_second_sync_of_the_same_page_costs_no_model_call(
    db_session, organization_id
) -> None:
    source = FakeSource({SPACEWARP: "Spacewarp moves ServiceNow data."})
    llm = FakeLLM({SPACEWARP: offering("Spacewarp")})

    await run_sync(db_session, organization_id, source, llm, SETTINGS)
    counts = await run_sync(db_session, organization_id, source, llm, SETTINGS)

    assert counts["skipped"] == 1 and counts["new"] == 0
    assert llm.calls == 1
    assert len(await proposals(db_session)) == 1


async def test_pages_that_are_not_offerings_and_failures_are_counted(
    db_session, organization_id
) -> None:
    source = FakeSource({CLOUD: "text", SPACEWARP: None, "https://infobeans.ai/bfsi": "bfsi"})
    llm = FakeLLM(
        {
            CLOUD: OfferingExtraction(is_offering=False),
            "https://infobeans.ai/bfsi": LLMError("rate limited"),
        }
    )

    counts = await run_sync(db_session, organization_id, source, llm, SETTINGS)

    assert counts["not_offering"] == 1
    assert counts["failed"] == 2  # one unreadable page, one model failure
    assert await proposals(db_session) == []


async def test_changed_page_proposes_a_change_and_leaves_the_live_offering_alone(
    db_session, organization_id
) -> None:
    live = await create_product(db_session, organization_id, name="Spacewarp", description="Old.")
    live.source = "website"
    live.source_url = SPACEWARP
    live.source_hash = content_hash("old page text")
    await db_session.commit()
    source = FakeSource({SPACEWARP: "brand new page text"})
    llm = FakeLLM({SPACEWARP: offering("Spacewarp", description="A new description.")})

    counts = await run_sync(db_session, organization_id, source, llm, SETTINGS)

    assert counts["changed"] == 1
    [proposal] = await proposals(db_session)
    assert (proposal.change, proposal.product_id) == (CHANGE_CHANGED, live.id)
    await db_session.refresh(live)
    assert live.description == "Old."  # only approving a proposal may change it
    assert live.source_hash == content_hash("old page text")


async def test_reworded_page_with_the_same_meaning_needs_no_review(
    db_session, organization_id
) -> None:
    live = await create_product(
        db_session, organization_id, name="Spacewarp", description="Does a thing."
    )
    live.source = "website"
    live.source_url = SPACEWARP
    live.source_hash = content_hash("old page text")
    await db_session.commit()
    source = FakeSource({SPACEWARP: "the page was reflowed"})
    llm = FakeLLM({SPACEWARP: offering("Spacewarp")})

    counts = await run_sync(db_session, organization_id, source, llm, SETTINGS)

    assert counts["unchanged"] == 1
    assert await proposals(db_session) == []
    await db_session.refresh(live)
    assert live.source_hash == content_hash("the page was reflowed")


async def test_page_gone_from_the_site_proposes_archiving_but_manual_offerings_are_ignored(
    db_session, organization_id
) -> None:
    imported = await create_product(db_session, organization_id, name="Old thing", description=None)
    imported.source = "website"
    imported.source_url = "https://infobeans.ai/old-thing"
    manual = await create_product(db_session, organization_id, name="By hand", description=None)
    await db_session.commit()
    source = FakeSource({CLOUD: "text"}, gone={"https://infobeans.ai/old-thing"})
    llm = FakeLLM({CLOUD: OfferingExtraction(is_offering=False)})

    counts = await run_sync(db_session, organization_id, source, llm, SETTINGS)
    again = await run_sync(db_session, organization_id, source, llm, SETTINGS)

    assert counts["removed"] == 1 and again["removed"] == 0  # not proposed twice
    [proposal] = await proposals(db_session)
    assert (proposal.change, proposal.product_id) == (CHANGE_REMOVED, imported.id)
    await db_session.refresh(manual)
    assert manual.status == "active" and manual.source == "manual"


async def test_a_rejected_page_is_not_proposed_again_until_it_changes(
    db_session, organization_id
) -> None:
    source = FakeSource({SPACEWARP: "same text"})
    source.lastmods[SPACEWARP] = datetime(2026, 9, 1, tzinfo=UTC)
    llm = FakeLLM({SPACEWARP: offering("Spacewarp")})
    await run_sync(db_session, organization_id, source, llm, SETTINGS)
    [proposal] = await proposals(db_session)
    proposal.status = PROPOSAL_REJECTED
    await db_session.commit()

    again = await run_sync(db_session, organization_id, source, llm, SETTINGS)
    assert again["new"] == 0 and llm.calls == 1

    source.lastmods[SPACEWARP] = datetime(2026, 10, 1, tzinfo=UTC)
    source.pages[SPACEWARP] = "different text now"
    changed = await run_sync(db_session, organization_id, source, llm, SETTINGS)
    assert changed["new"] == 1


def test_filter_keeps_same_site_offering_pages_only() -> None:
    urls = [
        "https://infobeans.ai/",
        "https://infobeans.ai/spacewarp",
        "https://infobeans.ai/spacewarp/#faq",
        "https://www.infobeans.ai/cloud",
        "https://infobeans.ai/blog/post-1",
        "https://infobeans.ai/careers",
        "https://other.com/spacewarp",
    ]
    assert filter_offering_urls(urls, "infobeans.ai", ["/blog", "/careers"]) == [
        "https://infobeans.ai/spacewarp",
        "https://infobeans.ai/cloud",
    ]


class _Broken(OfferingPageSource):
    name = "broken"

    async def list_urls(self) -> list[str]:
        raise PageSourceError("down")

    async def fetch_text(self, url: str) -> str | None:
        return None


async def test_page_sources_fall_back_in_order() -> None:
    chain = FallbackPageSource([_Broken(), FakeSource({SPACEWARP: "text"})])

    assert await chain.list_urls() == [SPACEWARP]
    assert chain.list_source == "fake"
    assert await chain.fetch_text(SPACEWARP) == "text"
    assert chain.text_sources == {"fake"}

    with pytest.raises(PageSourceError):
        await FallbackPageSource([_Broken()]).list_urls()


async def test_language_models_fall_back_in_order() -> None:
    class Down(StructuredLLM):
        name = "down"

        async def generate(self, prompt, schema):
            raise LLMError("rate limited")

    chain = FallbackStructuredLLM([Down(), FakeLLM({"x": offering("Answer")})])
    result = await chain.generate("x", OfferingExtraction)

    assert result.name == "Answer"
    assert chain.used == {"fake"}
    with pytest.raises(LLMError):
        await FallbackStructuredLLM([Down()]).generate("x", OfferingExtraction)


async def test_groq_reply_is_validated_and_failures_become_llm_errors(monkeypatch) -> None:
    llm = GroqStructuredLLM(Settings(_env_file=None, groq_api_key="key"))
    reply = {"content": '{"is_offering": true, "kind": "service", "name": "Cloud"}'}

    async def post(self, url, **kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer key"
        assert kwargs["json"]["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200, json={"choices": [{"message": reply}]}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    assert (await llm.generate("p", OfferingExtraction)).name == "Cloud"

    reply["content"] = "not json"
    with pytest.raises(LLMError):
        await llm.generate("p", OfferingExtraction)

    async def rate_limited(self, url, **kwargs):
        return httpx.Response(429, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", rate_limited)
    with pytest.raises(LLMError, match="429"):
        await llm.generate("p", OfferingExtraction)

    with pytest.raises(LLMError, match="not configured"):
        await GroqStructuredLLM(Settings(_env_file=None, groq_api_key=None)).generate(
            "p", OfferingExtraction
        )


async def test_groq_waits_out_a_short_rate_limit_then_succeeds(monkeypatch) -> None:
    llm = GroqStructuredLLM(Settings(_env_file=None, groq_api_key="key"))
    waits: list[float] = []
    replies = [
        httpx.Response(429, headers={"retry-after": "3"}),
        httpx.Response(
            200, json={"choices": [{"message": {"content": '{"is_offering": false}'}}]}
        ),
    ]

    async def post(self, url, **kwargs):
        reply = replies.pop(0)
        reply.request = httpx.Request("POST", url)
        return reply

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    monkeypatch.setattr("app.modules.llm.structured.asyncio.sleep", fake_sleep)

    assert (await llm.generate("p", OfferingExtraction)).is_offering is False
    assert waits == [3.0]


async def test_groq_does_not_wait_for_a_long_rate_limit(monkeypatch) -> None:
    llm = GroqStructuredLLM(Settings(_env_file=None, groq_api_key="key"))

    async def post(self, url, **kwargs):
        return httpx.Response(
            429, headers={"retry-after": "600"}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    with pytest.raises(LLMError, match="429"):
        await llm.generate("p", OfferingExtraction)
