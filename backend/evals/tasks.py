"""The tasks an eval can run: how to call the real code on a frozen input, and how to grade it.

`run` calls the same functions the app uses, so a result describes what the app would do.
`grade` is separate and pure, so it can be tested with canned answers, including answers from a
model that was fooled on purpose. An `expect` key a task does not know is rejected when the cases
are loaded, so a typo cannot quietly turn a check off."""

import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.modules.ai_recommendation import recommendation_generator as recommendation_module
from app.modules.ai_recommendation.recommendation_generator import RecommendationGenerator
from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.documents.knowledge import (
    KNOWLEDGE_VENDORS,
    Knowledge,
    Passage,
    generate_with_knowledge,
    pack,
)
from app.modules.draft import prompts as draft_prompts
from app.modules.draft import refine as draft_refine_module
from app.modules.draft.draft_generator import DraftGenerator
from app.modules.draft.evidence import DraftEvidence
from app.modules.enrichment.models import EnrichmentRecord
from app.modules.llm.structured import FallbackStructuredLLM, StructuredLLM
from app.modules.offerings import extractor as offering_extractor
from app.modules.opportunity import area_prompts
from app.modules.opportunity import fit as fit_module
from app.modules.opportunity import prompts as opportunity_prompts
from app.modules.opportunity import relevance as relevance_module
from app.modules.opportunity.assessment import verified_findings
from app.modules.opportunity.discovery import judge_areas, suggest_areas
from app.modules.opportunity.evidence import build_evidence_pack, format_evidence, verify_citation
from app.modules.opportunity.llm_models import AssessmentOut
from app.modules.opportunity.models import VERDICT_INSUFFICIENT, CompanyOpportunity
from app.modules.opportunity.sufficiency import decide_verdict
from app.modules.products.models import Product
from app.modules.qualification import prompts as qualification_prompts
from app.modules.qualification.evidence import evidence_sources
from app.modules.qualification.models import QualificationCriterion
from app.modules.qualification.qualification_generator import QualificationGenerator
from app.modules.quicklook import prompts as quicklook_prompts
from app.modules.quicklook.snapshot import Evidence, OfferingRef, build_summary
from app.modules.role_relevance import prompts as role_prompts
from app.modules.role_relevance.models import RoleCategory
from app.modules.role_relevance.role_relevance_generator import RoleRelevanceGenerator
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
    # Only the tasks that call these generators need them.
    recommendation: RecommendationGenerator | None = None
    role_relevance: RoleRelevanceGenerator | None = None


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


# --- passages from our documents (Phase 8d) -----------------------------------------------------


def _knowledge(data: dict[str, Any]) -> Knowledge:
    """The case's `knowledge` (passages from our documents: document, locator, text), packed exactly
    as the app packs passages from the library."""
    return pack(
        (
            Passage(k.get("document", "Our document"), k.get("locator", "Page 1"), k["text"])
            for k in data.get("knowledge", [])
        ),
        4000,
    )


def _shows_knowledge(llm: StructuredLLM) -> bool:
    """Whether this model may be shown passages from our documents (G1: Gemini only). A case about
    passages run on another model would quietly test the plain prompt, so it is failed instead."""
    if isinstance(llm, FallbackStructuredLLM):
        return not llm.restricted_to(KNOWLEDGE_VENDORS).is_empty
    return True


def _knowledge_shown(wanted: bool, case: Case, out: dict[str, Any]) -> Check:
    shown = bool(out.get("_knowledge_shown"))
    ok = shown == bool(wanted)
    detail = (
        ""
        if ok
        else (
            "the passages were not shown to the model (it is not one that may see them)"
            if wanted
            else "the passages were shown"
        )
    )
    return Check("knowledge_shown", ok, detail)


_FIGURE = re.compile(r"[$€£]?\d[\d,.]*\s?(?:%|percent|[MKB]\b|million|billion)?", re.IGNORECASE)


def _figures(text: str) -> set[str]:
    """Numbers with their unit, written the same way they are compared ("35%", "$2M")."""
    found = (m.group(0).replace(" ", "").lower().rstrip(".,") for m in _FIGURE.finditer(text or ""))
    return {figure for figure in found if figure}


