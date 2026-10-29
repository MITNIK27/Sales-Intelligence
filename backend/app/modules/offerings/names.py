"""Whether two offering names are the same thing written differently."""

import re

# A word that may follow a name without making it a different offering.
_QUALIFIERS = {"ai", "for", "by", "platform", "suite"}


def _words(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def names_match(a: str, b: str) -> bool:
    """"Expona AI" and "Expona", "Spacewarp for ServiceNow" and "Spacewarp" match; "Cloud" and
    "Cloud Migration Suite" do not."""
    wa, wb = _words(a), _words(b)
    if wa == wb:
        return True
    shorter, longer = sorted((wa, wb), key=len)
    if not shorter or not longer.startswith(shorter + " "):
        return False
    # Only a qualifier after the name counts, not a longer, different name that merely starts the
    # same way.
    return longer[len(shorter) + 1 :].split()[0] in _QUALIFIERS
