"""Evidence enforcement: a PASS/FAIL must be backed by a quote that really exists in the data."""

import uuid

from app.modules.companies.models import Company
from app.modules.enrichment.models import EnrichmentRecord
from app.modules.qualification.evidence import (
    overall_confidence,
    quote_is_in_source,
    status_for_verdict,
)
from app.modules.qualification.models import QualificationCriterion
from app.modules.qualification.qualification_generator import (
    CriterionVerdict,
    QualificationJudgment,
    enforce_evidence,
)
from app.modules.qualification.service import build_run_criteria, judge_qualification


def _company() -> Company:
    return Company(
        name="DPD",
        domain="dpd.com",
        industry="Logistics & Supply Chain",
        employee_count_range="10000+",
        description="DPD is a parcel delivery network operating across Europe.",
    )


def _signal(text: str, source: str = "contextdev:signals:x") -> EnrichmentRecord:
    return EnrichmentRecord(
        entity_type="company",
        entity_id=uuid.uuid4(),
        source=source,
        raw_payload={"signal_type": "news", "text": text, "url": "https://n.example/a"},
    )


def _verdict(**kw: object) -> QualificationJudgment:
    base: dict[str, object] = {"criterion_id": "c1", "verdict": "met", "reasoning": "r"}
    base.update(kw)
    return QualificationJudgment(criteria_results=[CriterionVerdict(**base)])  # type: ignore[arg-type]


def test_status_vocabulary() -> None:
    assert status_for_verdict("met") == "PASS"
    assert status_for_verdict("not_met") == "FAIL"
    assert status_for_verdict("could_not_determine") == "UNKNOWN"


def test_quote_matching_ignores_case_and_whitespace_and_supports_ellipsis() -> None:
    source = "DPD is a parcel   delivery network operating across Europe."
    assert quote_is_in_source("parcel delivery NETWORK", source)
    assert quote_is_in_source("DPD is ... across Europe", source)
    assert not quote_is_in_source("...", source)
    assert not quote_is_in_source("fleet of 4,000 vans", source)


def test_supported_pass_is_kept() -> None:
    out = enforce_evidence(
        _verdict(
            evidence_ref="company.description",
            evidence_quote="parcel delivery network",
            confidence=1.4,
        ),
        _company(),
        [],
    )
    item = out.criteria_results[0]
    assert item.verdict == "met"
    assert item.confidence == 1.0  # clamped


def test_pass_without_evidence_becomes_unknown() -> None:
    item = enforce_evidence(_verdict(), _company(), []).criteria_results[0]
    assert item.verdict == "could_not_determine"
    assert "no evidence was cited" in item.reasoning


def test_invented_quote_becomes_unknown() -> None:
    item = enforce_evidence(
        _verdict(evidence_ref="company.description", evidence_quote="operates 4,000 vans"),
        _company(),
        [],
    ).criteria_results[0]
    assert item.verdict == "could_not_determine"
    assert item.evidence_quote is None


def test_unknown_source_reference_becomes_unknown() -> None:
    item = enforce_evidence(
        _verdict(verdict="not_met", evidence_ref="S9", evidence_quote="anything"),
        _company(),
        [_signal("DPD opens a new hub")],
    ).criteria_results[0]
    assert item.verdict == "could_not_determine"


def test_signal_citation_is_verified_against_that_signal() -> None:
    signals = [_signal("DPD opens a new automated hub in Lyon")]
    ok = enforce_evidence(
        _verdict(evidence_ref="S1", evidence_quote="new automated hub"), _company(), signals
    )
    assert ok.criteria_results[0].verdict == "met"


async def test_snapshot_records_status_evidence_and_source() -> None:
    criterion = QualificationCriterion(
        id=uuid.uuid4(), name="Digital", description=None, is_disqualifying=False, is_active=True
    )
    signals = [_signal("DPD opens a new automated hub in Lyon")]

    class _Gen:
        model_name = "fake"

        async def generate(self, company, sigs, criteria):  # type: ignore[no-untyped-def]
            return QualificationJudgment(
                criteria_results=[
                    CriterionVerdict(
                        criterion_id=str(criteria[0].id),
                        verdict="met",
                        reasoning="automation",
                        evidence_ref="S1",
                        evidence_quote="automated hub",
                        confidence=0.8,
                    )
                ]
            )

    _, results = await judge_qualification(_company(), signals, [criterion], _Gen())  # type: ignore[arg-type]
    entry = results[0]
    assert entry["status"] == "PASS"
    assert entry["source"] == "context.dev news"
    assert entry["url"] == "https://n.example/a"
    assert entry["confidence"] == 0.8


def test_overall_confidence_is_the_weakest_hard_criterion() -> None:
    results = [
        {"is_disqualifying": True, "confidence": 0.9},
        {"is_disqualifying": True, "confidence": 0.6},
        {"is_disqualifying": False, "confidence": 0.1},
        {"is_disqualifying": True, "confidence": None},
    ]
    assert overall_confidence(results) == 0.6
    assert overall_confidence([{"is_disqualifying": True}]) is None


def test_run_criteria_are_hard_transient_and_skip_blank_names() -> None:
    org = uuid.uuid4()
    criteria = build_run_criteria(
        org,
        [
            {"name": "Operates in logistics", "description": "parcel / freight"},
            {"name": "   "},
        ],
    )
    assert len(criteria) == 1
    assert criteria[0].is_disqualifying is True
    assert criteria[0].description == "parcel / freight"
    assert build_run_criteria(org, None) == []