# --- quicklook ----------------------------------------------------------------------------------


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
        _knowledge(data),
    ) | {"_knowledge_shown": bool(data.get("knowledge")) and _shows_knowledge(rt.llm)}


def _strong_offerings(out: dict[str, Any]) -> int:
    return sum(1 for pick in out["offerings"] if pick["band"] == "strong")


_QUICKLOOK: dict[str, Handler] = {
    "call_in": lambda v, c, o: check_one_of("call_in", o["call"], v),
    "call_not_in": lambda v, c, o: check_none_of("call_not_in", o["call"], v),
    "max_strong_offerings": lambda v, c, o: check_at_most(
        "max_strong_offerings", _strong_offerings(o), v
    ),
    "knowledge_shown": _knowledge_shown,
    "no_leak": _no_leak,
}


# --- qualification ------------------------------------------------------------------------------


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


# --- draft --------------------------------------------------------------------------------------


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


# --- draft rewrite ------------------------------------------------------------------------------


async def _run_draft_refine(case: Case, rt: Runtime) -> dict[str, Any]:
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
    result = await rt.draft.refine(
        company,
        contact,
        product,
        None,
        data.get("framing_style", "business"),
        data["draft"].get("subject"),
        data["draft"]["body"],
        data["instruction"],
    )
    return {"subject": result.subject, "body": result.body}


def _refine_claims(wanted: bool, case: Case, out: dict[str, Any]) -> Check:
    """What the rewrite may draw on: the same sources as a first draft, plus the draft it started
    from (its own earlier checked text). The rep's request is not a source for figures or
    past work."""
    if not wanted:
        return Check("no_unsupported_claims", True)
    data = case.input
    allowed = [
        *_draft_allowed(data),
        data["draft"].get("subject"),
        data["draft"]["body"],
    ]
    text = f"{out['subject'] or ''}\n{out['body']}"
    return check_no_unsupported_claims("no_unsupported_claims", text, allowed)


_DRAFT_REFINE: dict[str, Handler] = {
    "no_unsupported_claims": _refine_claims,
    "max_words": lambda v, c, o: check_at_most("max_words", len(o["body"].split()), v),
    "no_leak": _no_leak,
}


# --- offering extraction ------------------------------------------------------------------------


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


# --- shared helpers for the research tasks ------------------------------------------------------


def _need[G](generator: G | None, name: str) -> G:
    if generator is None:
        raise RuntimeError(f"this run has no {name}")
    return generator


def _records(signals: list[dict[str, Any]]) -> list[EnrichmentRecord]:
    return [
        EnrichmentRecord(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            entity_type="company",
            entity_id=uuid.uuid4(),
            source="eval",
            raw_payload={
                "signal_type": s.get("signal_type", "news"),
                "text": s["text"],
                "url": s.get("url"),
                "date": s.get("date"),
            },
            fetched_at=datetime.now(UTC),
        )
        for s in signals
    ]


def _product(data: dict[str, Any]) -> Product:
    return Product(
        name=data["name"],
        description=data.get("description"),
        kind=data.get("kind", "service"),
        buyer_profile=data.get("buyer_profile"),
    )


def _opportunity(data: dict[str, Any]) -> CompanyOpportunity:
    return CompanyOpportunity(
        area_label=data["area_label"], industry_context=data.get("industry_context")
    )


def _exact(name: str, actual: dict[str, Any], expected: dict[str, Any]) -> Check:
    """Each named item has exactly the expected value (None means "no match")."""
    missing = object()
    wrong = [
        f"{key}: expected {want!r}, got {got!r}"
        for key, want in expected.items()
        if (got := actual.get(key, missing)) != want
    ]
    return Check(name, not wrong, "; ".join(wrong).replace("<object object", "nothing (<object"))


def _forbidden(name: str, actual: dict[str, Any], forbidden: dict[str, list[Any]]) -> Check:
    bad = [
        f"{key}: {actual.get(key)!r} is not allowed"
        for key, values in forbidden.items()
        if actual.get(key) in values
    ]
    return Check(name, not bad, "; ".join(bad))


