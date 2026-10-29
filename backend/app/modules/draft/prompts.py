"""First-touch and follow-up are genuinely different message shapes per the meeting — kept as
two separate templates rather than one parameterized template with a branch inside it, so each
reads as a complete, reviewable spec on its own."""

from app.modules.draft.models import (
    DRAFT_TYPE_FIRST_TOUCH,
    DRAFT_TYPE_FOLLOW_UP,
    DRAFT_TYPE_FOLLOW_UP_2,
    DRAFT_TYPE_FOLLOW_UP_3,
)
from app.modules.products.models import KIND_SERVICE

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


# Written for both templates: drafts are read by buyers, so they say what the buyer gets and what
# happens next, not how the thing is built. The role framing above may still ask for metrics.
SALES_LENS_INSTRUCTION = (
    "Write from a salesperson's point of view: say what the buyer gets and what the next step is. "
    "Translate technical descriptions into plain business language, and leave out architecture, "
    "tooling and feature lists unless the role framing above asks for technical detail."
)

# What the closing line may do depends on how far into the sequence this email is. Passing the
# email on to someone else is only natural once the reader has been written to a couple of times,
# so it appears from the second follow-up, never in a first touch. The concrete next step (a
# walkthrough or a conversation) comes from the chosen offering's own block, see
# `offering_guidance`, because the model picks the offering itself.
_NEVER_PUSHY = "Never pushy, hard or guilt-driven."

_CTA_INSTRUCTIONS = {
    DRAFT_TYPE_FIRST_TOUCH: (
        "Close with ONE soft, low-friction line proposing the next step named in your chosen "
        "option below, phrased as a light question or an easy offer. Do not point to another "
        "person or ask who else should look at it: this is a first message to the person you are "
        f"writing to. {_NEVER_PUSHY}"
    ),
    DRAFT_TYPE_FOLLOW_UP: (
        "Close with ONE light ask tied to the new detail you led with, using the next step named "
        "in your chosen option below (or offering to share a short summary). Do not ask them to "
        f"pass this to someone else yet. {_NEVER_PUSHY}"
    ),
    DRAFT_TYPE_FOLLOW_UP_2: (
        "Close with ONE soft ask using the next step named in your chosen option below, and add "
        "a courteous way out: if this is not theirs to look at, ask who on their team would be "
        f"the right person. {_NEVER_PUSHY}"
    ),
    DRAFT_TYPE_FOLLOW_UP_3: (
        "This is the last note in the sequence. Close briefly and politely: leave the door open, "
        "ask once who would be the right person to speak to if you have the wrong one, and make "
        f"clear no reply is needed if the timing is wrong. {_NEVER_PUSHY}"
    ),
}


def cta_instruction(draft_type: str) -> str:
    return _CTA_INSTRUCTIONS.get(draft_type, _CTA_INSTRUCTIONS[DRAFT_TYPE_FIRST_TOUCH])


def offering_guidance(kind: str) -> str:
    """Per option, so it applies to whichever offering the model ends up choosing."""
    if kind == KIND_SERVICE:
        return (
            "Type: Service. Lead with the outcome and relevant experience. The next step you may "
            "offer is a short conversation to understand their situation. Do not offer a demo or "
            "walkthrough, and do not list features or technical components."
        )
    return (
        "Type: Product. Say what it does for the buyer in plain business terms. The next step "
        "you may offer is a short walkthrough or demo."
    )


_PREVIOUS_BODY_CHARS = 1200


def format_previous_emails(emails: list[tuple[str | None, str]] | None) -> str:
    """The emails this person was already sent, oldest first, so a follow-up can build on them
    instead of repeating them. Empty for a first touch."""
    if not emails:
        return ""
    blocks = [
        f"--- Earlier email {i} ---\nSubject: {subject or '(none)'}\n{body[:_PREVIOUS_BODY_CHARS]}"
        for i, (subject, body) in enumerate(emails, start=1)
    ]
    return (
        "Earlier emails to this person (oldest first). Do not repeat their pitch or wording; "
        "build on them with something new:\n\n" + "\n\n".join(blocks)
    )


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

[One soft, low-friction closing line proposing a small next step.]

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
- {cta_instruction}
- Do NOT explicitly state "problem" or "solution" — no overclaiming, no listing pain points. Keep \
it short and human, not a pitch deck in email form.
- {framing_instruction}
- {sales_lens}
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
- {sales_lens}
- {cta_instruction}
- Do not use generic AI-outreach clichés ("just circling back", "wanted to bump this to the top \
of your inbox", "in today's fast-paced world") — a real salesperson recognizes these instantly \
and so do prospects; write like a person, not a template.
- Do not repeat the first email's pitch verbatim — add something new.

{previous_email_section}

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
