"""Turns one page of InfoBeans' website into "is this an offering, and what is it?"."""

from typing import Literal

from pydantic import BaseModel

from app.modules.llm.structured import StructuredLLM

# Only this much of a page is shown to the model: the top of a marketing page carries what the
# offering is; the rest is boilerplate, and a smaller prompt keeps a free-tier call cheap.
_PROMPT_CHARS = 8_000

_PROMPT = """You are cataloguing what the IT services company InfoBeans sells, from one page of \
its own website.

Decide whether this page describes ONE specific offering InfoBeans sells to clients:
- "service": a capability or discipline InfoBeans delivers for clients (for example cloud \
engineering, QA automation, ServiceNow or Salesforce implementation).
- "product": a packaged software product, platform or accelerator that InfoBeans owns.

It is NOT an offering (set is_offering to false) when the page is: a list or overview of many \
offerings, an industry or market page, a case study, an article, a playbook or white paper, \
about/people/careers/news/legal/contact content, or a partner badge page.

If it is an offering, give:
- name: the offering's own name, short, without the company name or "| InfoBeans".
- description: 2 to 3 plain sentences saying what it is, who it is for, and the problem it \
solves. Use only what the page says. Do not invent anything. Never include numbers, \
percentages or statistics (such as "up to 85%" or "30% faster"), even when the page has them.

Page address: {url}

Page text:
\"\"\"{text}\"\"\"
"""


class OfferingExtraction(BaseModel):
    is_offering: bool
    kind: Literal["service", "product"] | None = None
    name: str | None = None
    description: str | None = None


_FORCED_NOTE = """A person has already confirmed that this page describes an offering, so set \
is_offering to true and choose its kind. Do not second-guess that.

"""


async def extract_offering(
    llm: StructuredLLM, url: str, text: str, forced: bool = False
) -> OfferingExtraction | None:
    """The extraction, or `None` when the page is not a usable offering (not one, or the model
    left out its kind or name). `forced` is for a page a person has said is an offering: the model
    is told so, and only a missing kind or name can make it unusable."""
    prompt = _PROMPT.format(url=url, text=text[:_PROMPT_CHARS])
    result = await llm.generate((_FORCED_NOTE + prompt) if forced else prompt, OfferingExtraction)
    if not forced and not result.is_offering:
        return None
    if result.kind is None or not (result.name or "").strip():
        return None
    return result
