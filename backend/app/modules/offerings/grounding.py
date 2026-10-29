"""A cheap, deterministic check that a written description sticks to what its page says. It cannot
prove a description is right, but it reliably points at the usual failures: an invented number, a
statistic repeated from marketing copy, or a name the page never uses."""

import re

_MAX_FLAGS = 5
_EXCERPT_CHARS = 600

_NUMBER = re.compile(r"\d[\d,.]*\s?%?")
# A capitalised word, or an acronym, that is not simply the first word of a sentence.
_TERM = re.compile(r"(?<![.!?]\s)(?<!^)\b([A-Z][A-Za-z0-9]{2,}|[A-Z]{2,})\b")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def source_excerpt(page_text: str) -> str:
    """The start of the page, enough for a reviewer to compare the description against."""
    return re.sub(r"\s+", " ", page_text).strip()[:_EXCERPT_CHARS]


def check_grounding(name: str, description: str | None, page_text: str) -> list[str]:
    """Plain-language flags, empty when everything checks out."""
    page = _normalize(page_text)
    flags: list[str] = []

    if name and _normalize(name) not in page:
        flags.append(f'the name "{name}" is not on the page')

    for token in _NUMBER.findall(description or ""):
        cleaned = token.strip().rstrip(".,")
        if "%" in cleaned:
            flags.append(f"includes a percentage ({cleaned}); descriptions should not")
        elif cleaned.lower() not in page:
            flags.append(f"the number {cleaned} is not on the page")

    seen: set[str] = set()
    for match in _TERM.finditer(description or ""):
        term = match.group(1)
        if term.lower() in seen:
            continue
        seen.add(term.lower())
        if term.lower() not in page:
            flags.append(f'"{term}" is not on the page')

    return flags[:_MAX_FLAGS]
