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


FIRST_TOUCH_PROMPT_TEMPLATE = """You are writing a first cold outreach email from a salesperson \
to a prospect. This is customer-facing message copy — it will be sent as-is unless a human edits \
it first.

Strict structure and length: **max 7-8 lines total**.
- 1-2 lines of credibility (who you are, your company, relevant partnerships — grounded only in \
the information given below, never invented).
- 1-2 lines citing a relevant proof point or analogous project. {grounding_instruction}
- One closing call-to-action line.
- Do NOT explicitly state "problem" or "solution" — no overclaiming, no listing pain points. Keep \
it short and human, not a pitch deck in email form.
- {framing_instruction}
- Do not use generic AI-outreach clichés ("I hope this email finds you well", "I wanted to reach \
out", "in today's fast-paced world"). Write like a real person who did their homework, not a \
template.

Recipient:
- Name: {contact_name}
- Role: {contact_role}

Company being contacted:
- Name: {company_name}
- Industry: {company_industry}
- Description: {company_description}

What's being offered:
- Product/service: {product_name} — {product_description}

{grounding_section}

Write:
- subject: a short, specific, non-clickbait subject line.
- body: the email body, following the structure above exactly.
"""

FOLLOW_UP_PROMPT_TEMPLATE = """You are writing a follow-up outreach email from a salesperson to \
a prospect who has not yet responded to a prior message. This is customer-facing message copy — \
it will be sent as-is unless a human edits it first.

This is NOT a "just following up" nudge — it must offer something informational or useful on its \
own (a relevant insight, a short resource, a specific observation about their company), so it has \
value even if they never reply to the first message. Keep it short (a few lines).
- {framing_instruction}
- Do not use generic AI-outreach clichés ("just circling back", "wanted to bump this to the top \
of your inbox", "in today's fast-paced world") — a real salesperson recognizes these instantly \
and so do prospects; write like a person, not a template.
- Do not repeat the first email's pitch verbatim — add something new.

Recipient:
- Name: {contact_name}
- Role: {contact_role}

Company being contacted:
- Name: {company_name}
- Industry: {company_industry}
- Description: {company_description}

What's being offered:
- Product/service: {product_name} — {product_description}

{grounding_section}

Write:
- subject: a short, specific subject line (can reference the prior email lightly, but the body \
should stand on its own).
- body: the email body, following the guidance above.
"""
