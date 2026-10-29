from datetime import UTC, datetime

import httpx

from app.db.session import get_db
from app.main import app
from app.modules.jobs.models import STATUS_DONE, Job
from app.modules.offerings.coverage import (
    MENU_COVERED,
    MENU_MISSING,
    MENU_NOT_AN_OFFERING,
    MENU_UNREADABLE,
    get_coverage,
    names_match,
    reconcile_menu,
    request_extraction,
)
from app.modules.offerings.menu import parse_menu
from app.modules.offerings.models import (
    VERDICT_FAILED,
    VERDICT_NOT_OFFERING,
    VERDICT_OFFERING,
    OfferingPage,
)
from app.modules.offerings.service import JOB_TYPE_SYNC_OFFERINGS

HOME = """
<html><body><header><nav class="nav-menu">
  <a href="#">Disciplines</a>
  <a href="/ux-design/">Design</a>
  <a href="/servicenow/"><span>ServiceNow</span><span>Premier Partner badge</span></a>
  <a href="https://infobeans.ai?wow_story=1">Read Someone's wow Story</a>
  <a href="#">Innovation</a>
  <a href="https://expona.io/">Expona AI</a>
  <a href="/spacewarp/">Spacewarp for ServiceNow</a>
  <a href="/true-stories/long-story/">View True Story</a>
  <a href="#">Insights</a>
  <a href="/blog/">Blog</a>
</nav></header></body></html>
"""


def page(url, verdict, lane="site"):
    return OfferingPage(url=url, verdict=verdict, lane=lane)


def test_menu_parsing_keeps_only_offering_headings_and_drops_promotions() -> None:
    items = parse_menu(HOME, "https://infobeans.ai/", ["Disciplines", "Innovation"])

    assert [(i.group, i.label, i.url) for i in items] == [
        ("Disciplines", "Design", "https://infobeans.ai/ux-design"),
        ("Disciplines", "ServiceNow", "https://infobeans.ai/servicenow"),
        ("Innovation", "Expona AI", "https://expona.io/"),
        ("Innovation", "Spacewarp for ServiceNow", "https://infobeans.ai/spacewarp"),
    ]
    assert parse_menu("<html></html>", "https://infobeans.ai/", ["Disciplines"]) == []


def test_names_match_tolerates_suffixes_but_not_unrelated_names() -> None:
    assert names_match("Expona AI", "Expona")
    assert names_match("Spacewarp for ServiceNow", "Spacewarp")
    assert not names_match("Cloud", "Cloud Migration Suite")  # short names must match exactly
    assert not names_match("Stanza", "Spacewarp")
    assert not names_match("AI", "AI-Led Engineering")


def test_menu_reconciliation_flags_what_the_catalogue_does_not_cover() -> None:
    menu = [
        {"group": "Innovation", "label": "Expona AI", "url": "https://expona.io/"},
        {"group": "Innovation", "label": "Stanza", "url": "https://infobeans.ai/stanza"},
        {"group": "Disciplines", "label": "BFSI", "url": "https://infobeans.ai/bfsi"},
        {"group": "Disciplines", "label": "GCC", "url": "https://infobeans.ai/gcc-services"},
        {"group": "Disciplines", "label": "Mendix", "url": "https://infobeans.ai/mendix"},
    ]
    pages = {
        "https://infobeans.ai/stanza": page("https://infobeans.ai/stanza", VERDICT_OFFERING),
        "https://infobeans.ai/bfsi": page("https://infobeans.ai/bfsi", VERDICT_NOT_OFFERING),
        "https://infobeans.ai/gcc-services": page(
            "https://infobeans.ai/gcc-services", VERDICT_FAILED
        ),
    }

    result = reconcile_menu(menu, pages, offering_names=["Expona", "Stanza"])

    assert [r["status"] for r in result] == [
        MENU_COVERED,  # expona.io is matched by name to the imported "Expona"
        MENU_COVERED,
        MENU_NOT_AN_OFFERING,
        MENU_UNREADABLE,
        MENU_MISSING,  # never looked at: the gap the check exists to find
    ]


async def test_coverage_lists_every_page_with_its_verdict_and_the_menu_check(
    db_session, organization_id
) -> None:
    db_session.add_all(
        [
            OfferingPage(
                organization_id=organization_id,
                url="https://infobeans.ai/stanza",
                verdict=VERDICT_OFFERING,
                lane="site",
                reason="read as an offering",
            ),
            OfferingPage(
                organization_id=organization_id,
                url="https://infobeans.ai/bfsi",
                verdict=VERDICT_NOT_OFFERING,
                lane="site",
                reason="the model judged it not to be an offering",
            ),
        ]
    )
    job = Job(organization_id=organization_id, job_type=JOB_TYPE_SYNC_OFFERINGS, payload={})
    job.status = STATUS_DONE
    job.finished_at = datetime.now(UTC)
    job.result = {
        "menu": [{"group": "Innovation", "label": "Stanza", "url": "https://infobeans.ai/stanza"}],
        "menu_error": None,
    }
    db_session.add(job)
    await db_session.commit()

    coverage = await get_coverage(db_session, organization_id)

    assert coverage["summary"] == {"total": 2, "offering": 1, "not_offering": 1, "failed": 0}
    assert {p["url"]: p["verdict"] for p in coverage["pages"]} == {
        "https://infobeans.ai/stanza": "offering",
        "https://infobeans.ai/bfsi": "not_offering",
    }
    assert [m["status"] for m in coverage["menu"]] == [MENU_COVERED]


async def test_coverage_has_no_menu_until_a_sync_has_read_it(db_session, organization_id) -> None:
    coverage = await get_coverage(db_session, organization_id)

    assert coverage["menu"] is None and coverage["pages"] == []


async def test_treat_as_offering_marks_a_known_page_and_adds_an_unknown_one(
    db_session, organization_id
) -> None:
    known = OfferingPage(
        organization_id=organization_id,
        url="https://infobeans.ai/bfsi",
        verdict=VERDICT_NOT_OFFERING,
        lane="site",
    )
    db_session.add(known)
    await db_session.commit()

    await request_extraction(db_session, organization_id, "https://infobeans.ai/bfsi")
    added = await request_extraction(db_session, organization_id, "https://expona.io/")

    assert known.force_extract is True
    assert (added.lane, added.force_extract, added.reason) == ("extra", True, "added by a person")


async def test_coverage_endpoints_queue_one_sync_for_a_requested_page(
    db_session, organization_id
) -> None:
    async def override():
        yield db_session

    app.dependency_overrides[get_db] = override
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            bad = await client.post("/api/v1/products/coverage/check", json={"url": "expona.io"})
            ok = await client.post(
                "/api/v1/products/coverage/check", json={"url": "https://expona.io/"}
            )
            again = await client.post(
                "/api/v1/products/coverage/check", json={"url": "https://expona.io/x"}
            )
            view = await client.get("/api/v1/products/coverage")
    finally:
        app.dependency_overrides.clear()

    assert bad.status_code == 422
    assert ok.status_code == 202 and again.json() == ok.json()  # one sync is queued, not two
    assert {p["url"] for p in view.json()["pages"]} == {"https://expona.io/", "https://expona.io/x"}
