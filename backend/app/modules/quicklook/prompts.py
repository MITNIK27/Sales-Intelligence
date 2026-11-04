"""The Quick Look prompt. It states the rules the checking code enforces afterwards; the code does
not rely on the model following them."""

from pydantic import BaseModel

from app.modules.llm.untrusted import untrusted_aware, wrap_untrusted

# Bump when the prompt changes in a way that should make old snapshots stale.
PROMPT_VERSION = "v4"

BANDS = ("strong", "potential", "weak")
VERDICTS = ("met", "not_met", "unknown")


class OfferingPickOut(BaseModel):
    offering: str  # offering label, for example O2
    band: str  # strong | potential | weak
    reason: str  # one sentence: why this offering could help them, or why not much
    evidence: str | None = None  # evidence label, for example E1
    quote: str | None = None  # a short verbatim quote from that evidence
    idea: str | None = None  # one sentence: what we would offer them and how
    why_now: str | None = None  # one sentence: which of their moves this builds on


class WorkingOnOut(BaseModel):
    point: str  # one short sentence: something they are doing in an area we sell in
    evidence: str | None = None
    quote: str | None = None  # a short verbatim quote from that evidence


class CriterionAnswerOut(BaseModel):
    criterion: str  # criterion label, for example C1
    verdict: str  # met | not_met | unknown
    reason: str  # one sentence
    evidence: str | None = None
    quote: str | None = None


class QuickLookOut(BaseModel):
    company_name: str
    what_they_do: str  # two or three plain sentences
    industry: str | None = None
    size_hint: str | None = None  # only if the evidence states it
    relevance: str  # two or three plain sentences on how this relates to what we sell
    call: str  # yes | maybe | no | unclear
    call_reason: str  # one sentence
    working_on: list[WorkingOnOut] = []
    offerings: list[OfferingPickOut] = []
    criteria: list[CriterionAnswerOut] = []


@untrusted_aware
def build_quicklook_prompt(
    name: str,
    domain: str,
    evidence_text: str,
    offerings_text: str,
    criteria_text: str = "",
    focus: str | None = None,
) -> str:
    focus_rule = (
        f'- The person wants to know about this area: "{focus}". In "relevance", say what the '
        "evidence shows about the company in that area, and judge the offerings with it in mind.\n"
        if focus
        else ""
    )
    criteria_rule = (
        '- "criteria": the person\'s own questions, listed below. For each, give a verdict of met, '
        "not_met or unknown, one sentence, and a VERBATIM quote with its evidence label for met or "
        "not_met. Use unknown when the evidence does not say. These are for information only and "
        'must not change "call".\n'
        if criteria_text
        else ""
    )
    criteria_block = (
        f"\nCriteria to check (the person's own):\n{criteria_text}\n" if criteria_text else ""
    )
    return f"""You are helping a salesperson at a technology services company decide, in one \
minute, whether a company is worth approaching.

Company: {name}
Website: {domain}

Ground rules:
- Use ONLY the numbered evidence below. Do not use anything else you know about this company.
- Write plainly, like a colleague explaining it. No marketing words, no guesses about budget or \
plans.
- "what_they_do": two or three sentences on what the company does and who it serves.
- "relevance": two or three sentences on how what they do relates to what we sell (listed below), \
or say plainly that it does not.
- "working_on": two to four points on what the company is doing, and how, in the areas we sell in \
(listed below): programmes, technology moves, partnerships, hiring. Use recent news, open jobs and \
their own site first. Each point has a short VERBATIM quote and its evidence label; a point \
without a real quote will be discarded. Do not list things that have nothing to do with our \
offerings.
- "offerings": up to three of OUR offerings (by label, for example O2) that connect to that work. \
For each, "band" is strong (their own site, recent news or an open job clearly shows a need we \
serve), potential (a plausible need), or weak (a stretch). Give a short VERBATIM quote and its \
evidence label for anything strong or potential; a quote that is not in the evidence will be \
discarded. "idea" is one sentence on what we would offer them and how; "why_now" is one sentence \
naming the move of theirs it builds on.
- "call": yes (worth approaching now), maybe (worth a conversation), no (not a fit), or unclear \
(not enough information). Give the reason in one sentence.
- If the evidence does not say something, leave it out.
{focus_rule}{criteria_rule}
Our offerings:
{offerings_text}
{criteria_block}
Evidence:
{wrap_untrusted(evidence_text, "evidence")}"""
