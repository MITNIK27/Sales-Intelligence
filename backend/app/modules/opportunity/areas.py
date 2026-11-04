"""Opportunity areas are free text ("AI adoption", "cloud migration"), so each one is reduced to a
stable key. The key is what makes "the same area asked for twice" find the same opportunity, and
it is part of every cache key that depends on an area."""

import re
import unicodedata

from app.modules.opportunity.models import GENERAL_AREA_KEY

_MAX_KEY_CHARS = 120
_MAX_LABEL_CHARS = 200


def clean_area_label(label: str | None) -> str | None:
    """The area as a person reads it: whitespace tidied, length bounded; None when blank."""
    text = " ".join((label or "").split())[:_MAX_LABEL_CHARS].strip()
    return text or None


def normalize_area_key(label: str | None) -> str:
    """A lower-case slug with accents removed and every run of other characters turned into a
    single hyphen. A blank label is the whole-company opportunity, `general`."""
    cleaned = clean_area_label(label)
    if cleaned is None:
        return GENERAL_AREA_KEY
    ascii_text = unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:_MAX_KEY_CHARS].strip("-")
    return slug or GENERAL_AREA_KEY
