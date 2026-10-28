"""First-touch and follow-up are genuinely different message shapes per the meeting — kept as
two separate templates rather than one parameterized template with a branch inside it, so each
reads as a complete, reviewable spec on its own."""

_FRAMING_INSTRUCTIONS = {
    "business": (
        "Write in outcome/cost-savings language — frame value in terms of business results, "
        "time saved, revenue impact, or risk reduced. Avoid deep technical detail."
    ),
    "technical": (
        "Write in technical/KPI language — frame value in terms of concrete technical outcomes, "
        "metrics, or how it fits into an engineering workflow. Avoid vague business-speak."
    ),
}


def framing_instruction(framing_style: str) -> str:
    return _FRAMING_INSTRUCTIONS.get(framing_style, _FRAMING_INSTRUCTIONS["business"])


# Condensed, genericized from real outreach emails a working sales rep shared as reference —
# names/companies/events replaced with bracketed placeholders. These exist purely to anchor tone
# and structure; the model must never reuse their specific industry, names, or claims.
STYLE_REFERENCE_EXAMPLES = """Structure/tone reference only — do not copy any name, company, \
industry, or specific claim from these. Match their shape and voice, not their content:

---
Subject: Meeting with [sender] | [specific trigger, e.g. an event or named initiative]

Hi [recipient],

Saw that you'll be attending [specific trigger] next month.

I'm reaching out from [sender's company], a [one grounded credential — e.g. partner/status] \
focused on [relevant area].

Our team will be there as well, and I thought it would be great to connect in person for 15-20 \
minutes to exchange perspectives.

Best,

---
Subject: [Specific initiative/remit] | [outcome-oriented hook]

Hi [recipient],

Given your remit around [specific, researched detail about the recipient's role or initiative], \
I thought this [use case] may be relevant.

[Sender's company] currently [one grounded credential], and we've built [one concrete capability] \
that [what it does, one line].

Would you be open to a brief walkthrough, or is there someone better suited within your org to \
take a look?

Best,
---"""


FIRST_TOUCH_PROMPT_TEMPLATE = """You are writing a first cold outreach email from a salesperson \
to a prospect. This is customer-facing message copy — it will be sent as-is unless a human edits \
it first.

Strict structure and length: **max 7-8 lines total**.
- Opening line: lead with a specific, researched trigger about this recipient or company (their \
role/remit, something concrete from the description or grounding below) — never open with a \
generic credibility statement or greeting filler.
- 1-2 lines of credibility (who you are, your company, relevant partnerships — grounded only in \
the information given below, never invented) connected back to that specific trigger.
- 1-2 lines citing a relevant proof point or analogous project, grounded in whichever product \
option you choose below.
- One closing call-to-action line that is soft and low-friction (e.g. "would you be open to a \
brief walkthrough", "happy to connect if it makes sense") — optionally offer an explicit out, \
such as pointing to someone better suited. Never a hard or pushy ask.
- Do NOT explicitly state "problem" or "solution" — no overclaiming, no listing pain points. Keep \
it short and human, not a pitch deck in email form.
- {framing_instruction}
- Do not use generic AI-outreach clichés ("I hope this email finds you well", "I wanted to reach \
out", "in today's fast-paced world"). Write like a real person who did their homework, not a \
template.

{style_reference}

Recipient:
- Name: {contact_name}
- Role: {contact_role}

Company being contacted:
- Name: {company_name}
- Industry: {company_industry}
- Description: {company_description}

What's being offered — pick exactly ONE of the following numbered options, whichever best fits \
this specific company's evident need. Write the email about that one option only — never blend \
more than one service into a single email:

{product_options_section}

{evidence_section}

Write:
- subject: a short, specific, non-clickbait subject line that names the specific trigger/hook, \
not a generic label.
- body: the email body, following the structure above exactly, about the one option you chose.
- chosen_option: the number of the option above that this email is about.
"""

FOLLOW_UP_PROMPT_TEMPLATE = """You are writing a follow-up outreach email from a salesperson to \
a prospect who has not yet responded to a prior message. This is customer-facing message copy — \
it will be sent as-is unless a human edits it first.

This is NOT a "just following up" nudge — it must offer something informational or useful on its \
own (a relevant insight, a short resource, a specific observation about their company), so it has \
value even if they never reply to the first message. Keep it short (a few lines).
- Lead with the specific new detail or insight, not a reference to having emailed before.
- {framing_instruction}
- Close with a soft, low-friction ask (e.g. "would this be worth a brief look") — never a pushy \
or guilt-driven nudge. Optionally offer an explicit out, such as pointing to someone better suited.
- Do not use generic AI-outreach clichés ("just circling back", "wanted to bump this to the top \
of your inbox", "in today's fast-paced world") — a real salesperson recognizes these instantly \
and so do prospects; write like a person, not a template.
- Do not repeat the first email's pitch verbatim — add something new.

{style_reference}

Recipient:
- Name: {contact_name}
- Role: {contact_role}

Company being contacted:
- Name: {company_name}
- Industry: {company_industry}
- Description: {company_description}

What's being offered — pick exactly ONE of the following numbered options, whichever best fits \
this specific company's evident need. Write the email about that one option only — never blend \
more than one service into a single email:

{product_options_section}

{evidence_section}

Write:
- subject: a short, specific subject line (can reference the prior email lightly, but the body \
should stand on its own).
- body: the email body, following the guidance above, about the one option you chose.
- chosen_option: the number of the option above that this email is about.
"""
