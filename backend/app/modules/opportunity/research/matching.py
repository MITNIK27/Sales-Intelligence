"""Which postings are about an area. A deliberately plain rule so it can be explained: a posting is
about the area when the area's words appear in its title or department, or at least two of them
appear in its description. The cheap check that decides what is worth keeping as evidence; whether
it shows real activity in the area is still the assessment's call."""

import re

from app.modules.opportunity.research.types import Posting

_STOPWORDS = {
    "and",
    "for",
    "the",
    "with",
    "from",
    "into",
    "our",
    "adoption",
    "services",
    "solutions",
}
_MIN_TERM_CHARS = 3
_MAX_POSTINGS_KEPT = 15


def area_terms(label: str) -> list[str]:
    """The distinctive words of an area label, lower-cased and without filler."""
    words = re.findall(r"[a-z0-9+#.]+", label.lower())
    seen: dict[str, None] = {}
    for word in words:
        word = word.strip(".")
        if len(word) >= _MIN_TERM_CHARS and word not in _STOPWORDS:
            seen.setdefault(word, None)
    return list(seen)


def _contains(text: str, term: str) -> bool:
    """The term as a whole word, allowing a plural or common ending ("cloud", "clouds",
    "migrating"), so "cloud" matches "cloud-native" but never "Cloudera"."""
    pattern = rf"(?<![a-z0-9]){re.escape(term)}(?:s|es|ed|ing)?(?![a-z0-9])"
    return re.search(pattern, text) is not None


def posting_matches(posting: Posting, terms: list[str]) -> bool:
    if not terms:
        return False
    headline = f"{posting.title} {posting.department or ''}".lower()
    if any(_contains(headline, term) for term in terms):
        return True
    body = posting.excerpt.lower()
    return sum(1 for term in terms if _contains(body, term)) >= 2


def matching_postings(postings: list[Posting], label: str) -> list[Posting]:
    terms = area_terms(label)
    return [p for p in postings if posting_matches(p, terms)][:_MAX_POSTINGS_KEPT]
