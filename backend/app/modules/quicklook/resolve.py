"""Which company did the person mean? A name on its own can match several websites, so search
results are turned into candidates and scored by how well the name matches the site and how closely
the result relates to the areas we sell in. The best one is picked only when it clearly leads;
otherwise the person is asked. Pure functions: no network, easy to test."""

import re
from dataclasses import dataclass

from app.modules.companies.service import is_denylisted_domain, normalize_domain

MAX_CANDIDATES = 5
PICK_MIN_SCORE = 50  # below this the top result is not convincing on its own
PICK_MIN_LEAD = 15  # the best must beat the next by this much to be picked without asking

_SUFFIXES = frozenset(
    {"inc", "llc", "ltd", "limited", "corp", "corporation", "co", "company", "plc", "gmbh", "the"}
)
_SECOND_LEVEL = frozenset({"co", "com", "org", "net", "gov", "ac", "edu"})
_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Candidate:
    name: str
    domain: str
    snippet: str
    score: int = 0


def name_tokens(name: str) -> list[str]:
    return [t for t in _WORD.findall(name.lower()) if t not in _SUFFIXES]


def _site_label(domain: str) -> str:
    """The brand part of a website: "infor" in "infor.com", "bbc" in "bbc.co.uk"."""
    parts = domain.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in _SECOND_LEVEL:
        return parts[-3]
    return parts[-2] if len(parts) >= 2 else parts[0]


def _title_name(title: str) -> str:
    """A result title is usually "Brand - what it does" or "Brand | tagline"; keep the brand."""
    return re.split(r"\s[-|–—:·]\s", title.strip(), maxsplit=1)[0].strip()[:120] or title.strip()


def score_candidate(
    tokens: list[str], domain: str, title: str, snippet: str, position: int, area_words: set[str]
) -> int:
    label = _site_label(domain)
    compact = "".join(tokens)
    score = 0
    if compact and (compact == label or compact in label):
        score += 60
    elif tokens:
        score += int(30 * sum(t in label for t in tokens) / len(tokens))
    text = f"{title} {snippet}".lower()
    if tokens:
        score += int(20 * sum(t in text for t in tokens) / len(tokens))
    score += max(0, 10 - 2 * position)
    if area_words:
        words = set(_WORD.findall(text))
        score += min(10, 2 * len(words & area_words))
    return score


def build_candidates(
    name: str,
    results: list[dict[str, str]],
    denylist: list[str],
    area_words: set[str],
    avoid: set[str] | None = None,
) -> list[Candidate]:
    """One candidate per website, best first. Social and directory sites are skipped (they are
    still useful as evidence), and so are websites the person already said were wrong."""
    avoided = avoid or set()
    tokens = name_tokens(name)
    best: dict[str, Candidate] = {}
    for position, item in enumerate(results):
        domain = normalize_domain(item.get("link"))
        if not domain or domain in avoided or is_denylisted_domain(domain, denylist):
            continue
        title = item.get("title") or ""
        snippet = (item.get("snippet") or "").strip()
        score = score_candidate(tokens, domain, title, snippet, position, area_words)
        found = Candidate(_title_name(title) or domain, domain, snippet[:200], score)
        if domain not in best or found.score > best[domain].score:
            best[domain] = found
    ranked = sorted(best.values(), key=lambda c: c.score, reverse=True)
    return ranked[:MAX_CANDIDATES]


def pick(candidates: list[Candidate]) -> Candidate | None:
    """The candidate to go with, or None when the person should be asked."""
    if not candidates:
        return None
    top = candidates[0]
    if top.score < PICK_MIN_SCORE:
        return None
    if len(candidates) > 1 and top.score - candidates[1].score < PICK_MIN_LEAD:
        return None
    return top