def _allowed(name: str, actual: dict[str, Any], allowed: dict[str, list[Any]]) -> Check:
    bad = [
        f"{key}: {actual.get(key)!r} is not one of {values!r}"
        for key, values in allowed.items()
        if actual.get(key) not in values
    ]
    return Check(name, not bad, "; ".join(bad))


# --- recommendation -----------------------------------------------------------------------------


async def _run_recommendation(case: Case, rt: Runtime) -> dict[str, Any]:
    data = case.input
    generator = _need(rt.recommendation, "recommendation generator")
    knowledge = _knowledge(data)
    result = await generator.generate(
        _company(data["company"]),
        [Contact(role_title=title) for title in data.get("contact_titles", [])],
        _records(data.get("signals", [])),
        _product(data["product"]),
        data.get("opportunity_context"),
        **({"knowledge": knowledge.block} if knowledge else {}),
    )
    return {
        "pitch_summary": result.pitch_summary,
        "why_this_company": result.why_this_company,
        "talking_points": list(result.talking_points),
        "_knowledge_shown": bool(knowledge),  # the recommendation is written by Gemini only
    }


def _recommendation_claims(wanted: bool, case: Case, out: dict[str, Any]) -> Check:
    if not wanted:
        return Check("no_unsupported_claims", True)
    data = case.input
    company, product = data["company"], data["product"]
    allowed = [
        company.get("description"),
        company.get("industry"),
        company.get("employee_count_range"),
        *data.get("contact_titles", []),
        *(s["text"] for s in data.get("signals", [])),
        product["name"],
        product.get("description"),
        data.get("opportunity_context"),
        # What our own documents say may be used about us (in the pitch and talking points).
        *(k["text"] for k in data.get("knowledge", [])),
    ]
    text = "\n".join([out["pitch_summary"], out["why_this_company"], *out["talking_points"]])
    return check_no_unsupported_claims("no_unsupported_claims", text, allowed)


def _knowledge_not_in_why(wanted: bool, case: Case, out: dict[str, Any]) -> Check:
    """A figure from our documents (what we did for someone else) must not be told as a fact about
    this company. "why_this_company" is about them, so no such figure may appear there unless the
    company's own input states it too."""
    if not wanted:
        return Check("knowledge_not_in_why", True)
    data = case.input
    ours = set().union(*(_figures(k["text"]) for k in data.get("knowledge", [])))
    theirs = _figures(
        " ".join(
            [
                str(data["company"].get("description") or ""),
                *(s["text"] for s in data.get("signals", [])),
                str(data.get("opportunity_context") or ""),
            ]
        )
    )
    borrowed = sorted((ours - theirs) & _figures(out["why_this_company"]))
    return Check(
        "knowledge_not_in_why",
        not borrowed,
        "" if not borrowed else f"figures from our documents told as theirs: {borrowed}",
    )


def _points_between(bounds: list[int], case: Case, out: dict[str, Any]) -> Check:
    count = len(out["talking_points"])
    low, high = bounds
    ok = low <= count <= high
    return Check(
        "talking_points_between", ok, "" if ok else f"{count} talking points, wanted {low}-{high}"
    )


_RECOMMENDATION: dict[str, Handler] = {
    "no_unsupported_claims": _recommendation_claims,
    "talking_points_between": _points_between,
    "knowledge_not_in_why": _knowledge_not_in_why,
    "knowledge_shown": _knowledge_shown,
    "no_leak": _no_leak,
}


# --- opportunity assessment ---------------------------------------------------------------------


async def _run_assessment(case: Case, rt: Runtime) -> dict[str, Any]:
    data = case.input
    company = _company(data["company"])
    items = build_evidence_pack(company, _records(data.get("evidence", [])))
    if not items:  # the app does not call a model with nothing to show it
        return {
            "verdict": VERDICT_INSUFFICIENT,
            "summary": "",
            "findings": [],
            "dropped": 0,
            "not_found": [],
        }
    prompt = opportunity_prompts.build_assessment_prompt(
        company, data["area_label"], data.get("industry_context"), format_evidence(items)
    )
    answer = await rt.llm.generate(prompt, AssessmentOut)
    findings, dropped = verified_findings(items, answer)
    return {
        "verdict": decide_verdict(findings),
        "summary": answer.summary,
        "findings": [
            {"kind": f.kind, "statement": f.statement, "evidence": f.item.label, "quote": f.quote}
            for f in findings
        ],
        "dropped": dropped,
        "not_found": list(answer.not_found),
    }


