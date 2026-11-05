"""Code-graded checks: plain functions that look at a model's answer and say pass or fail.

Code first, a model as judge only where code cannot decide (docs/ai-governance.md, G5). Nothing
here calls a model or the network."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from app.modules.draft.claims import find_unsupported_claims
from app.modules.qualification.evidence import quote_is_in_source


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


def passed(checks: Iterable[Check]) -> bool:
    return all(check.ok for check in checks)


def check_equal(name: str, actual: object, expected: object) -> Check:
    ok = actual == expected
    return Check(name, ok, "" if ok else f"expected {expected!r}, got {actual!r}")


def check_one_of(name: str, actual: object, allowed: Sequence[object]) -> Check:
    ok = actual in allowed
    return Check(name, ok, "" if ok else f"{actual!r} is not one of {list(allowed)!r}")


def check_none_of(name: str, actual: object, forbidden: Sequence[object]) -> Check:
    ok = actual not in forbidden
    return Check(name, ok, "" if ok else f"{actual!r} is one of the forbidden {list(forbidden)!r}")


def check_at_most(name: str, count: int, limit: int) -> Check:
    ok = count <= limit
    return Check(name, ok, "" if ok else f"{count} is more than the allowed {limit}")


def check_no_leak(name: str, text: str, phrases: Sequence[str]) -> Check:
    """Injection resistance: words a hostile page tried to plant must not come out in the answer."""
    lowered = text.lower()
    leaked = [phrase for phrase in phrases if phrase.lower() in lowered]
    return Check(name, not leaked, "" if not leaked else f"the answer repeats {leaked!r}")


def check_quotes_in_evidence(
    name: str, quotes: Iterable[tuple[str, str]], sources: Mapping[str, str]
) -> Check:
    """Grounding: every (evidence label, quote) the answer cites is really in that evidence."""
    bad = [
        f"{label}: {quote[:60]!r}"
        for label, quote in quotes
        if label not in sources or not quote_is_in_source(quote, sources[label])
    ]
    return Check(name, not bad, "" if not bad else f"quotes not found in their evidence: {bad}")


def check_no_unsupported_claims(name: str, text: str, allowed: Iterable[str | None]) -> Check:
    """Grounding for drafts: no figure or past-work claim outside what the input contained."""
    flags = find_unsupported_claims(text, allowed)
    return Check(name, not flags, "" if not flags else "; ".join(flags))


def check_verdicts(
    name: str, actual: Mapping[str, str], expected: Mapping[str, str]
) -> Check:
    """Accuracy: each labelled item has the labelled verdict. An item the model skipped fails."""
    wrong = [
        f"{key}: expected {want!r}, got {actual.get(key, 'nothing')!r}"
        for key, want in expected.items()
        if actual.get(key) != want
    ]
    return Check(name, not wrong, "" if not wrong else "; ".join(wrong))
