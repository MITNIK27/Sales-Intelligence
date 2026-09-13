"""The judgment prompt lives here as a standalone, provider-neutral asset — same reasoning as
`discovery_agent/prompts.py`: plain instructions plus a description of the required output
fields, not tied to any one SDK's structured-output mechanism, so every `QualificationGenerator`
implementation formats this same text and only swaps how it binds the response to a schema.

The LLM is asked ONLY for per-criterion verdicts — never an overall qualified/not_qualified call.
That gate is computed deterministically in `service.py` from `is_disqualifying`, per the explicit
design decision for this phase: auditable Python logic, not a model inferring intent from wording.
"""

from app.modules.companies.models import Company
from app.modules.enrichment.models import EnrichmentRecord
from app.modules.qualification.models import QualificationCriterion

# Recent signals are informative but unbounded history isn't useful in a prompt — same cap and
# reasoning as ai_recommendation/recommendation_generator.py's MAX_SIGNALS_IN_PROMPT.
MAX_SIGNALS_IN_PROMPT = 10

_PROMPT = """You are judging a company against a sales organization's own qualification \
criteria, one criterion at a time. This judgment decides whether a real sales rep spends real \
time pursuing this company — a wrong "met" wastes their time on a bad-fit prospect, a wrong \
"not_met" costs a real opportunity, and a lazy "could_not_determine" when the evidence actually \
does answer the question is just as unhelpful. Get each one right individually; do not average \
or rush.

Company:
- Name: {company_name}
- Domain: {company_domain}
- Industry: {company_industry}
- Employee count range: {company_employee_count_range}
- Description: {company_description}

Recent signals (news, hiring activity) for this company:
{signals}

Criteria to judge against (each has an id — judge every one independently, in isolation from \
the others; a verdict on one criterion must never influence a verdict on another):
{criteria}

Ground rules, all of which apply to every criterion:

1. COMPLETENESS: output exactly one entry per criterion id listed above — never fewer (do not \
skip a criterion because it seems hard to judge; "could_not_determine" is always a valid, \
complete answer), never more (never invent a criterion that wasn't given), and never a \
criterion_id that doesn't appear above.

2. GROUNDING: a verdict of "met" or "not_met" must be justified by something actually written \
in the Company or Signals text above. Do not use general/parametric knowledge about this \
company, its industry, or companies like it to fill gaps in what's written — if the criterion \
asks about something the text above doesn't address, the correct verdict is \
"could_not_determine", full stop, regardless of what you believe is probably true.

3. NO HALO EFFECT: a large, famous, or reputable company must NOT be assumed to meet a \
criterion just because of its size or reputation, and a small or unknown company must NOT be \
assumed to fail one just because it's obscure. Judge only the specific text given, the same way \
for every company regardless of how recognizable its name is.

4. SILENCE IS NOT FAILURE: "could_not_determine" and "not_met" are different claims. \
"not_met" means the text above actively contradicts or rules out the criterion. \
"could_not_determine" means the text is simply silent on it. Example: if a criterion is \
"has an active digital-transformation initiative" and the company description only says \
"a logistics company operating in six countries" with no mention of technology at all, the \
correct verdict is "could_not_determine" — NOT "not_met". Only use "not_met" when the evidence \
itself points the other way (e.g. the description explicitly describes a small, purely local, \
manual operation with no digital initiatives mentioned anywhere despite the description \
otherwise being detailed about operations).

5. CONFLICTING EVIDENCE: if signals disagree with each other or with the description (e.g. an \
old signal suggests one thing, a more recent one suggests another), prefer the most recent \
evidence, note the conflict explicitly in the reasoning, and lean toward "could_not_determine" \
rather than picking a side with unstated confidence.

For each criterion, output:
- criterion_id: copied exactly as given.
- verdict: "met" | "not_met" | "could_not_determine" — per the ground rules above.
- reasoning: one sentence. If "met" or "not_met", quote or closely paraphrase the specific \
evidence that drove it. If "could_not_determine", say plainly what's missing (e.g. "no \
information above addresses IT spend or budget").

If no signals are available at all, reason from firmographics alone and expect most criteria \
that aren't answerable from name/domain/industry/employee-range/description to land on \
could_not_determine — that is the correct, expected outcome, not a failure of this judgment.
"""


def _format_signals(signals: list[EnrichmentRecord]) -> str:
    if not signals:
        return "No recent buying signals found for this company."
    lines = []
    for record in signals[:MAX_SIGNALS_IN_PROMPT]:
        signal_type = record.raw_payload.get("signal_type", "signal")
        text = record.raw_payload.get("text", "")
        lines.append(f"- [{signal_type}] {text}")
    return "\n".join(lines)


def _format_criteria(criteria: list[QualificationCriterion]) -> str:
    lines = []
    for criterion in criteria:
        description = criterion.description or "(no further description given)"
        lines.append(f"[{criterion.id}] {criterion.name}: {description}")
    return "\n".join(lines)


def build_qualification_prompt(
    company: Company, signals: list[EnrichmentRecord], criteria: list[QualificationCriterion]
) -> str:
    return _PROMPT.format(
        company_name=company.name,
        company_domain=company.domain or "unknown",
        company_industry=company.industry or "unknown",
        company_employee_count_range=company.employee_count_range or "unknown",
        company_description=company.description or "No description available.",
        signals=_format_signals(signals),
        criteria=_format_criteria(criteria),
    )