_ASSESSMENT: dict[str, Handler] = {
    "verdict_in": lambda v, c, o: check_one_of("verdict_in", o["verdict"], v),
    "verdict_not_in": lambda v, c, o: check_none_of("verdict_not_in", o["verdict"], v),
    "max_findings": lambda v, c, o: check_at_most("max_findings", len(o["findings"]), v),
    "min_findings": lambda v, c, o: Check(
        "min_findings",
        len(o["findings"]) >= v,
        f"{len(o['findings'])} findings, wanted at least {v}",
    ),
    "max_dropped": lambda v, c, o: check_at_most("max_dropped", o["dropped"], v),
    "no_leak": _no_leak,
}


# --- offering fit -------------------------------------------------------------------------------


async def _run_fit(case: Case, rt: Runtime) -> dict[str, Any]:
    data = case.input
    company = _company(data["company"])
    items = build_evidence_pack(company, _records(data.get("evidence", [])))
    products = [_product(o) for o in data["offerings"]]
    labelled = [(f"O{i}", p) for i, p in enumerate(products, start=1)]
    answers: dict[str, Any] = {}
    knowledge = _knowledge(data)
    shown = False
    if items:  # the app does not call a model with nothing to show it
        evidence_text = format_evidence(items)
        opportunity = _opportunity(data)
        plain = fit_module.build_fit_prompt(company, opportunity, evidence_text, None, labelled)
        prompt = fit_module.build_fit_prompt(
            company, opportunity, evidence_text, None, labelled, knowledge.block
        )
        out, shown = await generate_with_knowledge(
            rt.llm, prompt, plain, fit_module.FitOut, knowledge
        )
        answers = fit_module._answers_by_label(out, labelled)
        if not answers:  # the app asks once more, plainly
            out, again = await generate_with_knowledge(
                rt.llm,
                prompt + fit_module._RETRY_NOTE,
                plain + fit_module._RETRY_NOTE,
                fit_module.FitOut,
                knowledge if shown else Knowledge(),
            )
            shown = shown and again
            answers = fit_module._answers_by_label(out, labelled)
    by_label = {item.label: item for item in items}
    offerings: dict[str, dict[str, Any]] = {}
    for label, product in labelled:
        answer = answers.get(label)
        verified: set[str] = set()
        dropped = 0
        for citation in (answer.evidence if answer else [])[: fit_module._MAX_CITATIONS]:
            item = verify_citation(by_label, citation.evidence, citation.quote)
            if item is None:
                dropped += 1
            else:
                verified.add(item.identity)
        offerings[product.name] = {
            "answered": answer is not None,
            "reasoning": answer.reasoning if answer else "",
            "verified": len(verified),
            "dropped": dropped,
        }
    return {"offerings": offerings, "_knowledge_shown": shown}


def _fits(names: list[str], case: Case, out: dict[str, Any]) -> Check:
    weak = [n for n in names if out["offerings"].get(n, {}).get("verified", 0) < 1]
    return Check("fits", not weak, "" if not weak else f"no verified evidence for {weak}")


def _no_fit(names: list[str], case: Case, out: dict[str, Any]) -> Check:
    claimed = [n for n in names if out["offerings"].get(n, {}).get("verified", 0) > 0]
    return Check(
        "no_fit", not claimed, "" if not claimed else f"cites verified evidence for {claimed}"
    )


_FIT: dict[str, Handler] = {
    "fits": _fits,
    "no_fit": _no_fit,
    "max_dropped": lambda v, c, o: check_at_most(
        "max_dropped", sum(x["dropped"] for x in o["offerings"].values()), v
    ),
    "knowledge_shown": _knowledge_shown,
    "no_leak": _no_leak,
}


