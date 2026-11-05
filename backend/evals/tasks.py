"""The tasks an eval can run: how to call the real code on a frozen input, and how to grade it.

`run` calls the same functions the app uses, so a result describes what the app would do.
`grade` is separate and pure, so it can be tested with canned answers, including answers from a
model that was fooled on purpose. An `expect` key a task does not know is rejected when the cases
are loaded, so a typo cannot quietly turn a check off."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.draft import prompts as draft_prompts
from app.modules.draft.draft_generator import DraftGenerator
from app.modules.draft.evidence import DraftEvidence
from app.modules.enrichment.models import EnrichmentRecord
from app.modules.llm.structured import StructuredLLM
from app.modules.offerings import extractor as offering_extractor
from app.modules.products.models import Product
from app.modules.qualification import prompts as qualification_prompts
from app.modules.qualification.evidence import evidence_sources
from app.modules.qualification.models import QualificationCriterion
from app.modules.qualification.qualification_generator import QualificationGenerator
from app.modules.quicklook import prompts as quicklook_prompts
from app.modules.quicklook.snapshot import Evidence, OfferingRef, build_summary
from evals.cases import Case, CaseError
from evals.graders import (
    Check,
    check_at_most,
    check_equal,
    check_no_leak,
    check_no_unsupported_claims,
    check_none_of,
    check_one_of,
    check_quotes_in_evidence,
    check_verdicts,
)


@dataclass
class Runtime:
    """What a run needs to call a model. `model` is the name that goes on the report."""

    llm: StructuredLLM
    qualification: QualificationGenerator
    draft: DraftGenerator
    model: str


Handler = Callable[[Any, Case, dict[str, Any]], Check]


@dataclass(frozen=True)
class Task:
    name: str
    prompt_version: str
    required_input: tuple[str, ...]
    run: Callable[[Case, Runtime], Awaitable[dict[str, Any]]]
    handlers: dict[str, Handler]

    def grade(self, case: Case, output: dict[str, Any]) -> list[Check]:
        return [self.handlers[key](value, case, output) for key, value in case.expect.items()]


def _all_text(value: object) -> str:
    """Every string in an answer, joined, so a planted phrase is found wherever it ended up. Keys
    starting with an underscore hold the frozen input and are skipped."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(_all_text(v) for k, v in value.items() if not str(k).startswith("_"))
    if isinstance(value, list | tuple):
        return "\n".join(_all_text(v) for v in value)
    return ""


def _no_leak(phrases: list[str], case: Case, out: dict[str, Any]) -> Check:
    return check_no_leak("no_leak", _all_text(out), phrases)


# --- quicklook -------------------------------------------------------------------------------


async def _run_quicklook(case: Case, rt: Runtime) -> dict[str, Any]:
    data = case.input
    evidence = [
        Evidence(e["label"], e["url"], e["kind"], e["text"], e.get("date"))
        for e in data["evidence"]
    ]
    offerings = [
        OfferingRef(o["label"], f"eval-{o['label']}", o["name"], o["description"])
        for o in data["offerings"]
    ]
    return await build_summary(
        rt.llm,
        data["name"],
        data["domain"],
        evidence,
        offerings,
        data.get("criteria") or [],
        data.get("focus"),
    )


def _strong_offerings(out: dict[str, Any]) -> int:
    return sum(1 for pick in out["offerings"] if pick["band"] == "strong")


_QUICKLOOK: dict[str, Handler] = {
    "call_in": lambda v, c, o: check_one_of("call_in", o["call"], v),
    "call_not_in": lambda v, c, o: check_none_of("call_not_in", o["call"], v),
    "max_strong_offerings": lambda v, c, o: check_at_most(
        "max_strong_offerings", _strong_offerings(o), v
    ),
    "no_leak": _no_leak,
}


# --- qualification ---------------------------------------------------------------------------


def _company(data: dict[str, Any]) -> Company:
    return Company(
        name=data["name"],
        domain=data.get("domain"),
        industry=data.get("industry"),
        employee_count_range=data.get("employee_count_range"),
        description=data.get("description"),
    )


async def _run_qualification(case: Case, rt: Runtime) -> dict[str, Any]:
    data = case.input
    company = _company(data["company"])
    signals = [
        EnrichmentRecord(
            organization_id=uuid.uuid4(),
            entity_type="company",
            entity_id=uuid.uuid4(),
            source="eval",
            raw_payload={"signal_type": s.get("signal_type", "news"), "text": s["text"]},
            fetched_at=datetime.now(UTC),
        )
        for s in data.get("signals", [])
    ]
    criteria = [
        QualificationCriterion(
            id=uuid.uuid4(),
            name=c["name"],
            description=c.get("description"),
            is_disqualifying=bool(c.get("is_disqualifying", False)),
            is_active=True,
        )
        for c in data["criteria"]
    ]
    judgment = await rt.qualification.generate(company, signals, criteria, data.get("focus"))
    names = {str(c.id): c.name for c in criteria}
    verdicts: dict[str, str] = {}
    quotes: list[dict[str, str]] = []
    reasoning: dict[str, str] = {}
    for item in judgment.criteria_results:
        name = names.get(item.criterion_id, item.criterion_id)
        verdicts[name] = item.verdict
        reasoning[name] = item.reasoning
        if item.verdict != "could_not_determine" and item.evidence_ref and item.evidence_quote:
            quotes.append(
                {"criterion": name, "ref": item.evidence_ref, "quote": item.evidence_quote}
            )
    return {
        "verdicts": verdicts,
        "quotes": quotes,
        "reasoning": reasoning,
        "_sources": evidence_sources(company, signals),
    }


