"""Deterministic, non-LLM backstop against listicle/article-title noise the extraction model
(`extractor.py`) might still accept as if it were a real company name — regex/shape checks only,
no model call. Applied in `agent.py` alongside `ExtractedCompany.accepted`.

The extraction prompt already instructs the model not to treat a listicle/directory/news page as
a company (`prompts.py`), but that's the model's own self-report — nothing upstream corroborates
it, and a weak free-tier model given only a thin title+snippet can and does return the page's own
title as if it were a company. This exists because that failure mode was observed live."""

import re

_ORDINAL_LIST_RE = re.compile(r"^(?:the\s+)?(top|best|worst|leading)\s+\d+\b", re.IGNORECASE)
_LIST_OF_RE = re.compile(r"^list of\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_LIST_NOUN_RE = re.compile(
    r"\b(companies|providers|firms|vendors|startups|businesses|list|guide|rankings?)\b",
    re.IGNORECASE,
)
_PAGE_TITLE_PIPE_RE = re.compile(r".+\|.+")


def classify_candidate_name(name: str) -> tuple[str | None, str | None]:
    """Returns (verdict, reason).

    - "reject": confidently a listicle/article title, not a company — safe to drop outright,
      overriding even an LLM `accepted=True` verdict.
    - "flag": structurally suspicious but not certain — kept (nothing here is silently lost),
      flagged with `needs_review` and a specific, actionable reason.
    - (None, None): no concern.
    """
    stripped = name.strip()

    if _ORDINAL_LIST_RE.match(stripped):
        reason = f"looks like a listicle title (matches 'Top/Best/Leading N ...'): {stripped!r}"
        return "reject", reason
    if _LIST_OF_RE.match(stripped):
        return "reject", f"looks like a listicle title (matches 'List of ...'): {stripped!r}"

    if _PAGE_TITLE_PIPE_RE.match(stripped) and stripped == stripped.title():
        return "flag", f"looks like a title-case, pipe-separated page title: {stripped!r}"
    if _YEAR_RE.search(stripped) and _LIST_NOUN_RE.search(stripped):
        reason = f"contains a bare year alongside a generic listicle word: {stripped!r}"
        return "flag", reason

    return None, None