# --- area suggestion ----------------------------------------------------------------------------


async def _run_area_suggestion(case: Case, rt: Runtime) -> dict[str, Any]:
    """Proposes areas from the frozen evidence and judges which offering serves each, exactly as
    the app does (`suggest_areas` then `judge_areas`), with the case's passages when it has any."""
    data = case.input
    company = _company(data["company"])
    knowledge = _knowledge(data)
    focus = list(data.get("focus", []))
    proposed = await suggest_areas(
        rt.llm,
        company,
        _records(data.get("evidence", [])),
        list(data.get("areas_we_cover", [])),
        data.get("industry_context"),
        focus=focus,
        knowledge=knowledge,
    )
    catalogue = [
        (o["name"], list((o.get("buyer_profile") or {}).get("area_tags", [])))
        for o in data.get("offerings", [])
    ]
    judged = (
        await judge_areas(rt.llm, company, proposed, catalogue, focus, knowledge)
        if proposed
        else []
    )
    return {
        "areas": [
            {
                "label": a.label,
                "reason": a.reason,
                "offering": a.offering,
                "support": a.support,
                "quote": a.quote,
                "cited": [r["label"] for r in a.knowledge_refs],
            }
            for a in judged
        ],
        "_knowledge_shown": bool(knowledge) and _shows_knowledge(rt.llm),
    }


def _area_words(out: dict[str, Any]) -> list[str]:
    return [a["label"].lower() for a in out["areas"]]


def _areas_include(words: list[str], case: Case, out: dict[str, Any]) -> Check:
    labels = _area_words(out)
    missing = [w for w in words if not any(w.lower() in label for label in labels)]
    return Check(
        "areas_include", not missing, "" if not missing else f"no area about {missing}: {labels}"
    )


def _areas_exclude(words: list[str], case: Case, out: dict[str, Any]) -> Check:
    found = [label for label in _area_words(out) if any(w.lower() in label for w in words)]
    return Check("areas_exclude", not found, "" if not found else f"should not suggest {found}")


def _offerings_include(names: list[str], case: Case, out: dict[str, Any]) -> Check:
    used = {a["offering"] for a in out["areas"] if a["offering"]}
    missing = [n for n in names if n not in used]
    return Check(
        "offerings_include",
        not missing,
        "" if not missing else f"no area is served by {missing} (used: {sorted(used)})",
    )


def _offerings_exclude(names: list[str], case: Case, out: dict[str, Any]) -> Check:
    wrong = sorted({a["offering"] for a in out["areas"]} & set(names))
    return Check("offerings_exclude", not wrong, "" if not wrong else f"areas served by {wrong}")


_AREA_SUGGESTION: dict[str, Handler] = {
    "areas_include": _areas_include,
    "areas_exclude": _areas_exclude,
    "max_areas": lambda v, c, o: check_at_most("max_areas", len(o["areas"]), v),
    "offerings_include": _offerings_include,
    "offerings_exclude": _offerings_exclude,
    "knowledge_shown": _knowledge_shown,
    "no_leak": _no_leak,
}


# --- contact relevance --------------------------------------------------------------------------


async def _run_contact_relevance(case: Case, rt: Runtime) -> dict[str, Any]:
    data = case.input
    labelled = [
        (
            f"C{i}",
            c["id"],
            Contact(id=uuid.uuid4(), role_title=c.get("role_title"), seniority=c.get("seniority")),
        )
        for i, c in enumerate(data["contacts"], start=1)
    ]
    product = _product(data["product"]) if data.get("product") else None
    prompt = relevance_module.build_relevance_prompt(
        _company(data["company"]),
        _opportunity(data),
        product,
        [(label, contact) for label, _, contact in labelled],
    )
    out = await rt.llm.generate(prompt, relevance_module.RelevanceOut)
    answers = {a.contact.strip(): a for a in out.contacts}
    roles: dict[str, str] = {}
    reasoning: dict[str, str] = {}
    for label, key, _ in labelled:
        answer = answers.get(label)
        roles[key] = relevance_module._clean_role(answer.role) if answer else "not_assessed"
        reasoning[key] = answer.reasoning if answer else ""
    return {"roles": roles, "reasoning": reasoning}


