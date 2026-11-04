"""What the language model is asked to return. Everything it returns is a proposal: each citation
is checked against the stored evidence before anything is kept (see `assessment.py`)."""

from pydantic import BaseModel


class FindingOut(BaseModel):
    kind: str  # initiative | hiring | news | partnership | technology
    statement: str  # one plain sentence about what the company is doing in the area
    evidence: str  # the label of the evidence it rests on, for example E3
    quote: str  # a short verbatim quote from that evidence


class AssessmentOut(BaseModel):
    summary: str
    findings: list[FindingOut] = []
    # What was looked for in the evidence and not found, so a gap is stated rather than hidden.
    not_found: list[str] = []


class AreaOut(BaseModel):
    label: str  # a short opportunity area, for example "cloud migration"
    reason: str  # one sentence on why the evidence points to it
    evidence: str  # the label of the evidence it rests on
    quote: str  # a short verbatim quote from that evidence


class AreaSuggestionsOut(BaseModel):
    areas: list[AreaOut] = []
