"""A last, deterministic check on a finished email (docs/ai-governance.md, G3).

The draft prompt forbids inventing figures, customers and case studies, but a prompt is a request,
not a guarantee. This reads the finished text and lists anything that looks like a claim of that
kind and is not in what the draft was given. It only flags: the rep reads the email either way,
so a false alarm costs a glance and a missed claim is the expensive mistake."""

import re
from collections.abc import Iterable

MAX_FLAGS = 5

# Figures a sales email must not make up. Years and dates are left alone, and so are headcounts
# ("200 employees"), because a size range from the research is often paraphrased.
_FIGURES = [
    re.compile(r"[$€£]\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|m|bn|b|million|billion|thousand)\b)?", re.I),
    re.compile(r"\b\d+(?:\.\d+)?\s?%"),
    re.compile(r"\b\d+(?:\.\d+)?x\b", re.I),
    re.compile(
        r"\b\d[\d,]*\+?\s(?:years?|clients?|customers?|projects?|engineers?|countries|users"
        r"|companies)\b",
        re.I,
    ),
]

# Wording that claims past work or named customers.
_PHRASES = [
    re.compile(r"\bcase stud(?:y|ies)\b", re.I),
    re.compile(r"\bour (?:clients?|customers?)\b", re.I),
    re.compile(
        r"\b(?:we|we've|we have) (?:helped|worked with|delivered|built|partnered with)\b", re.I
    ),
    re.compile(r"\b(?:clients?|customers?) (?:like|such as)\b", re.I),
    re.compile(r"\btrusted by\b", re.I),
    re.compile(r"\bfortune ?\d+\b", re.I),
]


def _squash(text: str) -> str:
    return re.sub(r"[\s,]", "", text.lower())


def find_unsupported_claims(text: str, allowed: Iterable[str | None]) -> list[str]:
    """Short, human-readable flags for each figure or past-work claim in `text` that does not
    appear in `allowed` (the research, offering description and earlier emails the draft had)."""
    haystack = " ".join(part for part in allowed if part)
    squashed = _squash(haystack)
    spaced = " ".join(haystack.lower().split())
    flags: list[str] = []
    seen: set[str] = set()

    for pattern in _FIGURES:
        for figure in pattern.finditer(text):
            claim = figure.group(0).strip()
            key = _squash(claim)
            if key in squashed or key in seen:
                continue
            seen.add(key)
            flags.append(f'Check "{claim}": it is not in the research this draft was given.')

    for pattern in _PHRASES:
        phrase = pattern.search(text)
        if phrase is None:
            continue
        claim = " ".join(phrase.group(0).lower().split())
        if claim in spaced or claim in seen:
            continue
        seen.add(claim)
        flags.append(f'Check "{phrase.group(0)}": no past work or customer is in the research.')

    return flags[:MAX_FLAGS]
