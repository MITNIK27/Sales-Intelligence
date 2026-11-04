"""Which offerings are worth judging for a company and area. A free, explainable pass over the
catalog so the model is shown a handful of offerings instead of every one: words shared between
what is known about the company and area and what each offering says about itself, weighted so an
offering's own area tags count most. Offerings the rep chose are always included. Pure functions."""

import re
from typing import Any

from app.modules.opportunity.models import GENERAL_AREA_KEY
from app.modules.products.models import Product

SHORTLIST_SIZE = 5
_MIN_WORD = 3
_STOP = {
    "and",
    "for",
    "the",
    "with",
    "from",
    "into",
    "our",
    "that",
    "this",
    "are",
    "was",
    "has",
    "have",
    "will",
    "can",
    "all",
    "its",
    "their",
    "your",
    "new",
    "more",
    "also",
    "about",
}

# How much a shared word counts, by where it appears in the offering's profile.
_W_AREA_TAG = 3
_W_KEYWORD = 2
_W_OTHER = 1


def words(text: str) -> set[str]:
    return {
        w
        for w in re.findall(r"[a-z0-9+#]+", text.lower())
        if len(w) >= _MIN_WORD and w not in _STOP
    }


def _profile(product: Product) -> dict[str, Any]:
    return product.buyer_profile or {}


def offering_weights(product: Product) -> dict[str, int]:
    """Each distinctive word an offering uses about itself, with the weight of its best source."""
    weights: dict[str, int] = {}

    def add(texts: list[str], weight: int) -> None:
        for text in texts:
            for word in words(text):
                weights[word] = max(weights.get(word, 0), weight)

    profile = _profile(product)
    add(profile.get("area_tags", []), _W_AREA_TAG)
    add(profile.get("keywords", []), _W_KEYWORD)
    add([product.name, product.description or ""], _W_OTHER)
    add(profile.get("problems", []), _W_OTHER)
    return weights


def relevance_score(product: Product, context_words: set[str]) -> int:
    return sum(w for word, w in offering_weights(product).items() if word in context_words)


def shortlist(
    products: list[Product],
    context_text: str,
    chosen_ids: set[Any] | None = None,
    limit: int = SHORTLIST_SIZE,
) -> list[Product]:
    """Chosen offerings first, then the best-scoring others that share at least one word with the
    context. An offering that shares nothing is never shortlisted, however short the list."""
    chosen_ids = chosen_ids or set()
    context_words = words(context_text)
    chosen = [p for p in products if p.id in chosen_ids]
    scored = sorted(
        (
            (relevance_score(p, context_words), p.name.lower(), p)
            for p in products
            if p.id not in chosen_ids
        ),
        key=lambda row: (-row[0], row[1]),
    )
    others = [p for score, _name, p in scored if score > 0]
    return (chosen + others)[: max(limit, len(chosen))]


def area_alignment(product: Product, area_key: str, area_label: str) -> bool:
    """Whether the offering says it belongs to this area: a word of the area appears in its area
    tags or its name. The whole-company opportunity has no area, so nothing aligns with it."""
    if area_key == GENERAL_AREA_KEY:
        return False
    area_words = words(area_label)
    own = words(" ".join(_profile(product).get("area_tags", []))) | words(product.name)
    return bool(area_words & own)


def keyword_hits(product: Product, evidence_text: str) -> int:
    """How many of the offering's own keywords appear in the evidence, as words or phrases."""
    text = evidence_text.lower()
    hits = 0
    for keyword in _profile(product).get("keywords", []):
        phrase = keyword.strip().lower()
        if phrase and re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text):
            hits += 1
    return hits
