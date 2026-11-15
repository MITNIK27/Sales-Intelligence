"""Prompts for opportunity research. They state the rules the checking code later enforces, but
the code does not depend on the model following them: every citation is verified afterwards."""

from app.modules.companies.models import Company
from app.modules.llm.untrusted import untrusted_aware, wrap_untrusted
from app.modules.opportunity.sufficiency import FINDING_KINDS

# Bump when a prompt changes in a way that should invalidate earlier assessments (it is part of
# the cache key, so a new version judges the same evidence again).
PROMPT_VERSION = "v2"

_GROUND_RULES = """Ground rules:
- Use ONLY the numbered evidence below. Do not use anything you know about this company from \
elsewhere.
- Cite the evidence by its label (for example E3) and give a short VERBATIM quote from it. A claim \
whose quote is not in the cited evidence will be discarded.
- Never infer buying intent, budget, or an initiative the evidence does not state. A company \
description says what a company is, not what it is doing.
- If the evidence does not support something, leave it out."""


def _company_block(company: Company, industry: str | None) -> str:
    return (
        f"Company: {company.name}\n"
        f"Website: {company.domain or 'unknown'}\n"
        f"Industry: {industry or company.industry or 'unknown'}"
    )


@untrusted_aware
def build_assessment_prompt(
    company: Company, area_label: str, industry: str | None, evidence_text: str
) -> str:
    kinds = ", ".join(FINDING_KINDS)
    return f"""You are checking what a company is actually doing in one business area, so a \
salesperson can judge whether it is worth approaching about it.

{_company_block(company, industry)}
Business area to assess: {area_label}

{_GROUND_RULES}
- Each finding has a kind, one of: {kinds}. Use "hiring" only for evidence that is a job posting.

Evidence:
{wrap_untrusted(evidence_text, "evidence")}

Return:
- summary: two plain sentences on what the evidence shows about this company in this area. If it \
shows little, say so plainly.
- findings: each with kind, a one-sentence statement, the evidence label and a verbatim quote.
- not_found: things you looked for in the evidence about this area and did not find (for example \
"no job postings", "no announcement of a programme")."""


@untrusted_aware
def build_area_prompt(
    company: Company, industry: str | None, evidence_text: str, offering_areas: list[str]
) -> str:
    offered = ", ".join(offering_areas) if offering_areas else "not specified"
    return f"""You are looking for business areas where a company shows real activity, so a \
salesperson can decide where to start a conversation.

{_company_block(company, industry)}

Areas our company can help with, for reference: {offered}.

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