def _verdicts_not(forbidden: dict[str, list[str]], case: Case, out: dict[str, Any]) -> Check:
    bad = [
        f"{name}: {out['verdicts'].get(name)!r} is not allowed"
        for name, verdicts in forbidden.items()
        if out["verdicts"].get(name) in verdicts
    ]
    return Check("verdicts_not", not bad, "; ".join(bad))


def _quotes_valid(wanted: bool, case: Case, out: dict[str, Any]) -> Check:
    if not wanted:
        return Check("quotes_valid", True)
    quotes = [(q["ref"], q["quote"]) for q in out["quotes"]]
    return check_quotes_in_evidence("quotes_valid", quotes, out["_sources"])


_QUALIFICATION: dict[str, Handler] = {
    "verdicts": lambda v, c, o: check_verdicts("verdicts", o["verdicts"], v),
    "verdicts_not": _verdicts_not,
    "quotes_valid": _quotes_valid,
    "no_leak": _no_leak,
}


# --- draft ---------------------------------------------------------------------------------------


async def _run_draft(case: Case, rt: Runtime) -> dict[str, Any]:
    data = case.input
    company = _company(data["company"])
    contact = Contact(
        full_name=data["contact"]["first_name"],
        role_title=data["contact"].get("role_title"),
        seniority=data["contact"].get("seniority"),
    )
    product = Product(
        name=data["product"]["name"],
        description=data["product"].get("description"),
        kind=data["product"].get("kind", "service"),
    )
    raw = data.get("evidence", {})
    evidence = DraftEvidence(
        signals=raw.get("signals", []),
        qualification_points=raw.get("qualification_points", []),
        employee_count_range=raw.get("employee_count_range"),
        contact_seniority=data["contact"].get("seniority"),
    )
    result = await rt.draft.generate(
        company,
        contact,
        [product],
        [None],
        data.get("framing_style", "business"),
        data.get("draft_type", "first_touch"),
        evidence,
    )
    return {"subject": result.subject, "body": result.body}


def _draft_allowed(data: dict[str, Any]) -> list[str | None]:
    """What the draft was allowed to draw on, as the real service builds it."""
    company, product = data["company"], data["product"]
    raw = data.get("evidence", {})
    return [
        company.get("description"),
        company.get("industry"),
        company.get("employee_count_range"),
        product["name"],
        product.get("description"),
        *(str(s.get("text") or "") for s in raw.get("signals", [])),
        *raw.get("qualification_points", []),
        raw.get("employee_count_range"),
    ]


def _draft_claims(wanted: bool, case: Case, out: dict[str, Any]) -> Check:
    if not wanted:
        return Check("no_unsupported_claims", True)
    text = f"{out['subject'] or ''}\n{out['body']}"
    return check_no_unsupported_claims("no_unsupported_claims", text, _draft_allowed(case.input))


_DRAFT: dict[str, Handler] = {
    "no_unsupported_claims": _draft_claims,
    "max_words": lambda v, c, o: check_at_most("max_words", len(o["body"].split()), v),
    "no_leak": _no_leak,
}


# --- offering extraction -------------------------------------------------------------------------


async def _run_offering_extraction(case: Case, rt: Runtime) -> dict[str, Any]:
    data = case.input
    found = await offering_extractor.extract_offering(
        rt.llm, data["url"], data["text"], forced=bool(data.get("forced", False))
    )
    if found is None:
        return {"is_offering": False, "kind": None, "name": None, "description": None}
    return {
        "is_offering": True,
        "kind": found.kind,
        "name": found.name,
        "description": found.description,
    }


def _name_contains(part: str, case: Case, out: dict[str, Any]) -> Check:
    ok = part.lower() in (out["name"] or "").lower()
    return Check("name_contains", ok, "" if ok else f"{part!r} is not in {out['name']!r}")


def _no_figures(wanted: bool, case: Case, out: dict[str, Any]) -> Check:
    if not wanted:
        return Check("no_figures", True)
    return check_no_unsupported_claims("no_figures", out["description"] or "", [])


_OFFERING_EXTRACTION: dict[str, Handler] = {
    "is_offering": lambda v, c, o: check_equal("is_offering", o["is_offering"], v),
    "kind": lambda v, c, o: check_equal("kind", o["kind"], v),
    "name_contains": _name_contains,
    "no_figures": _no_figures,
    "no_leak": _no_leak,
}


TASKS: dict[str, Task] = {
    "quicklook": Task(
        "quicklook",
        quicklook_prompts.PROMPT_VERSION,
        ("name", "domain", "evidence", "offerings"),
        _run_quicklook,
        _QUICKLOOK,
    ),
    "qualification": Task(
        "qualification",
        qualification_prompts.PROMPT_VERSION,
        ("company", "criteria"),
        _run_qualification,
        _QUALIFICATION,
    ),
    "draft": Task(
        "draft",
        draft_prompts.PROMPT_VERSION,
        ("company", "contact", "product"),
        _run_draft,
        _DRAFT,
    ),
    "offering_extraction": Task(
        "offering_extraction",
        offering_extractor.PROMPT_VERSION,
        ("url", "text"),
        _run_offering_extraction,
        _OFFERING_EXTRACTION,
    ),
}


def validate_cases(cases: list[Case]) -> None:
    """Every case names a task that exists, only uses expectations that task understands, and has
    the input that task needs. Raises `CaseError` naming the case."""
    for case in cases:
        task = TASKS.get(case.task)
        if task is None:
            raise CaseError(f"{case.id}: no task named {case.task!r} is registered")
        unknown = set(case.expect) - set(task.handlers)
        if unknown:
            raise CaseError(
                f"{case.id}: {case.task} does not understand {sorted(unknown)} "
                f"(it understands {sorted(task.handlers)})"
            )
        missing = [key for key in task.required_input if key not in case.input]
        if missing:
            raise CaseError(f"{case.id}: {case.task} needs input {missing}")
