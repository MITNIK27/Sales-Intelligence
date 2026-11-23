"""Prompts for suggesting opportunity areas, and for judging which offering serves each one.

They state the rules the checking code enforces afterwards; the code does not rely on the model
following them: every area's quote is verified against the evidence it cites, and an offering name
that is not one of ours is dropped.

Passages from our own documents (Phase 8d) may be added to either prompt. They describe what our
offerings do and have delivered, so the model can see where we can really help and pick the right
offering for an area. They are never evidence about the company: an area still needs a verified
quote from the company's own research. Without passages each prompt is word for word what it was
before Phase 8d (then in `prompts.py` under the assessment's version)."""

from app.modules.companies.models import Company
from app.modules.llm.untrusted import untrusted_aware, wrap_untrusted
from app.modules.opportunity.prompts import _GROUND_RULES, _company_block

# Bump when either prompt changes; stored on the suggested areas it produces (G9).
AREA_PROMPT_VERSION = "v1"


def _knowledge_section(knowledge_block: str, use: str) -> str:
    if not knowledge_block:
        return ""
    return (
        "\n\nWhat our own documents say about our offerings (internal material: "
        f"{use}; it is NOT evidence about the company and never a reason on its own; when a "
        "passage shaped your answer, name its label, for example [K2]):\n"
        f"{knowledge_block}"
    )


@untrusted_aware
def build_area_prompt(
    company: Company,
    industry: str | None,
    evidence_text: str,
    offering_areas: list[str],
    focus: list[str] | None = None,
    widen: bool = False,
    knowledge_block: str = "",
) -> str:
    """`focus` names the offerings the person is looking at (searched in Market Discovery or chosen
    on the Brief). By default areas close to them come first; with `widen` the focus offerings have
    already been looked at and did not fit well, so the next best areas elsewhere are wanted."""
    offered = ", ".join(offering_areas) if offering_areas else "not specified"
    if focus and widen:
        steer = (
            f"The person was looking at: {', '.join(focus)}. The evidence did not show a good "
            "fit for those, so do NOT limit yourself to them: suggest the best-supported areas "
            "where any of our offerings could help."
        )
    elif focus:
        steer = (
            f"The person is looking at: {', '.join(focus)}. Prefer areas where the company's "
            "activity connects to those offerings, and name the offering in the reason. Still "
            "only suggest an area the evidence supports."
        )
    else:
        steer = "No offering is singled out."
    knowledge = _knowledge_section(
        knowledge_block,
        "use it to see where we have really helped companies like this one and to name the area "
        "in words we use",
    )
    return f"""You are looking for business areas where a company shows real activity, so a \
salesperson can decide where to start a conversation.

{_company_block(company, industry)}

Areas our company can help with, for reference: {offered}.
{steer}{knowledge}

{_GROUND_RULES}
- Suggest an area only when the evidence shows activity in it. An area that merely matches what we \
sell, with no supporting evidence, must not be suggested.
- Prefer a few well-supported areas over many weak ones. At most 5.

Evidence:
{wrap_untrusted(evidence_text, "evidence")}

Return areas, each with a short label (for example "cloud migration"), one sentence on why the \
evidence points to it (say what the company is doing and, where one of the areas we can help with \
fits, name it), the evidence label and a verbatim quote. Return an empty list if the \
evidence does not support any area."""


@untrusted_aware
def build_area_judgement_prompt(
    company: Company,
    candidates: list[tuple[str, str, str]],
    offerings: list[tuple[str, list[str]]],
    focus: list[str],
    knowledge_block: str = "",
) -> str:
    """Second look at areas already proposed: which of our offerings each one is best served by,
    and how well the evidence behind it supports that. `candidates` are (label, reason, quote)."""
    listed = "\n".join(
        f'- {label}: {reason} Evidence quote: "{quote}"' for label, reason, quote in candidates
    )
    catalogue = "\n".join(
        f"- {name}" + (f" (areas: {', '.join(tags)})" if tags else "") for name, tags in offerings
    )
    wanted = f"The offerings the person is looking at are: {', '.join(focus)}.\n" if focus else ""
    knowledge = _knowledge_section(
        knowledge_block,
        "use it to tell which offering really does the kind of work each area needs",
    )
    sources_rule = (
        ' Also return "sources": the labels of the passages from our documents that decided the '
        "offering (empty when none did)."
        if knowledge_block
        else ""
    )
    return f"""You are checking proposed business areas for {company.name} against what our \
company sells.

{wanted}Our offerings:
{catalogue}{knowledge}

Proposed areas (each already has its evidence quote):
{wrap_untrusted(listed, "candidates")}

For EVERY proposed area return: label (exactly as given), offering (the name of the ONE offering \
from the list above that serves it best, or empty if none does) and support: "clear" when the \
quote shows the company doing the kind of work that offering serves, "partial" when it is related \
but indirect, "none" when the offering would not help. Do not invent offerings and do not add \
areas.{sources_rule}"""
