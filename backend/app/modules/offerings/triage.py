"""A light first look at blog posts: from the title and a one-line description alone, which posts
could be a page about something InfoBeans sells? Only those are read in full by the stronger
model, so hundreds of articles cost a handful of small calls instead of hundreds of big ones."""

import re
from dataclasses import dataclass

from pydantic import BaseModel

from app.modules.llm.structured import LLMError, StructuredLLM

BATCH_SIZE = 20
_BLURB_CHARS = 160

_PROMPT = """You are screening pages from the blog of the IT services company InfoBeans. For \
each numbered page below you are given only its title and, if known, a short description.

Pick the pages that are probably ABOUT ONE specific product, platform, accelerator or service \
that InfoBeans itself sells to clients (for example a named software product or a named service \
offering). Do NOT pick news, opinion, how-to articles, event or award announcements, customer \
stories, general technology explainers, or posts about other companies.

When unsure, leave the page out.

Reply with a single JSON object: {{"offering_numbers": [<the numbers of the pages you picked>]}}

Pages:
{pages}
"""


class TriageResult(BaseModel):
    offering_numbers: list[int] = []


@dataclass(frozen=True)
class TriagePage:
    url: str
    title: str
    description: str | None = None


def title_from_url(url: str) -> str:
    """A readable stand-in title from the last part of the address, for when none is known."""
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[-_]+", " ", slug).strip() or url


def _render(pages: list[TriagePage]) -> str:
    lines = []
    for number, page in enumerate(pages, start=1):
        blurb = f" - {page.description[:_BLURB_CHARS]}" if page.description else ""
        lines.append(f"{number}. {page.title}{blurb}")
    return "\n".join(lines)


async def triage_posts(
    llm: StructuredLLM, pages: list[TriagePage]
) -> tuple[list[TriagePage], list[TriagePage], list[TriagePage]]:
    """(likely offerings, screened out, undecided). A batch the model could not answer is
    returned as undecided, so it is tried again next sync rather than remembered as "no"."""
    likely: list[TriagePage] = []
    screened_out: list[TriagePage] = []
    undecided: list[TriagePage] = []
    for start in range(0, len(pages), BATCH_SIZE):
        batch = pages[start : start + BATCH_SIZE]
        try:
            result = await llm.generate(_PROMPT.format(pages=_render(batch)), TriageResult)
        except LLMError:
            undecided.extend(batch)
            continue
        picked = {n for n in result.offering_numbers if 1 <= n <= len(batch)}
        for number, page in enumerate(batch, start=1):
            (likely if number in picked else screened_out).append(page)
    return likely, screened_out, undecided
