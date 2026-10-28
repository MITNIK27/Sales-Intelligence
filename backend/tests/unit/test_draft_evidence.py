"""Drafts may cite only verified facts: cleaned recent news and evidence-backed qualification."""

import uuid
from datetime import UTC, datetime

from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.draft.draft_generator import DraftResult
from app.modules.draft.evidence import DraftEvidence, build_draft_evidence, format_evidence
from app.modules.draft.models import DRAFT_TYPE_FIRST_TOUCH
from app.modules.draft.service import generate_draft
from app.modules.enrichment.models import ENTITY_TYPE_COMPANY, EnrichmentRecord
from app.modules.products.models import Product
from app.modules.qualification.models import QualificationResult


class _CapturingGenerator:
    model_name = "capture"

    def __init__(self) -> None:
        self.evidence: DraftEvidence | None = None

    async def generate(  # type: ignore[no-untyped-def]
        self, company, contact, products, recommendations, framing_style, draft_type, evidence=None
    ):
        self.evidence = evidence
        return DraftResult(subject="s", body="b", chosen_option=1)


async def _setup(session, organization_id):
    company = Company(
        organization_id=organization_id,
        name="DPD",
        domain=f"dpd-{uuid.uuid4()}.com",
        employee_count_range="10000+",
    )
    session.add(company)
    await session.flush()
    contact = Contact(
        organization_id=organization_id,
        company_id=company.id,
        full_name="Marc Leroy",
        seniority="director",
    )
    product = Product(organization_id=organization_id, name="Widget", description="w")
    session.add_all([contact, product])
    await session.flush()

    def signal(text: str, source: str, date: str | None):
        return EnrichmentRecord(
            organization_id=organization_id,
            entity_type=ENTITY_TYPE_COMPANY,
            entity_id=company.id,
            source=source,
            raw_payload={"signal_type": "news", "text": text, "url": "https://n/x", "date": date},
            fetched_at=datetime.now(UTC),
        )

    session.add_all(
        [
            signal("DPD opens a new automated hub in Lyon", "contextdev:signals:a", "2026-09-20"),
            signal("Track shipment", "scraper:companysite:signals:b", None),  # page chrome
        ]
    )
    session.add(
        QualificationResult(
            organization_id=organization_id,
            company_id=company.id,
            overall_verdict="qualified",
            model_used="m",
            criteria_results=[
                {
                    "criterion_name": "Operates in logistics",
                    "status": "PASS",
                    "evidence_quote": "parcel delivery network",
                },
                {"criterion_name": "Unverified", "status": "PASS", "evidence_quote": None},
                {"criterion_name": "Fails", "status": "FAIL", "evidence_quote": "x"},
            ],
        )
    )
    await session.commit()
    return company, contact, product


async def test_evidence_contains_only_clean_news_and_verified_passes(
    db_session, organization_id
) -> None:
    company, contact, _ = await _setup(db_session, organization_id)

    evidence = await build_draft_evidence(db_session, organization_id, company, contact)

    assert [s["text"] for s in evidence.signals] == ["DPD opens a new automated hub in Lyon"]
    assert evidence.signals[0]["source"] == "context.dev"
    assert evidence.qualification_points == ['Operates in logistics: "parcel delivery network"']
    assert evidence.employee_count_range == "10000+"
    assert evidence.contact_seniority == "director"


async def test_generate_draft_hands_the_evidence_to_the_generator(
    db_session, organization_id
) -> None:
    company, contact, product = await _setup(db_session, organization_id)
    generator = _CapturingGenerator()

    await generate_draft(
        db_session, organization_id, company.id, contact.id, [product.id],
        DRAFT_TYPE_FIRST_TOUCH, generator,  # type: ignore[arg-type]
    )

    assert generator.evidence is not None and not generator.evidence.is_empty
    assert generator.evidence.signals[0]["text"].startswith("DPD opens")


def test_prompt_block_lists_facts_and_forbids_inventing_others() -> None:
    block = format_evidence(
        DraftEvidence(
            signals=[
                {
                    "text": "DPD opens a hub",
                    "date": "2026-09-20",
                    "source": "context.dev",
                    "url": "u",
                }
            ],
            qualification_points=['Operates in logistics: "parcel delivery"'],
            employee_count_range="10000+",
        )
    )
    assert "the ONLY facts you may cite" in block
    assert "Recent news (2026-09-20): DPD opens a hub [context.dev]" in block
    assert "Confirmed fit: Operates in logistics" in block
    assert "AT MOST ONE" in block and "Do not state any fact" in block


def test_prompt_block_without_evidence_says_so_instead_of_inviting_invention() -> None:
    for empty in (None, DraftEvidence()):
        block = format_evidence(empty)
        assert "none available" in block and "Do not invent" in block
