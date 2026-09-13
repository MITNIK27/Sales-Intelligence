"""The classification prompt lives here as a standalone, provider-neutral asset — same reasoning
as `qualification/prompts.py`: plain instructions plus a description of the required output
fields, not tied to any one SDK's structured-output mechanism.

The LLM is asked ONLY to match each contact to a role category (or none) — never to decide
priority. That gate is computed deterministically in `service.py` from
`RoleCategory.is_primary_target`, per the same design decision as Phase A2.2's qualification
verdict: auditable Python logic, not a model inferring intent from wording.
"""

from app.modules.companies.models import Company
from app.modules.contacts.models import Contact
from app.modules.role_relevance.models import RoleCategory

_PROMPT = """You are matching a company's contacts to a sales organization's own role categories, \
one contact at a time. This decides who a rep spends limited outreach effort on — a wrong match \
wastes that effort on the wrong person, and a wrong "no match" means a real decision-maker gets \
skipped. Get each one right individually; do not average or rush.

Company (for context — the same job function can have very different titles depending on the \
company's industry and size):
- Name: {company_name}
- Industry: {company_industry}
- Description: {company_description}

Contacts to classify (each has an id — classify every one independently, in isolation from the \
others; a match on one contact must never influence a match on another):
{contacts}

Role categories to match against (each has an id):
{categories}

Ground rules, all of which apply to every contact:

1. COMPLETENESS: output exactly one entry per contact id listed above — never fewer (do not skip \
a contact because the title is ambiguous; a null match is always a valid, complete answer), never \
more, and never a contact_id that doesn't appear above.

2. GROUNDING: a match must be justified by the contact's actual title/seniority text given above. \
Do not use general assumptions about what a company "usually" has in a given role, or about what \
a title like this "typically" means at other companies — reason from the specific text given.

3. TITLES AREN'T STANDARDIZED: the same underlying function is called different things at \
different companies (e.g. "IT vendor" at one company, "category procurement manager" at another). \
Infer the underlying function the title actually describes — using the title text plus the \
company's industry context above — rather than doing literal keyword matching between the title \
and a category's name. A title that never uses a category's exact words can still be the correct \
match if the function clearly lines up; a title that echoes a category's words can still be the \
wrong match if the actual function described is different.

4. NULL IS A VALID, EXPECTED ANSWER: if no given category genuinely fits a contact's function, \
output matched_category_id: null rather than forcing the closest-but-wrong match. This is the \
correct, expected outcome for contacts outside the categories configured — not a failure of this \
classification.

5. SENIORITY IS NOT FUNCTION: a senior title (VP, Director, Head of...) must NOT be matched to a \
category just because it sounds important or senior. The match must stand on the function \
described, independent of how senior the title is — a senior title in an unrelated function is \
still a null match, and a junior title in a matching function is still a real match.

For each contact, output:
- contact_id: copied exactly as given.
- matched_category_id: the id of the single best-fitting category, or null if none genuinely fits.
- reasoning: one sentence explaining the function you inferred from the title (and why it does or
  doesn't line up with the matched category, or why nothing matched).
"""


def _format_contacts(contacts: list[Contact]) -> str:
    lines = []
    for contact in contacts:
        name = contact.full_name or "(name unknown)"
        title = contact.role_title or "(title unknown)"
        seniority = contact.seniority or "(seniority unknown)"
        lines.append(f"[{contact.id}] {name} — title: {title}, seniority: {seniority}")
    return "\n".join(lines)


def _format_categories(categories: list[RoleCategory]) -> str:
    lines = []
    for category in categories:
        description = category.description or "(no further description given)"
        lines.append(f"[{category.id}] {category.name}: {description}")
    return "\n".join(lines)


def build_role_relevance_prompt(
    company: Company, contacts: list[Contact], categories: list[RoleCategory]
) -> str:
    return _PROMPT.format(
        company_name=company.name,
        company_industry=company.industry or "unknown",
        company_description=company.description or "No description available.",
        contacts=_format_contacts(contacts),
        categories=_format_categories(categories),
    )
