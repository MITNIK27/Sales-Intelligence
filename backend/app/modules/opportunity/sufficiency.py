"""When is the evidence enough? Decided here, in plain code, never by the model.

The model proposes findings and cites evidence; this module decides which findings stand and what
verdict the set of them earns. The rules are deliberately conservative: a company's own
description says what it is, not what it is doing, so it can never lift a verdict above "weak" on
its own, and a hiring claim needs an actual job posting. Below the thresholds the answer is
"insufficient evidence", and the screen says what was looked for and not found."""

from dataclasses import dataclass

from app.modules.opportunity.evidence import KIND_COMPANY_FIELD, EvidenceItem
from app.modules.opportunity.models import (
    VERDICT_EMERGING,
    VERDICT_INSUFFICIENT,
    VERDICT_SUPPORTED,
    VERDICT_WEAK,
)

FINDING_KINDS = ("initiative", "hiring", "news", "partnership", "technology")

# Findings backed by activity evidence (news, postings, searches), and how many distinct pieces of
# evidence they rest on.
SUPPORTED_MIN_FINDINGS = 3
SUPPORTED_MIN_RECORDS = 3
EMERGING_MIN_FINDINGS = 2
EMERGING_MIN_RECORDS = 2

JOB_POSTING = "job_posting"


@dataclass(frozen=True)
class VerifiedFinding:
    kind: str
    statement: str
    item: EvidenceItem
    quote: str


def kind_fits_evidence(kind: str, item: EvidenceItem) -> bool:
    """A claim must be the kind of thing its evidence can show: hiring needs a job posting, and
    nothing else may be called hiring."""
    if kind not in FINDING_KINDS:
        return False
    if kind == "hiring":
        return item.kind == JOB_POSTING
    return True


def decide_verdict(findings: list[VerifiedFinding]) -> str:
    activity = [f for f in findings if f.item.kind != KIND_COMPANY_FIELD]
    records = {f.item.identity for f in activity}
    if len(activity) >= SUPPORTED_MIN_FINDINGS and len(records) >= SUPPORTED_MIN_RECORDS:
        return VERDICT_SUPPORTED
    if len(activity) >= EMERGING_MIN_FINDINGS and len(records) >= EMERGING_MIN_RECORDS:
        return VERDICT_EMERGING
    if findings:
        return VERDICT_WEAK
    return VERDICT_INSUFFICIENT