_CONTACT_RELEVANCE: dict[str, Handler] = {
    "roles_in": lambda v, c, o: _allowed("roles_in", o["roles"], v),
    "roles_not": lambda v, c, o: _forbidden("roles_not", o["roles"], v),
    "no_leak": _no_leak,
}


# --- role relevance -----------------------------------------------------------------------------


async def _run_role_relevance(case: Case, rt: Runtime) -> dict[str, Any]:
    data = case.input
    generator = _need(rt.role_relevance, "role relevance generator")
    categories = [
        RoleCategory(
            id=uuid.uuid4(),
            name=c["name"],
            description=c.get("description"),
            is_primary_target=bool(c.get("is_primary_target", False)),
            framing_style="business",
            is_active=True,
        )
        for c in data["categories"]
    ]
    contacts = [
        Contact(id=uuid.uuid4(), role_title=c.get("role_title"), seniority=c.get("seniority"))
        for c in data["contacts"]
    ]
    judgment = await generator.generate(_company(data["company"]), contacts, categories)
    names = {str(category.id): category.name for category in categories}
    keys = {str(contact.id): c["id"] for contact, c in zip(contacts, data["contacts"], strict=True)}
    matches: dict[str, str | None] = {}
    reasoning: dict[str, str] = {}
    for verdict in judgment.contact_results:
        key = keys.get(verdict.contact_id)
        if key is None:
            continue
        category_id = verdict.matched_category_id
        matches[key] = names.get(category_id, "unknown category") if category_id else None
        reasoning[key] = verdict.reasoning
    missing = [c["id"] for c in data["contacts"] if c["id"] not in matches]
    return {"matches": matches, "reasoning": reasoning, "missing": missing}


_ROLE_RELEVANCE: dict[str, Handler] = {
    "matches": lambda v, c, o: _exact("matches", o["matches"], v),
    "matches_not": lambda v, c, o: _forbidden("matches_not", o["matches"], v),
    "all_answered": lambda v, c, o: Check(
        "all_answered",
        (not o["missing"]) == bool(v),
        f"no answer for {o['missing']}" if o["missing"] else "",
    ),
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
    "draft_refine": Task(
        "draft_refine",
        draft_refine_module.REFINE_PROMPT_VERSION,
        ("company", "contact", "product", "draft", "instruction"),
        _run_draft_refine,
        _DRAFT_REFINE,
    ),
    "offering_extraction": Task(
        "offering_extraction",
        offering_extractor.PROMPT_VERSION,
        ("url", "text"),
        _run_offering_extraction,
        _OFFERING_EXTRACTION,
    ),
    "recommendation": Task(
        "recommendation",
        recommendation_module.PROMPT_VERSION,
        ("company", "product"),
        _run_recommendation,
        _RECOMMENDATION,
    ),
    "opportunity_assessment": Task(
        "opportunity_assessment",
        opportunity_prompts.PROMPT_VERSION,
        ("company", "area_label", "evidence"),
        _run_assessment,
        _ASSESSMENT,
    ),
    "offering_fit": Task(
        "offering_fit",
        fit_module.FIT_PROMPT_VERSION,
        ("company", "area_label", "evidence", "offerings"),
        _run_fit,
        _FIT,
    ),
    "contact_relevance": Task(
        "contact_relevance",
        relevance_module.RELEVANCE_PROMPT_VERSION,
        ("company", "area_label", "contacts"),
        _run_contact_relevance,
        _CONTACT_RELEVANCE,
    ),
    "area_suggestion": Task(
        "area_suggestion",
        area_prompts.AREA_PROMPT_VERSION,
        ("company", "evidence"),
        _run_area_suggestion,
        _AREA_SUGGESTION,
    ),
    "role_relevance": Task(
        "role_relevance",
        role_prompts.PROMPT_VERSION,
        ("company", "contacts", "categories"),
        _run_role_relevance,
        _ROLE_RELEVANCE,
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
