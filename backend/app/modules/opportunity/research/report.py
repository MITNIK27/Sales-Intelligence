"""Turning what the collectors did into plain statements, in code. When a collector looked and
found nothing, the screen says exactly what was searched, instead of leaving the reader to wonder
whether anything was checked at all."""

from datetime import UTC, datetime, timedelta
from typing import Any

from app.modules.opportunity.research.types import KIND_HIRING, KIND_NEWS, KIND_WEB

# How long a collector's results stay fresh before the same request searches again.
FRESH_FOR = {
    KIND_NEWS: timedelta(days=7),
    KIND_HIRING: timedelta(days=3),
    KIND_WEB: timedelta(days=14),
}

_MAX_SNAPSHOTS = 12
TREND_UP, TREND_DOWN, TREND_FLAT = "up", "down", "flat"

_WHAT = {
    KIND_NEWS: "recent news",
    KIND_HIRING: "job postings",
    KIND_WEB: "announcements and pages on the web",
}


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def is_fresh(log: dict[str, Any] | None, kind: str, now: datetime) -> bool:
    """True when this kind was collected recently enough that searching again would only repeat it.
    A run that errored is never fresh, so it is tried again."""
    entry = (log or {}).get(kind)
    if not isinstance(entry, dict) or entry.get("error"):
        return False
    at = parse_time(entry.get("at"))
    return at is not None and now - at < FRESH_FOR[kind]


def add_snapshot(
    existing: list[dict[str, Any]] | None, now: datetime, total: int | None, matching: int
) -> list[dict[str, Any]]:
    """Append today's hiring count. Kept over time, it is what makes a trend possible later."""
    snapshots = [*(existing or []), {"at": now.isoformat(), "total": total, "matching": matching}]
    return snapshots[-_MAX_SNAPSHOTS:]


def hiring_trend(snapshots: list[dict[str, Any]] | None) -> str | None:
    """Direction of the matching-posting count between the last two snapshots. None until there
    are two: one count is a number, not a trend, and the screen says so."""
    counts: list[int] = [
        m for s in snapshots or [] if isinstance(m := s.get("matching"), int)
    ]
    if len(counts) < 2:
        return None
    before, now = counts[-2], counts[-1]
    return TREND_UP if now > before else TREND_DOWN if now < before else TREND_FLAT


def gap_statements(log: dict[str, Any] | None) -> list[str]:
    """One plain sentence for each collector that looked and found nothing, or could not look."""
    statements: list[str] = []
    for kind in (KIND_HIRING, KIND_NEWS, KIND_WEB):
        entry = (log or {}).get(kind)
        if not isinstance(entry, dict):
            continue
        searched = ", ".join(entry.get("searched") or []) or "the available sources"
        if entry.get("error"):
            statements.append(f"Could not check {_WHAT[kind]}: {entry['error']}")
        elif not entry.get("found"):
            if kind == KIND_HIRING and not entry.get("board"):
                statements.append(
                    "No job postings found: the company's careers page does not link to a public "
                    "job board we can read, so its openings could not be checked."
                )
            else:
                statements.append(f"No {_WHAT[kind]} found (searched {searched}).")
    return statements
